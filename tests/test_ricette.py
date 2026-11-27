import pytest

from app import db
from app.logic.produzioni import ErroreProduzione, proponi_produzione
from app.logic.ricette import (
    ErroreRicetta,
    crea_prodotto_lab,
    dettaglio_ricetta,
    elimina_ricetta,
    lista_ricette,
    salva_ricetta,
)


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (1, 'Creme')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (2, 'Dolci finiti')")
    # RIFIN 50: l'anagrafica u.m. (il fixture qui NON passa da
    # db.inizializza, la tabella parte vuota): la resa confronta i NOMI
    c.execute("INSERT INTO unita_misura (nome) VALUES ('kg')")
    c.execute("INSERT INTO unita_misura (nome) VALUES ('pz')")
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, marca, unita_misura, densita) "
        "VALUES (1, 'Latte intero', NULL, 'Mucca', 'lt', 1.03)"
    )
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, unita_misura) "
        "VALUES (2, 'Uova pastorizzate', NULL, 'kg')"
    )
    # il bignè: prodotto di laboratorio MA senza ricetta (il caso di Nicolas)
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, sigla, unita_misura) "
        "VALUES (3, 'Bignè', 2, 'BIG', 'pz')"
    )
    # un lotto in ingresso: il latte è un acquistato
    c.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (100, 1, 1, 'LAT-A', '2026-11-10', '2026-11-20', 10, 10)"
    )
    c.commit()
    yield c
    c.close()


# ---- crea_prodotto_lab (creazione rapida dalla modale) ----

def test_crea_prodotto_lab_ok(conn):
    p = crea_prodotto_lab(conn, {"nome": "Torta della nonna", "unita_misura": "kg", "sigla": "tor"})
    assert p["id"] > 0 and p["famiglia"] is None and p["sigla"] == "TOR"
    riga = conn.execute("SELECT * FROM prodotti WHERE id = ?", (p["id"],)).fetchone()
    assert riga["famiglia_id"] is None and riga["unita_misura"] == "kg"


def test_crea_prodotto_lab_duplicato_respinto(conn):
    # RIFIN 45: due creazioni identiche NON si respingono più: senza
    # ricetta la prima è un candidato abbandonato (zero storia) e si
    # riusa. Il RESPINTO vero si prova quando il nome è occupato da
    # un'anagrafica finita: vedi i test del candidato più sotto
    p1 = crea_prodotto_lab(conn, {"nome": "Torta", "unita_misura": "kg"})
    p2 = crea_prodotto_lab(conn, {"nome": "torta", "unita_misura": "kg"})
    assert p2["id"] == p1["id"]  # la riga vuota si riusa, mai duplicati


def test_crea_prodotto_lab_um_opzionale(conn):
    # l'u.m. non serve più al prodotto di laboratorio: pensa la resa
    # della ricetta ('5 kg'). Se arriva vuota, resta NULL
    p = crea_prodotto_lab(conn, {"nome": "Torta", "unita_misura": ""})
    riga = conn.execute(
        "SELECT unita_misura FROM prodotti WHERE id = ?", (p["id"],)
    ).fetchone()
    assert riga["unita_misura"] is None


# ---- salva + dettaglio ----

def _bigne(**extra):
    base = {
        "prodotto_id": 3,
        "famiglia_id": 2,
        "resa": "60 pz",
        "procedimento": "Impasto, farcia a servizio.",
        "righe": [
            {"ingrediente_id": 1, "quantita": 2},
            {"ingrediente_id": 2, "quantita": 0.5},
        ],
    }
    base.update(extra)
    return base


def test_salva_nuova_e_dettaglio(conn):
    # famiglia 1 ("Creme"): diversa da quella del prodotto (2) per provare
    # che è la RICETTA a decidere e l'anagrafica a rispecchiare
    r = salva_ricetta(conn, _bigne(famiglia_id=1))
    assert r["prodotto"]["nome"] == "Bignè"
    assert r["famiglia"] == "Creme"
    assert [(x["nome"], x["quantita"]) for x in r["righe"]] == [
        ("Latte intero", 2.0), ("Uova pastorizzate", 0.5),
    ]
    # la famiglia NASCE nella ricetta: l'anagrafica del prodotto la rispecchia
    riga = conn.execute("SELECT famiglia_id FROM prodotti WHERE id = 3").fetchone()
    assert riga["famiglia_id"] == 1


