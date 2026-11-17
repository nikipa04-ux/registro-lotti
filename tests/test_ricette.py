import pytest

from app import db
from app.logic.produzioni import ErroreProduzione, proponi_produzione
from app.logic.ricette import (
    ErroreRicetta,
    candidati,
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
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, marca, unita_misura) "
        "VALUES (1, 'Latte intero', NULL, 'Mucca', 'lt')"
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
    crea_prodotto_lab(conn, {"nome": "Torta", "unita_misura": "kg"})
    with pytest.raises(ErroreRicetta, match="esiste già"):
        crea_prodotto_lab(conn, {"nome": "torta", "unita_misura": "kg"})


def test_crea_prodotto_lab_um_obbligatoria(conn):
    with pytest.raises(ErroreRicetta, match="Unità di misura"):
        crea_prodotto_lab(conn, {"nome": "Torta", "unita_misura": ""})


# ---- candidati ----

def test_candidati_escludono_ricettati_e_acquistati(conn):
    salva_ricetta(conn, _bigne(famiglia_id=2))
    nomi = [p["nome"] for p in candidati(conn)]
    assert nomi == ["Uova pastorizzate"]   # no Bignè (ricettato), no Latte (arrivi)


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
