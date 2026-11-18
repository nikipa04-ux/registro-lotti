import pytest

from app import db
from app.logic.etichetta import ingredienti_lotto
from app.logic.produzioni import (
    ErroreProduzione,
    elimina_produzione,
    lotti_disponibili,
    proponi_produzione,
    registra_produzione,
)


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (1, 'Creme')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (2, 'Dolci finiti')")
    # ingredienti acquistati (famiglia_id NULL)
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, marca, unita_misura) "
        "VALUES (1, 'Latte intero', NULL, 'Mucca', 'lt')"
    )
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, marca, unita_misura) "
        "VALUES (2, 'Uova', NULL, 'Gallina', 'pz')"
    )
    # semilavorato con ricetta (famiglia via RICETTA, sigla per il codice lotto)
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, sigla, unita_misura) "
        "VALUES (3, 'Crema pasticcera', NULL, 'CRP', 'kg')"
    )
    # prodotto finito: la crema è suo ingrediente (ricorsività)
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, sigla, unita_misura) "
        "VALUES (4, 'Bignè', NULL, 'BGN', 'pz')"
    )
    # ricetta master della crema: 2 lt di latte
    c.execute(
        "INSERT INTO ricette (id, prodotto_id, famiglia_id, resa) VALUES (10, 3, 1, '2 kg')"
    )
    c.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (10, 1, 2)"
    )
    # ricetta del bignè: 1 kg di crema + 3 uova
    c.execute(
        "INSERT INTO ricette (id, prodotto_id, famiglia_id, resa) VALUES (11, 4, 2, '60 pz')"
    )
    c.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (11, 3, 1)"
    )
    c.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (11, 2, 3)"
    )
    # due lotti di latte con scadenze diverse: FEFO parte dal più vecchio
    c.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (100, 1, 1, 'LAT-A', '2026-11-10', '2026-11-20', 1.5, 1.5)"
    )
    c.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (101, 1, 1, 'LAT-B', '2026-11-12', '2026-11-25', 5, 5)"
    )
    # uova per il bignè
    c.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (102, 2, 1, 'UOV-A', '2026-11-10', '2026-12-01', 10, 10)"
    )
    c.commit()
    yield c
    c.close()


OGGI = "2026-11-16"


# ---- lotti_disponibili / proposta FEFO ----

def test_proposta_fefo_ordine_e_split(conn):
    lotti = lotti_disponibili(conn, 1, oggi=OGGI)
    assert [l["codice_lotto"] for l in lotti] == ["LAT-A", "LAT-B"]

    prop = proponi_produzione(conn, 3, oggi=OGGI)
    # la ricetta chiede 2 lt: 1.5 dal lotto A e 0.5 dal B
    riga = prop["righe"][0]
    assert riga["mancante"] == 0
    assert [(p["codice_lotto"], p["quantita"]) for p in riga["proposta"]] == [
        ("LAT-A", 1.5), ("LAT-B", 0.5),
    ]
    assert prop["ricetta"]["famiglia"] == "Creme"


def test_proposta_righe_mostrano_la_famiglia_non_tag_semilavorato(conn):
    # il bignè consuma crema (prodotto di laboratorio) + uova (acquistato):
    # la riga della crema porta la sua FAMIGLIA (dalla sua ricetta), il
    # latte/acquistato non ne porta. Mai un flag "semilaborato".
    prop = proponi_produzione(conn, 4, oggi=OGGI)
    assert "semilaborato" not in prop["righe"][0]
    assert prop["righe"][0]["famiglia"] == "Creme"   # la crema
    assert prop["righe"][1]["famiglia"] is None      # le uova


def test_proposta_mancante_quando_giacenza_insufficiente(conn):
    prop = proponi_produzione(conn, 4, oggi=OGGI)
    # la ricetta del bignè chiede 1 kg di crema: non ce n'è
    riga_crema = prop["righe"][0]
    assert riga_crema["mancante"] == 1
    assert riga_crema["lotti"] == []


def test_proposta_rifiuta_ingrediente_acquistato(conn):
    with pytest.raises(ErroreProduzione, match="acquistato"):
        proponi_produzione(conn, 1, oggi=OGGI)


