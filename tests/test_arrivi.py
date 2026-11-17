import pytest

from app import db
from app.logic.arrivi import ErroreArrivo, elimina_arrivo, registra_arrivo


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio Valle')")
    c.execute("INSERT INTO fornitori (id, nome) VALUES (2, 'Grossista')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (1, 'Creme')")
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, marca, unita_misura) "
        "VALUES (1, 'Latte intero', NULL, 'Mucca Felice', 'lt')"
    )
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, sigla) "
        "VALUES (2, 'Crema pasticcera', 1, 'CRP')"
    )
    c.commit()
    yield c
    c.close()


def arrivo(**extra):
    base = {
        "prodotto_id": 1,
        "fornitore_id": 1,
        "codice_lotto": "L2607A",
        "data_arrivo": "2026-11-16",
        "data_scadenza": "2026-11-23",
        "quantita": 10,
    }
    base.update(extra)
    return base


def test_arrivo_valido_immette_in_magazzino(conn):
    lotto = registra_arrivo(conn, arrivo())
    assert lotto["prodotto"] == "Latte intero"
    assert lotto["fornitore"] == "Caseificio Valle"
    assert lotto["um"] == "lt"
    assert lotto["quantita_residua"] == 10    # residua = quantita: il magazzino parte da qui
    assert lotto["marca"] == "Mucca Felice"   # default dall'anagrafica


def test_marca_del_lotto_vince_sul_default(conn):
    lotto = registra_arrivo(conn, arrivo(marca="Altri Marchi"))
    assert lotto["marca"] == "Altri Marchi"


def test_duplicato_respinto(conn):
    registra_arrivo(conn, arrivo())
    with pytest.raises(ErroreArrivo):
        registra_arrivo(conn, arrivo())               # stesso prodotto+lotto+fornitore
    # stesso lotto ma altro fornitore: valido
    lotto2 = registra_arrivo(conn, arrivo(fornitore_id=2))
    assert lotto2["fornitore"] == "Grossista"


def test_prodotto_di_laboratorio_non_arriva(conn):
    # "famiglia -> ricetta": un semilavorato nasce da una produzione, non da un arrivo
    with pytest.raises(ErroreArrivo, match="laboratorio"):
        registra_arrivo(conn, arrivo(prodotto_id=2))


def test_scadenza_prima_dell_arrivo_respinta(conn):
    with pytest.raises(ErroreArrivo, match="scadenza"):
        registra_arrivo(conn, arrivo(data_arrivo="2026-11-16", data_scadenza="2026-11-15"))


def test_quantita_nulla_o_negativa_respinta(conn):
    for q in (0, -3, None, "abc"):
        with pytest.raises(ErroreArrivo, match="quantità"):
            registra_arrivo(conn, arrivo(quantita=q))


def test_riferimenti_inesistenti_respinti(conn):
    with pytest.raises(ErroreArrivo, match="inesistente"):
        registra_arrivo(conn, arrivo(prodotto_id=99))
    with pytest.raises(ErroreArrivo, match="inesistente"):
        registra_arrivo(conn, arrivo(fornitore_id=99))


def test_codice_lotto_obbligatorio(conn):
    with pytest.raises(ErroreArrivo, match="obbligatorio"):
        registra_arrivo(conn, arrivo(codice_lotto="   "))


def test_nessuna_scrittura_parziale_su_errore(conn):
    # un arrivo respinto NON lascia righe nel database
    with pytest.raises(ErroreArrivo):
        registra_arrivo(conn, arrivo(quantita=0))
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 0


# ---- elimina_arrivo (eliminazione protetta) ----

def test_elimina_arrivo_senza_consumi_rimuove_il_lotto(conn):
    lotto = registra_arrivo(conn, arrivo())
    elimina_arrivo(conn, lotto["id"])
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 0


def test_elimina_arrivo_protetta_se_consumato(conn):
    from app.logic.produzioni import registra_produzione
    # una ricetta minima per consumare il latte del lotto
    conn.execute(
        "INSERT INTO ricette (id, prodotto_id, famiglia_id) VALUES (10, 1, 1)"
    )
    conn.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (10, 2, 1)"
    )
    conn.commit()
    lotto = registra_arrivo(conn, arrivo())
    registra_produzione(conn, {
        "prodotto_id": 1,
        "data_produzione": "2026-11-16",
        "data_scadenza": "2026-11-23",
        "qta_prodotta": 1,
        "consumi": [
            {"origine": "ingresso", "lotto_origine_id": lotto["id"], "quantita_usata": 2},
        ],
    })
    with pytest.raises(ErroreArrivo, match="protetta"):
        elimina_arrivo(conn, lotto["id"])
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 1  # il lotto resta: la tracciabilità non si riscrive
