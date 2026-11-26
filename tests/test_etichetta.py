import pytest

from app import db
from app.logic.etichetta import etichetta, ingredienti_lotto


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    # Scenario guida del prototipo: latte/uova/zucchero -> crema -> bignè
    for pid, nome, sigla in [(1, "Latte fresco", "LAT"), (2, "Uova", "UOV"),
                             (3, "Zucchero", "ZUC"), (4, "Crema pasticcera", "CRP"),
                             (5, "Bignè", "BIG")]:
        c.execute("INSERT INTO prodotti (id, nome, sigla) VALUES (?, ?, ?)", (pid, nome, sigla))
    # Il fornitore referenziato dagli arrivi deve esistere
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Fornitore test')")
    # Arrivi: 1 = latte, 2 = uova, 3 = zucchero
    for aid, pid in [(1, 1), (2, 2), (3, 3)]:
        c.execute(
            "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
            "data_arrivo, data_scadenza, quantita, quantita_residua) "
            "VALUES (?, ?, 1, 'L1', '2026-11-01', '2026-12-01', 10, 10)", (aid, pid))
    # Allergeni: latte e uova dichiarati, zucchero no
    c.execute("INSERT INTO allergeni (id, nome) VALUES (1, 'Latte'), (2, 'Uova')")
    c.execute("INSERT INTO prodotti_allergeni VALUES (1, 1), (2, 2)")
    # Produzione 1: crema (qta_prodotta 5 kg) con latte 4, uova 2, zucchero 1.5
    c.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (1, 4, 5, 'CRP-20261113-01', "
        "'2026-11-13', '2026-11-16')")
    for from_id, qta in [(1, 4), (2, 2), (3, 1.5)]:
        c.execute("INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
                  "VALUES (1, 'ingresso', ?, ?)", (from_id, qta))
    # Produzione 2: bignè che consuma 3 kg di crema + 0.5 kg di uova DIRETTE
    c.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (2, 5, 60, 'BIG-20261113-01', "
        "'2026-11-13', '2026-11-20')")
    c.execute("INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
              "VALUES (2, 'interno', 1, 3), (2, 'ingresso', 2, 0.5)")
    c.commit()
    yield c
    c.close()


def test_etichetta_crema(conn):
    r = etichetta(conn, 1)
    nomi = [riga["denominazione"] for riga in r["righe"]]
    assert nomi == ["Latte fresco", "Uova", "Zucchero"]  # ordine decrescente di qta
    assert r["allergeni"] == ["Latte", "Uova"]


def test_fusione_uova_una_riga_sola(conn):
    # Le uova DENTRO la crema (2 * 3/5 = 1.2) + le DIRETTE (0.5) = 1.7, UNA riga
    acc = ingredienti_lotto(conn, 2)
    assert acc[2] == pytest.approx(1.7)
    r = etichetta(conn, 2)
    nomi = [riga["denominazione"] for riga in r["righe"]]
    assert nomi.count("Uova") == 1
    # Ordine: latte 4*0.6=2.4 > uova 1.7 > zucchero 1.5*0.6=0.9
    assert nomi == ["Latte fresco", "Uova", "Zucchero"]


def test_allergeni_doppia_fonte_una_volta_sola(conn):
    # le uova arrivano DIRETTE e DENTRO la crema: si sommano le fonti
    # ma in "Contiene (allergeni)" compare UNA volta sola
    r = etichetta(conn, 2)
    assert r["allergeni"] == ["Latte", "Uova"]
    assert r["allergeni"].count("Uova") == 1


def test_fallback_qta_prodotta_nulla_usa_la_resa(conn):
    # Se la produzione non ha dichiarato qta_prodotta, si scala sulla resa
    # della ricetta (stesso comportamento del prototipo)
    conn.execute("UPDATE lotti_interni SET qta_prodotta = NULL WHERE id = 1")
    conn.execute("INSERT INTO ricette (id, prodotto_id, resa) VALUES (1, 4, '5 kg')")
    conn.commit()
    acc = ingredienti_lotto(conn, 2)
    assert acc[2] == pytest.approx(1.7)  # identico: 5 kg == resa 5 kg