def test_proposta_rifiuta_prodotto_senza_ricetta(conn):
    c = conn.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, sigla) "
        "VALUES (9, 'Torta', 2, 'TOR')"
    )
    conn.commit()
    with pytest.raises(ErroreProduzione, match="ricetta"):
        proponi_produzione(conn, 9, oggi=OGGI)


# ---- registra_produzione ----

def produzione_crema(**extra):
    base = {
        "prodotto_id": 3,
        "data_produzione": OGGI,
        "data_scadenza": "2026-11-20",
        "qta_prodotta": 2,
        "consumi": [
            {"origine": "ingresso", "lotto_origine_id": 100, "quantita_usata": 1.5},
            {"origine": "ingresso", "lotto_origine_id": 101, "quantita_usata": 0.5},
        ],
    }
    base.update(extra)
    return base


def test_registra_valida_codice_scarico_e_consumi(conn):
    lotto = registra_produzione(conn, produzione_crema())
    assert lotto["codice_lotto"] == "CRP-20261116-01"
    # snapshot della famiglia dalla RICETTA (il prodotto non ce l'ha)
    assert lotto["famiglia_id"] == 1
    # scarico della residua: 1.5 e 0.5
    residui = dict(conn.execute(
        "SELECT codice_lotto, quantita_residua FROM lotti_ingresso WHERE id IN (100, 101)"
    ).fetchall())
    assert residui == {"LAT-A": 0.0, "LAT-B": 4.5}
    n = conn.execute("SELECT COUNT(*) FROM consumi").fetchone()[0]
    assert n == 2


def test_secondo_lotto_stesso_giorno_progressivo(conn):
    registra_produzione(conn, produzione_crema())
    lotto2 = registra_produzione(conn, produzione_crema(
        consumi=[{"origine": "ingresso", "lotto_origine_id": 101, "quantita_usata": 2}],
    ))
    assert lotto2["codice_lotto"] == "CRP-20261116-02"


def test_giacenza_insufficiente_respinta(conn):
    prima = dict(conn.execute(
        "SELECT quantita_residua FROM lotti_ingresso WHERE id = 100"
    ).fetchone())
    with pytest.raises(ErroreProduzione, match="insufficiente"):
        registra_produzione(conn, produzione_crema(
            consumi=[{"origine": "ingresso", "lotto_origine_id": 100,
                      "quantita_usata": 99}],
        ))
    dopo = dict(conn.execute(
        "SELECT quantita_residua FROM lotti_ingresso WHERE id = 100"
    ).fetchone())
    assert prima == dopo   # rollback: nessuno scarico parziale


def test_scadenza_prima_della_produzione_respinta(conn):
    with pytest.raises(ErroreProduzione, match="scadenza non può precedere"):
        registra_produzione(conn, produzione_crema(data_scadenza="2026-11-15"))


def test_ingrediente_acquistato_respinto(conn):
    with pytest.raises(ErroreProduzione, match="acquistato"):
        registra_produzione(conn, produzione_crema(prodotto_id=1))


def test_consumi_vuoti_respinti(conn):
    with pytest.raises(ErroreProduzione, match="verbale"):
        registra_produzione(conn, produzione_crema(consumi=[]))


def test_lotto_duplicato_respinto(conn):
    with pytest.raises(ErroreProduzione, match="due volte"):
        registra_produzione(conn, produzione_crema(consumi=[
            {"origine": "ingresso", "lotto_origine_id": 100, "quantita_usata": 1},
            {"origine": "ingresso", "lotto_origine_id": 100, "quantita_usata": 0.5},
        ]))


def test_origine_non_valida_respinta(conn):
    with pytest.raises(ErroreProduzione, match="Origine"):
        registra_produzione(conn, produzione_crema(consumi=[
            {"origine": "magazzino", "lotto_origine_id": 100, "quantita_usata": 1},
        ]))


def test_quantita_zero_respinta(conn):
    with pytest.raises(ErroreProduzione, match="maggiori di zero"):
        registra_produzione(conn, produzione_crema(consumi=[
            {"origine": "ingresso", "lotto_origine_id": 100, "quantita_usata": 0},
        ]))