def test_salvata_la_ricetta_il_prodotto_e_producibile(conn):
    with pytest.raises(ErroreProduzione, match="Ricette"):
        proponi_produzione(conn, 3)
    salva_ricetta(conn, _bigne())
    p = proponi_produzione(conn, 3)
    assert p["ricetta"]["resa"] == "60 pz"
    assert len(p["righe"]) == 2


def test_semilavorato_facoltativo_salvato_e_ritornato(conn):
    # RIFIN 56: il semilavorato facoltativo (riga facoltativa) si salva e si
    # dettaglio e nella proposta: il resto delle righe resta obbligatorio
    salva_ricetta(conn, _bigne(righe=[
        {"ingrediente_id": 1, "quantita": 2},
        {"ingrediente_id": 2, "quantita": 0.5, "facoltativa": True},
    ]))
    d = dettaglio_ricetta(conn, 3)
    far = {r["nome"]: r["facoltativa"] for r in d["righe"]}
    assert far == {"Latte intero": 0, "Uova pastorizzate": 1}
    # ritrova nel dettaglio; la proposta FEFO lo porta al form produzione
    p = proponi_produzione(conn, 3)
    assert [r["facoltativa"] for r in p["righe"]] == [False, True]


def test_resa_scrive_um_canonica_del_prodotto(conn):
    """RIFIN 50: la resa NOMINA l'u.m. canonica ('5 kg' -> kg), come la
    ricetta nomina la famiglia. Il prodotto nato dal ➕ non ce l'ha: senza
    base nota, la tendina u.m. di Produzioni non compare MAI."""
    p = crea_prodotto_lab(conn, {"nome": "Torta al cioccolato", "sigla": "TRC"})
    assert p["unita_misura"] is None
    salva_ricetta(conn, _bigne(prodotto_id=p["id"], resa="5 kg"))
    riga = conn.execute(
        "SELECT unita_misura FROM prodotti WHERE id = ?", (p["id"],)
    ).fetchone()
    assert riga["unita_misura"] == "kg"


def test_resa_aggiorna_um_e_virgola_decimale(conn):
    # '5,5 kg' con la virgola si legge come 5.5: e la ricetta è il MASTER:
    # il Bignè aveva 'pz', la resa lo riscrive
    salva_ricetta(conn, _bigne(resa="5,5 kg"))
    riga = conn.execute("SELECT unita_misura FROM prodotti WHERE id = 3").fetchone()
    assert riga["unita_misura"] == "kg"


def test_resa_um_ignota_o_muta_non_tocca_l_um(conn):
    """U.m. IGNOTA ('12 teglie' fuori dall'anagrafica) o resa muta: il
    prodotto resta esattamente com'era. Mai un'u.m. tolta o inventata."""
    salva_ricetta(conn, _bigne(resa="12 teglie"))
    riga = conn.execute("SELECT unita_misura FROM prodotti WHERE id = 3").fetchone()
    assert riga["unita_misura"] == "pz"
    salva_ricetta(conn, _bigne(resa=""))
    riga = conn.execute("SELECT unita_misura FROM prodotti WHERE id = 3").fetchone()
    assert riga["unita_misura"] == "pz"


def test_famiglia_nuova_creata_dalla_ricetta(conn):
    r = salva_ricetta(conn, _bigne(famiglia_id=None, famiglia_nuova="Torte"))
    assert r["famiglia"] == "Torte"
    n = conn.execute("SELECT COUNT(*) FROM famiglie").fetchone()[0]
    assert n == 3


def test_famiglia_esistente_per_nome_riusata(conn):
    salva_ricetta(conn, _bigne(famiglia_id=None, famiglia_nuova="dolci finiti"))
    n = conn.execute("SELECT COUNT(*) FROM famiglie").fetchone()[0]
    assert n == 2   # riusata, non duplicata


def test_famiglia_mancante_respinta(conn):
    with pytest.raises(ErroreRicetta, match="famiglia"):
        salva_ricetta(conn, _bigne(famiglia_id=None, famiglia_nuova=None))