# ---- RIFIN 44: ingredienti COMPOSTI (denominazione = parti) ----

def _produzione_con_cioccolato(conn, denominazione, qta_cioccolato=2.0):
    """Lungo interno 3 che usa 2 kg di cioccolato (composto) + 3 kg di
    zucchero DIRETTO: il caso guida del dopppione 'zucchero'."""
    conn.execute(
        "INSERT INTO prodotti (id, nome, sigla, denominazione_legale) "
        "VALUES (6, 'Cioccolato fondente', 'CIO', ?)", (denominazione,))
    conn.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (4, 6, 1, 'L4', '2026-11-01', '2027-05-01', 10, 10)")
    conn.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (3, 5, 60, 'BIG-20261122-01', "
        "'2026-11-22', '2026-11-29')")
    conn.execute(
        "INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
        "VALUES (3, 'ingresso', 4, ?), (3, 'ingresso', 3, 3)", (qta_cioccolato,))
    conn.commit()


def test_composto_splittato_in_parti_appiattite(conn):
    # denominazione del cioccolato = SOLO le parti separate da virgola:
    # in etichetta una riga per parte, il nome del composto sparisce
    # (le parti restano scritte come le ha digitate chi crea l'ingrediente)
    _produzione_con_cioccolato(conn, "Zucchero, Pasta di cacao, Burro di cacao")
    r = etichetta(conn, 3)
    nomi = [riga["denominazione"] for riga in r["righe"]]
    # lo zucchero DIRETTO (3 kg) pesa piu' del cioccolato (2 kg): la sua
    # riga resta; la parte 'zucchero' del composto deduplica via
    assert nomi == ["Zucchero", "Pasta di cacao", "Burro di cacao"]
    assert "Cioccolato fondente" not in nomi
    # le parti ereditano il peso del composto: contano solo per l'ordine
    assert r["righe"][1]["qta"] == pytest.approx(2.0)


def test_composto_dedup_senza_maiuscole_e_allergeni_comunque_dichiarati(conn):
    # due composti che dichiarano le STESSE parti (maiuscole diverse):
    # le righe compaiono UNA volta sola, MA gli allergeni del composto
    # deduplicato sono comunque entrati nel prodotto finito
    conn.execute(
        "INSERT INTO prodotti (id, nome, sigla, denominazione_legale) "
        "VALUES (6, 'Cioccolato fondente', 'CIO', 'zucchero, cacao')")
    conn.execute(
        "INSERT INTO prodotti (id, nome, sigla, denominazione_legale) "
        "VALUES (7, 'Copertura al cacao', 'CDC', 'Zucchero, Cacao')")
    conn.execute(
        "INSERT INTO prodotti_allergeni VALUES (7, 1)")  # dichiara LATTE
    for aid, pid in [(4, 6), (5, 7)]:
        conn.execute(
            "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
            "data_arrivo, data_scadenza, quantita, quantita_residua) "
            "VALUES (?, ?, 1, 'L', '2026-11-01', '2027-05-01', 10, 10)", (aid, pid))
    conn.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (3, 5, 60, 'BIG-20261122-02', "
        "'2026-11-22', '2026-11-29')")
    conn.execute(
        "INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
        "VALUES (3, 'ingresso', 4, 2), (3, 'ingresso', 5, 1)")
    conn.commit()
    r = etichetta(conn, 3)
    nomi = [riga["denominazione"] for riga in r["righe"]]
    # il primo composto (2 kg) scrive le parti; il secondo (1 kg) e'
    # TUTTO doppione: via. L'allergene LATTE della copertura resta
    assert nomi == ["zucchero", "cacao"]
    assert r["allergeni"] == ["Latte"]