def test_qta_prodotta_non_valida_respinta(conn):
    with pytest.raises(ErroreProduzione, match="maggiore di zero"):
        registra_produzione(conn, produzione_crema(qta_prodotta=-3))


# ---- ricorsività: semilavorato consumato, etichetta e qta_prodotta ----

def test_etichetta_ricorsiva_con_fusione_e_fattore(conn):
    # crema: 2 kg prodotti consumando 1.5 lt LAT-A (latte) + 0.5 lt LAT-B
    crema = registra_produzione(conn, produzione_crema())
    # bignè: 6 pz prodotti consumando 1 kg di crema interna + 3 uova
    bigne = registra_produzione(conn, {
        "prodotto_id": 4,
        "data_produzione": OGGI,
        "data_scadenza": "2026-11-19",
        "qta_prodotta": 6,
        "consumi": [
            {"origine": "interno", "lotto_origine_id": crema["id"], "quantita_usata": 1},
            {"origine": "ingresso", "lotto_origine_id": 102, "quantita_usata": 3},
        ],
    })
    assert bigne["codice_lotto"] == "BGN-20261116-01"
    # il fattore: 1 kg di crema su 2 kg prodotti -> metà dei suoi ingredienti
    ing = ingredienti_lotto(conn, bigne["id"])
    assert ing == {1: 1.0, 2: 3.0}   # latte 1.0 lt fuso, uova 3 pz


def test_disponibilita_semilavorato_usa_qta_prodotta(conn):
    crema = registra_produzione(conn, produzione_crema())
    lotti = lotti_disponibili(conn, 3, oggi=OGGI)
    # v0.1: il lotto interno vale la sua qta_prodotta (nessuna tracciatura residua)
    assert [(l["origine"], l["quantita_residua"]) for l in lotti] == [("interno", 2.0)]


# ---- elimina_produzione (eliminazione protetta) ----

def test_elimina_produzione_ripristina_le_giacenze(conn):
    lotto = registra_produzione(conn, produzione_crema())
    elimina_produzione(conn, lotto["id"])
    # il verbale si annulla e le giacenze tornano come prima dello scarico
    residui = dict(conn.execute(
        "SELECT codice_lotto, quantita_residua FROM lotti_ingresso WHERE id IN (100, 101)"
    ).fetchall())
    assert residui == {"LAT-A": 1.5, "LAT-B": 5.0}
    assert conn.execute("SELECT COUNT(*) FROM consumi").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM lotti_interni").fetchone()[0] == 0


def test_elimina_produzione_protetta_se_usata_da_altra_produzione(conn):
    crema = registra_produzione(conn, produzione_crema())
    bigne = registra_produzione(conn, {
        "prodotto_id": 4,
        "data_produzione": OGGI,
        "data_scadenza": "2026-11-19",
        "qta_prodotta": 60,
        "consumi": [
            {"origine": "interno", "lotto_origine_id": crema["id"], "quantita_usata": 1},
            {"origine": "ingresso", "lotto_origine_id": 102, "quantita_usata": 3},
        ],
    })
    with pytest.raises(ErroreProduzione, match="protetta"):
        elimina_produzione(conn, crema["id"])   # il bignè la consuma: resta
    # il bignè invece non è usato da nessuno: si elimina e ripristina
    elimina_produzione(conn, bigne["id"])
    residui = dict(conn.execute(
        "SELECT codice_lotto, quantita_residua FROM lotti_ingresso WHERE id = 102"
    ).fetchall())
    assert residui == {"UOV-A": 10.0}
    n = conn.execute("SELECT COUNT(*) FROM lotti_interni").fetchone()[0]
    assert n == 1  # solo la crema


# ---- ricetta modificata: snapshot al momento del verbale ----

def test_produzione_che_segue_la_ricetta_non_e_marcata(conn):
    lotto = registra_produzione(conn, produzione_crema())
    assert lotto["ricetta_modificata"] == 0


def test_ingrediente_aggiunto_fuori_ricetta_marca_il_lotto(conn):
    lotto = registra_produzione(conn, produzione_crema(
        consumi=[
            {"origine": "ingresso", "lotto_origine_id": 100, "quantita_usata": 1.5},
            {"origine": "ingresso", "lotto_origine_id": 101, "quantita_usata": 0.5},
            # "UOV-A": le uova NON sono negli ingredienti della crema
            {"origine": "ingresso", "lotto_origine_id": 102, "quantita_usata": 1},
        ],
    ))
    assert lotto["ricetta_modificata"] == 1


