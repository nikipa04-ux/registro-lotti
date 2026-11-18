"""Le scadenze sono un CALCOLO sulla finestra scelta, come il magazzino.

Fixture con date fisse e oggi passato a mano ("2026-11-18"): la finestra
predefinita è 7 giorni, gli scaduti si vedono SOLO col filtro "scad"
(scelta di Nicolas, 18/11/2026 notte).
"""
import pytest

from app import db
from app.logic.magazzino import ErroreMagazzino, lista_scadenze

OGGI = "2026-11-18"


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.executescript("""
      INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio Valle');

      INSERT INTO prodotti (id, nome, famiglia_id, marca, conservazione, unita_misura)
        VALUES (1, 'Latte intero', NULL, 'Val Tiberina', 'Frigo', 'lt');
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (2, 'Farina 00', NULL, 'Magazzino', 'kg');

      INSERT INTO famiglie (id, nome) VALUES (1, 'Creme');
      INSERT INTO prodotti (id, nome, famiglia_id, unita_misura)
        VALUES (3, 'Crema pasticcera', 1, 'kg');

      -- Lotti in ingresso: scaduto con giacenza, rosso <3, ambra, esaurito,
      -- a 7 giorni esatti, oltre 7 ma entro 30, oltre 30, scaduto esausto
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, marca, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES
          (1, 1, 1, 'Centro Latte', 'L2616A', '2026-11-05', '2026-11-16', 10, 2),
          (2, 1, 1, NULL,          'L2620B', '2026-11-10', '2026-11-20', 20, 12),
          (3, 1, 1, NULL,          'L2621C', '2026-11-12', '2026-11-21', 30, 0),
          (4, 2, 1, NULL,          'F2625',  '2026-11-02', '2026-11-25', 40, 40),
          (5, 2, 1, NULL,          'F1215',  '2026-11-01', '2026-12-15', 25, 25),
          (6, 2, 1, NULL,          'F2705',  '2026-11-01', '2027-05-01', 10, 10),
          (7, 1, 1, NULL,          'L2615D', '2026-11-01', '2026-11-15', 5, 0);

      -- Lotti interni: domani, tra 10 giorni, scaduto
      INSERT INTO lotti_interni (id, prodotto_id, famiglia_id, qta_prodotta,
        um_prodotta, codice_lotto, data_produzione, data_scadenza)
        VALUES
          (1, 3, 1, 5, NULL,     'CRP-20261116-01', '2026-11-16', '2026-11-19'),
          (2, 3, 1, 3, 'teglie', 'CRP-20261108-02', '2026-11-08', '2026-11-28'),
          (3, 3, 1, 2, NULL,     'CRP-20261106-03', '2026-11-06', '2026-11-10');
    """)
    c.commit()
    yield c
    c.close()


def lotti(dati, tipo):
    return [r for r in dati if r["tipo"] == tipo]


def codici(dati):
    return [r["lotto"] for r in dati]


# --------------------------- le finestre ---------------------------

def test_finestra_default_7_giorni(conn):
    # 19 (1 giorno), 20 (2) e 25-11 (7 giorni esatti): dentro. Il resto no:
    # L2621C è esausto, L2616A è scaduto, F1215/F2705 oltre la finestra
    dati = lista_scadenze(conn, oggi=OGGI)
    assert codici(dati) == ["CRP-20261116-01", "L2620B", "F2625"]


def test_finestra_3_giorni(conn):
    dati = lista_scadenze(conn, "3", oggi=OGGI)
    assert codici(lotti(dati, "ingresso")) == ["L2620B"]
    assert codici(lotti(dati, "interno")) == ["CRP-20261116-01"]


def test_finestra_30_giorni(conn):
    dati = lista_scadenze(conn, "30", oggi=OGGI)
    assert "F1215" in codici(dati)        # 27 giorni: entra
    assert "F2705" not in codici(dati)    # oltre 30: no
    assert "CRP-20261108-02" in codici(dati)   # interno a 10 giorni


