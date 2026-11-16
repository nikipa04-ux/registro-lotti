import pytest

from app import db
from app.logic.dashboard import calcola_dashboard
from datetime import date


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    # Scenario: latte in scadenza critica, panna in ambra, uova fuori range
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Fornitore test')")
    c.execute("INSERT INTO prodotti (id, nome) VALUES (1, 'Latte'), (2, 'Panna'), (3, 'Uova'), (4, 'Crema')")
    oggi = date(2026, 11, 16)
    def ingresso(pid, lotto, arrivo, scadenza, residua=5):
        c.execute(
            "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
            "data_arrivo, data_scadenza, quantita, quantita_residua) "
            "VALUES (?, ?, 1, ?, ?, ?, 10, ?)", (pid, pid, lotto, arrivo, scadenza, residua))
    ingresso(1, "LAT-1", "2026-11-10", "2026-11-18")     # entro 7 giorni, critico (2g)
    ingresso(2, "PAN-1", "2026-11-11", "2026-11-21")     # entro 7 giorni, ambra (5g)
    ingresso(3, "UOV-1", "2026-11-11", "2026-12-01")    # oltre 7 giorni: fuori
    c.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (1, 4, 5, 'CRP-20261115-01', "
        "'2026-11-15', '2026-11-19')")
    c.commit()
    yield c
    c.close()


def test_stats_e_scadenze(conn):
    d = calcola_dashboard(conn, oggi=date(2026, 11, 16))
    assert d["stats"]["scadenze_critiche"] == 2          # latte 2g + crema 3g
    assert d["stats"]["arrivi_settimana"] == 3           # tutti arrivi dal 9/11
    assert d["stats"]["produzioni"] == 1
    # In scadenza: latte (2g), crema interna (3g), panna (5g) - ordine per data
    prodotti = [r["prodotto"] for r in d["in_scadenza"]]
    assert prodotti == ["Latte", "Crema", "Panna"]
    assert "Uova" not in prodotti                        # oltre i 7 giorni
    crema = d["in_scadenza"][1]
    assert crema["origine"] == "interno"
    assert crema["fornitore"] == "produzione interna"


def test_dashboard_vuota(conn):
    conn.execute("DELETE FROM consumi"); conn.execute("DELETE FROM lotti_interni")
    conn.execute("DELETE FROM lotti_ingresso"); conn.commit()
    d = calcola_dashboard(conn, oggi=date(2026, 11, 16))
    assert d["stats"]["scadenze_critiche"] == 0
    assert d["in_scadenza"] == []


def test_nessun_lotto_esaurito_in_scadenza(conn):
    # Un lotto esaurito (residua 0) NON deve comparire tra le scadenze
    conn.execute("UPDATE lotti_ingresso SET quantita_residua = 0 WHERE id = 1")
    conn.commit()
    d = calcola_dashboard(conn, oggi=date(2026, 11, 16))
    assert "Latte" not in [r["prodotto"] for r in d["in_scadenza"]]
    assert d["stats"]["scadenze_critiche"] == 1           # resta solo la crema