def test_riga_di_ricetta_esclusa_marca_il_lotto(conn):
    # il bignè (ricetta: crema + uova) prodotto consumando SOLO la crema
    crema = registra_produzione(conn, produzione_crema())
    bigne = registra_produzione(conn, {
        "prodotto_id": 4,
        "data_produzione": OGGI,
        "data_scadenza": "2026-11-24",
        "qta_prodotta": 40,
        "consumi": [
            {"origine": "interno", "lotto_origine_id": crema["id"], "quantita_usata": 1},
        ],
    })
    assert bigne["ricetta_modificata"] == 1


def test_migrazione_colonna_idempotente_sui_db_nati_prima():
    c = db.connessione(":memory:")
    c.execute("CREATE TABLE prova (id INTEGER)")
    db.garantisci_colonna(c, "prova", "extra", "INTEGER NOT NULL DEFAULT 0")
    db.garantisci_colonna(c, "prova", "extra", "INTEGER NOT NULL DEFAULT 0")
    c.execute("INSERT INTO prova (id, extra) VALUES (1, 1)")
    assert c.execute("SELECT extra FROM prova").fetchone()["extra"] == 1
    c.close()


# ---- u.m. della quantità prodotta: SNAPSHOT um_prodotta ----

def test_um_prodotta_diversa_da_canonica_si_salva(conn):
    # il bignè è in pz, ma oggi si fanno 6 teglie: tipi diversi non si
    # convertono, il lotto registra la verità dell'operatore
    crema = registra_produzione(conn, produzione_crema())
    bigne = registra_produzione(conn, {
        "prodotto_id": 4,
        "data_produzione": OGGI,
        "data_scadenza": "2026-11-24",
        "qta_prodotta": 6,
        "um_prodotta": "teglie",
        "consumi": [
            {"origine": "interno", "lotto_origine_id": crema["id"], "quantita_usata": 1},
        ],
    })
    assert bigne["um_prodotta"] == "teglie"


def test_um_prodotta_convertibile_e_rifiutata(conn):
    # 'g' per un prodotto in kg: stesso tipo, quindi la conversione spetta
    # a CHI CHIAMA (la UI lo fa): l'API non converte di nascosto
    with pytest.raises(ErroreProduzione, match="CONVERTITA"):
        registra_produzione(conn, produzione_crema(
            qta_prodotta=2000, um_prodotta="g",
        ))


def test_um_prodotta_come_la_canonica_resta_null(conn):
    lotto = registra_produzione(conn, produzione_crema(um_prodotta="kg"))
    assert lotto["um_prodotta"] is None   # nessuna snapshot inutile


def test_um_prodotta_vuota_resta_null(conn):
    lotto = registra_produzione(conn, produzione_crema(um_prodotta="  "))
    assert lotto["um_prodotta"] is None


def test_lotto_in_um_diversa_non_e_proposto_dalla_fefo(conn):
    # la crema è in kg, ma oggi se ne fanno 4 vassoi (u.m. non convertibile):
    # il lotto resta valido per tracciabilità, la FEFO però NON lo propone
    # come giacenza per chi la consuma (4 vassoi non sono 4 kg)
    vassoi = registra_produzione(conn, produzione_crema(
        qta_prodotta=4, um_prodotta="vassoi",
        consumi=[{"origine": "ingresso", "lotto_origine_id": 101, "quantita_usata": 1.5}],
    ))
    assert lotti_disponibili(conn, 3, oggi=OGGI) == []
    # il lotto canonico invece sì: la FEFO non cambia per lui
    lotto = registra_produzione(conn, produzione_crema(
        consumi=[{"origine": "ingresso", "lotto_origine_id": 101, "quantita_usata": 1.5}],
    ))
    lotti = lotti_disponibili(conn, 3, oggi=OGGI)
    assert [l["id"] for l in lotti] == [lotto["id"]]
    assert vassoi["um_prodotta"] == "vassoi"