def test_righe_vuote_respinte(conn):
    with pytest.raises(ErroreRicetta, match="senza ingredienti"):
        salva_ricetta(conn, _bigne(righe=[]))


def test_quantita_zero_respinta(conn):
    with pytest.raises(ErroreRicetta, match="maggiori di zero"):
        salva_ricetta(conn, _bigne(righe=[{"ingrediente_id": 1, "quantita": 0}]))


def test_riga_duplicata_respinta(conn):
    with pytest.raises(ErroreRicetta, match="due volte"):
        salva_ricetta(conn, _bigne(righe=[
            {"ingrediente_id": 1, "quantita": 2},
            {"ingrediente_id": 1, "quantita": 1},
        ]))


def test_ingrediente_inesistente_respinto(conn):
    with pytest.raises(ErroreRicetta, match="inesistente"):
        salva_ricetta(conn, _bigne(righe=[{"ingrediente_id": 99, "quantita": 1}]))


def test_ingrediente_acquistato_con_arrivi_respinto(conn):
    with pytest.raises(ErroreRicetta, match="acquistato"):
        salva_ricetta(conn, _bigne(prodotto_id=1))


def test_aggiorna_ricetta_righe_rimpiazzate(conn):
    salva_ricetta(conn, _bigne())
    r = salva_ricetta(conn, _bigne(resa="80 pz", righe=[{"ingrediente_id": 1, "quantita": 3}]))
    assert r["resa"] == "80 pz"
    assert len(r["righe"]) == 1 and r["righe"][0]["quantita"] == 3.0
    n = conn.execute("SELECT COUNT(*) FROM ricette").fetchone()[0]
    assert n == 1   # upsert: stessa ricetta, non una seconda


def test_lista_ricette_filtro_testo(conn):
    salva_ricetta(conn, _bigne())
    assert len(lista_ricette(conn)) == 1
    assert lista_ricette(conn, "bign")[0]["prodotto"] == "Bignè"
    assert lista_ricette(conn, "torta") == []


def test_lista_ricette_porta_sigla(conn):
    """La tendina "Prodotto da produrre" di Produzioni nasce dalle ricette:
    la lista deve portare anche la sigla, con i dati presi da lì."""
    salva_ricetta(conn, _bigne())
    r = lista_ricette(conn)[0]
    assert r["prodotto_id"] == 3
    assert r["sigla"] == "BIG"
    assert r["famiglia"] == "Dolci finiti"


def test_dettaglio_senza_ricetta_none(conn):
    assert dettaglio_ricetta(conn, 3) is None


# ---- eliminazione protetta ----

def test_elimina_protetta_con_produzioni(conn):
    from app.logic.produzioni import registra_produzione
    salva_ricetta(conn, _bigne())
    registra_produzione(conn, {
        "prodotto_id": 3, "data_produzione": "2026-11-16",
        "data_scadenza": "2026-11-19", "qta_prodotta": 60,
        "consumi": [{"origine": "ingresso", "lotto_origine_id": 100, "quantita_usata": 2}],
    })
    with pytest.raises(ErroreRicetta, match="protetta"):
        elimina_ricetta(conn, 3)


def test_elimina_senza_produzioni_pulisce_tutto(conn):
    salva_ricetta(conn, _bigne())
    elimina_ricetta(conn, 3)
    assert dettaglio_ricetta(conn, 3) is None
    righe = conn.execute("SELECT COUNT(*) FROM ricette_righe").fetchone()[0]
    assert righe == 0
    # senza ricetta il prodotto non è più producibile e perde la famiglia
    riga = conn.execute("SELECT famiglia_id FROM prodotti WHERE id = 3").fetchone()
    assert riga["famiglia_id"] is None


# ---- RIFIN 44bis/45: un CANDIDATO abbandonato non intrappola il nome ----