def test_finestra_all_tutto_compreso_di_scaduti(conn):
    dati = lista_scadenze(conn, "all", oggi=OGGI)
    assert len(dati) == 8
    assert "L2616A" in codici(dati)       # scaduto con giacenza
    assert "L2615D" not in codici(dati)   # scaduto ESAURITO mai
    assert "CRP-20261106-03" in codici(dati)   # interno scaduto


def test_filtro_scaduti_solo_con_giacenza(conn):
    dati = lista_scadenze(conn, "scad", oggi=OGGI)
    assert codici(dati) == ["CRP-20261106-03", "L2616A"]
    assert all(r["giorni"] < 0 for r in dati)


def test_nessun_lotto_esaurito_in_nessuna_finestra(conn):
    for finestra in ("3", "7", "30", "all", "scad"):
        dati = lista_scadenze(conn, finestra, oggi=OGGI)
        residui = [r["lotto"] for r in lotti(dati, "ingresso")]
        assert "L2621C" not in residui and "L2615D" not in residui


# ----------------------- i dati di ogni riga -----------------------

def test_ordine_per_urgenza(conn):
    dati = lista_scadenze(conn, "all", oggi=OGGI)
    scadenze = [r["scadenza"] for r in dati]
    assert scadenze == sorted(scadenze)


def test_giorni_positivi_e_negativi(conn):
    dati = lista_scadenze(conn, "all", oggi=OGGI)
    per_lotto = {r["lotto"]: r["giorni"] for r in dati}
    assert per_lotto["L2616A"] == -2      # scaduto da 2 giorni
    assert per_lotto["F2625"] == 7        # 7 giorni esatti
    assert per_lotto["CRP-20261116-01"] == 1


def test_marca_del_lotto_o_fallback_anagrafica(conn):
    dati = lista_scadenze(conn, "all", oggi=OGGI)
    per_lotto = {r["lotto"]: r["marca"] for r in lotti(dati, "ingresso")}
    assert per_lotto["L2616A"] == "Centro Latte"      # la marca del LOTTO vince
    assert per_lotto["L2620B"] == "Val Tiberina"      # NULL: quella dell'anagrafica


def test_interni_um_dello_snapshot_o_del_prodotto(conn):
    dati = lista_scadenze(conn, "all", oggi=OGGI)
    per_lotto = {r["lotto"]: r["um"] for r in lotti(dati, "interno")}
    assert per_lotto["CRP-20261116-01"] == "kg"       # snapshot nullo: um del prodotto
    assert per_lotto["CRP-20261108-02"] == "teglie"   # snapshot: vince la teglia


def test_interni_senza_marca_fornitore_niente_conservazione(conn):
    dati = lista_scadenze(conn, "all", oggi=OGGI)
    r = next(x for x in lotti(dati, "interno") if x["lotto"] == "CRP-20261108-02")
    assert r["marca"] is None and r["fornitore"] is None
    assert r["conservazione"] is None
    assert r["quantita"] == 3


def test_origine_e_qta_residua(conn):
    dati = lista_scadenze(conn, oggi=OGGI)
    ing = next(r for r in dati if r["lotto"] == "L2620B")
    assert ing["fornitore"] == "Caseificio Valle"
    assert ing["quantita"] == 12 and ing["um"] == "lt"
    assert ing["prodotto"] == "Latte intero"
    assert ing["conservazione"] == "Frigo"
    assert ing["id"] == 2                # per il click che apre il dettaglio


# --------------------------- input respinti ---------------------------

def test_finestra_sconosciuta_respinta(conn):
    with pytest.raises(ErroreMagazzino):
        lista_scadenze(conn, "14", oggi=OGGI)
    with pytest.raises(ErroreMagazzino):
        lista_scadenze(conn, 7, oggi=OGGI)   # serve la STRINGA "7", come il selettore
