"""Il magazzino si LEGGE, non si scrive: qui si verificano i CALCOLI.

Fixture con date fisse e oggi passato a mano ("2026-11-18"): i numeri non
dipendono dal giorno in cui girano i test.
"""
import pytest

from app import db
from app.logic.magazzino import SOGLIA_AMBRA, SOGLIA_ROSSO, magazzino

OGGI = "2026-11-18"


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.executescript("""
      INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio Valle');

      -- Latte: 3 arrivi, 2 marche in giacenza, lotto 1 ESAURITO
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (1, 'Latte intero', NULL, 'Frigo', 'lt');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (1, 1, 1, 'L2607A', '2026-11-02', '2026-11-23', 10, 0),
               (2, 1, 1, 'L2612B', '2026-11-12', '2026-11-26', 20, 12),
               (3, 1, 1, 'L2612C', '2026-11-12', '2026-11-26', 8, 8);
      UPDATE lotti_ingresso SET marca = 'Centro Latte' WHERE id = 2;
      UPDATE lotti_ingresso SET marca = 'Alpe' WHERE id = 3;

      -- Farina: marca solo ANAGRAFICA (il lotto non ne ha: COALESCE)
      INSERT INTO prodotti (id, nome, famiglia_id, marca, conservazione, unita_misura)
        VALUES (2, 'Farina 00', NULL, 'Molino', 'Magazzino', 'kg');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (4, 2, 1, 'F2610', '2026-11-10', '2027-05-10', 40, 40);

      -- Panna: consumo lento, copertura oltre la soglia
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (3, 'Panna', NULL, 'Freezer', 'lt');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (5, 3, 1, 'P2601', '2026-11-01', '2026-12-01', 5, 2);

      -- Uova: copertura ROSSA (< 3 giorni)
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (4, 'Uova', NULL, 'Frigo', 'pz');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (6, 4, 1, 'U2615', '2026-11-15', '2026-12-05', 60, 15);

      -- Burro: copertura AMBRA (3 <= x < 7)
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (5, 'Burro', NULL, 'Freezer', 'kg');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (7, 5, 1, 'B2608', '2026-11-15', '2026-12-15', 100, 50);

      -- Zucchero: ESENATO (residua 0) ma con consumo storico
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (6, 'Zucchero', NULL, 'Magazzino', 'kg');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (8, 6, 1, 'Z2601', '2026-11-15', '2027-11-15', 30, 0);

      -- Zenzero: primo arrivo IERI, storico di 1 giorno (mai divisione per 0)
      INSERT INTO prodotti (id, nome, famiglia_id, conservazione, unita_misura)
        VALUES (7, 'Zenzero', NULL, 'Magazzino', 'kg');
      INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto,
        data_arrivo, data_scadenza, quantita, quantita_residua)
        VALUES (9, 7, 1, 'Z2617', '2026-11-17', '2027-11-17', 4, 2);

      -- Una produzione in laboratorio che VERBALE i consumi
      INSERT INTO famiglie (id, nome) VALUES (1, 'Creme');
      INSERT INTO prodotti (id, nome, famiglia_id) VALUES (10, 'Crema pasticcera', 1);
      INSERT INTO lotti_interni (id, prodotto_id, famiglia_id, qta_prodotta,
        codice_lotto, data_produzione, data_scadenza)
        VALUES (1, 10, 1, 5, 'CRP-20261116-01', '2026-11-16', '2026-11-19');

      INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata)
        VALUES
          (1, 'ingresso', 1, 10),    -- latte: lotto 1 esaurito
          (1, 'ingresso', 5, 3),     -- panna: 3 dei 5 lt
          (1, 'ingresso', 6, 45),    -- uova: 45 dei 60 pz
          (1, 'ingresso', 7, 50),    -- burro: 50 dei 100 kg
          (1, 'ingresso', 8, 30),    -- zucchero: tutto il lotto
          (1, 'ingresso', 9, 2);     -- zenzero: 2 dei 4 kg
    """)
    c.commit()
    yield c
    c.close()


def stat_di(dati, nome):
    return next(s for s in dati["stat"] if s["nome"] == nome)


def righe_di(dati, nome):
    return [r for r in dati["righe"] if r["nome"] == nome]


# ------------------------- le RIGHE (per marca) -------------------------

def test_righe_multi_marca_lo_stesso_ingrediente(conn):
    dati = magazzino(conn, oggi=OGGI)
    righe = righe_di(dati, "Latte intero")
    marche = sorted(r["marca"] for r in righe)
    assert marche == ["Alpe", "Centro Latte"]
    giacenze = {r["marca"]: r["giacenza"] for r in righe}
    assert giacenze == {"Centro Latte": 12, "Alpe": 8}


