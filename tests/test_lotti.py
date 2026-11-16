import pytest

from app import db
from app.logic.lotti import genera_codice


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    # Il lotto interno referenzia il prodotto: l'anagrafica deve esistere
    c.execute("INSERT INTO prodotti (id, nome, sigla) VALUES (1, 'Crema pasticcera', 'CRP')")
    yield c
    c.close()


def test_formato_sigla_data_progressivo(conn):
    p = {"id": 1, "nome": "Crema pasticcera", "sigla": "CRP"}
    assert genera_codice(conn, p, "2026-11-13") == "CRP-20261113-01"


def test_progressivo_per_giorno_e_prodotto(conn):
    p = {"id": 1, "nome": "Crema pasticcera", "sigla": "CRP"}
    conn.execute(
        "INSERT INTO lotti_interni (prodotto_id, codice_lotto, data_produzione, data_scadenza) "
        "VALUES (1, 'CRP-20261113-01', '2026-11-13', '2026-11-16')")
    # Secondo lotto dello stesso prodotto nello stesso giorno
    assert genera_codice(conn, p, "2026-11-13") == "CRP-20261113-02"
    # Altro giorno ricomincia da 01
    assert genera_codice(conn, p, "2026-11-14") == "CRP-20261114-01"


def test_sigla_fallback_dal_nome(conn):
    p = {"id": 1, "nome": "Bignè", "sigla": None}
    assert genera_codice(conn, p, "2026-11-13").startswith("BIG-20261113-")