def test_crea_prodotto_lab_candidato_riusato_stesso_id(conn):
    # prima creazione abbandonata (nessuna ricetta mai salvata): riprovare
    # NON da errore: la riga vuota si riusa e si completa, stesso id
    p1 = crea_prodotto_lab(conn, {"nome": "Torta al cioccolato", "sigla": "TC"})
    p2 = crea_prodotto_lab(conn, {"nome": "torta AL CIOCCOLATO", "sigla": "TOR"})
    assert p2["id"] == p1["id"]
    assert p2["sigla"] == "TOR"
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM prodotti "
        "WHERE LOWER(nome) = LOWER('Torta al cioccolato')").fetchone()["n"]
    assert n == 1  # mai due righe per lo stesso nome


def test_crea_prodotto_lab_duplicato_respinto_se_ha_ricetta(conn):
    # il nome E' occupato per davvero (prodotto con ricetta): si respinge
    # e il messaggio dice COS'È e DOVE guardarlo
    p = crea_prodotto_lab(conn, {"nome": "Torta", "unita_misura": "kg"})
    fam = conn.execute("INSERT INTO famiglie (nome) VALUES ('Dolci')").lastrowid
    conn.execute(
        "INSERT INTO ricette (prodotto_id, famiglia_id, resa) VALUES (?, ?, '10 pz')",
        (p["id"], fam))
    with pytest.raises(ErroreRicetta, match="esiste già"):
        crea_prodotto_lab(conn, {"nome": "torta"})
    with pytest.raises(ErroreRicetta, match="card Prodotti"):
        crea_prodotto_lab(conn, {"nome": "torta"})


def test_crea_prodotto_lab_occupato_da_ingrediente(conn):
    # il nome di un ingrediente ACQUISTATO non si prende: anche senza arrivi,
    # la conservazione lo rende un ingrediente vero con la sua scheda
    conn.execute(
        "INSERT INTO prodotti (nome, conservazione, unita_misura) "
        "VALUES ('Latte fresco', 'Frigo', 'lt')")
    with pytest.raises(ErroreRicetta, match="è un ingrediente acquistato"):
        crea_prodotto_lab(conn, {"nome": "latte fresco"})


# ---- RIFIN 51: la dose si scrive come la usa il laboratorio ----

def test_riga_in_grammi_su_liquido_con_densita(conn):
    """La domanda di Nicolas: latte registrato in lt, laboratorio che pesa.
    500 g su una riga in lt: il BACKEND converte col densità e salva in
    CANONICA (0,485 lt): il verbale e lo scarico restano esatti, il libro
    ricette e le tendine mostrano i grammi."""
    r = salva_ricetta(conn, _bigne(righe=[
        {"ingrediente_id": 1, "quantita": 500, "um": "g"},
        {"ingrediente_id": 2, "quantita": 0.5},
    ]))
    riga_latte = [x for x in r["righe"] if x["ingrediente_id"] == 1][0]
    assert abs(riga_latte["quantita"] - 500 / 1.03 / 1000) < 1e-9   # canonica
    assert riga_latte["um_scritta"] == "g"
    # il laboratorio la legge COME L'HAI SCRITTA
    assert abs(riga_latte["dose_qta"] - 500) < 1e-9
    assert riga_latte["dose_um"] == "g"


def test_riga_um_non_ammessa_senza_densita_respinta(conn):
    # le Uova sono in kg SENZA densità: i litri non si possono scrivere.
    # Mai una conversioneImplicita: il messaggio dice COSA correggere
    with pytest.raises(ErroreRicetta, match="non ammette la u.m"):
        salva_ricetta(conn, _bigne(righe=[
            {"ingrediente_id": 1, "quantita": 2},
            {"ingrediente_id": 2, "quantita": 0.5, "um": "lt"},
        ]))


def test_riga_stesso_gruppo_si_converte_e_si_ricorda(conn):
    # 500 ml di latte: 0,5 lt canonici, il ricordo del "ml" resta
    r = salva_ricetta(conn, _bigne(righe=[
        {"ingrediente_id": 1, "quantita": 500, "um": "ml"},
        {"ingrediente_id": 2, "quantita": 0.5},
    ]))
    riga_latte = [x for x in r["righe"] if x["ingrediente_id"] == 1][0]
    assert abs(riga_latte["quantita"] - 0.5) < 1e-9
    assert riga_latte["um_scritta"] == "ml"
    assert abs(riga_latte["dose_qta"] - 500) < 1e-9