def test_marca_del_lotto_o_fallback_anagrafica(conn):
    # il lotto della farina NON dichiara marca: vale quella dell'anagrafica
    dati = magazzino(conn, oggi=OGGI)
    righe = righe_di(dati, "Farina 00")
    assert len(righe) == 1
    assert righe[0]["marca"] == "Molino"
    assert righe_di(dati, "Latte intero")[0]["marca"] != "Molino"


def test_lotto_esaurito_non_e_dietro_le_righe_ma_la_stat_resta(conn):
    # Zucchero: residua 0 non appare tra le giacenze, MA la statistica c'è
    dati = magazzino(conn, oggi=OGGI)
    assert righe_di(dati, "Zucchero") == []
    s = stat_di(dati, "Zucchero")
    assert s["giacenza_tot"] == 0


def test_righe_riportano_um_conservazione_e_n_lotti(conn):
    dati = magazzino(conn, oggi=OGGI)
    r = righe_di(dati, "Latte intero")[0]
    assert r["um"] == "lt"
    assert r["conservazione"] == "Frigo"
    assert r["n_lotti"] == 1   # una riga per marca, per lotti SERVE sommare


# --------------------------- le STAT (per prodotto) ---------------------------

def test_consumo_medio_su_tutto_lo_storico_dal_primo_arrivo(conn):
    # latte: 10 lt consumati dal 2026-11-02 al 2026-11-18 = 16 giorni
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Latte intero")
    assert s["consumo_medio"] == pytest.approx(10 / 16)
    assert s["consumo_medio"] == pytest.approx(0.625)
    assert s["n_arrivi"] == 3


def test_storico_di_un_giorno_mai_divisione_per_zero(conn):
    # zenzero arrivo ieri: giorni = 1, consumo medio = 2 kg/giorno
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Zenzero")
    assert s["consumo_medio"] == pytest.approx(2.0)


def test_copertura_rossa_sotto_i_3_giorni(conn):
    # uova: 15 pz residui / 15 pz al giorno = 1 giorno di copertura
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Uova")
    assert s["copertura"] == 1.0
    assert s["livello"] == "rosso"
    assert s["da_ordinare"] is True
    assert s["copertura"] < SOGLIA_ROSSO


def test_copertura_ambra_fino_a_7_giorni(conn):
    # burro: 50 kg / (50/3 al giorno) = 3 giorni: ambra, non rosso
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Burro")
    assert s["copertura"] == 3.0
    assert s["livello"] == "ambra"
    assert s["da_ordinare"] is True
    assert SOGLIA_ROSSO <= s["copertura"] < SOGLIA_AMBRA


def test_copertura_oltre_la_soglia_non_e_da_ordinare(conn):
    # panna: 2 lt / (3/17 al giorno) ≈ 11.3 giorni
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Panna")
    assert s["copertura"] == 11.3
    assert s["livello"] is None
    assert s["da_ordinare"] is False


def test_senza_consumi_la_copertura_restasospesa(conn):
    # farina: mai consumata, non si sa quanto duri: nessuna copertura
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Farina 00")
    assert s["consumo_medio"] is None
    assert s["copertura"] is None
    assert s["livello"] is None
    assert s["da_ordinare"] is False


def test_esaurito_con_consumo_e_da_ordinare_rosso(conn):
    # zucchero a zero: copertura 0, è IL caso da ordinare per antonomasia
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Zucchero")
    assert s["copertura"] == 0.0
    assert s["livello"] == "rosso"
    assert s["da_ordinare"] is True


def test_cadenza_media_e_prossimo_rifornimento_atteso(conn):
    # 3 arrivi latte in 10 giorni: cadenza 5, prossimo = 12 + 5 = 17/11
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Latte intero")
    assert s["cadenza"] == pytest.approx(5.0)
    assert s["prossimo_atteso"] == "2026-11-17"
    assert s["ultimo_arrivo"] == "2026-11-12"


def test_un_arrivo_solo_senza_cadenza(conn):
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Burro")
    assert s["cadenza"] is None
    assert s["prossimo_atteso"] is None


def test_stat_riporta_um_conservazione_e_giacenza_totale(conn):
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Latte intero")
    assert s["um"] == "lt"
    assert s["conservazione"] == "Frigo"
    assert s["giacenza_tot"] == 20   # 12 + 8, tutte le marche


def test_il_consumo_conta_anche_i_lotti_esauriti(conn):
    # il consumo storico non è solo di chi è ancora in giacenza
    dati = magazzino(conn, oggi=OGGI)
    s = stat_di(dati, "Latte intero")
    assert s["consumo_medio"] == pytest.approx(10 / 16)   # lotto 1 esausto consumato
