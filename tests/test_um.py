import pytest

from app import db
from app.logic.um import (
    converti,
    densita_suggerita,
    fattore,
    fattore_liquido,
    gruppo_di,
)


def test_stessa_um():
    assert fattore("kg", "kg") == 1.0


def test_massa_g_kg():
    assert fattore("g", "kg") == 1 / 1000
    assert converti(1500, "g", "kg") == 1.5


def test_massa_kg_g():
    assert converti(1.5, "kg", "g") == 1500


def test_volume_ml_lt():
    assert converti(500, "ml", "lt") == 0.5


def test_tipi_diversi_vietato():
    # REGOLA DI PROGETTO: mai conversione implicita fra tipi diversi
    assert fattore("kg", "lt") is None
    assert fattore("pz", "kg") is None


def test_um_libere_non_si_convertono():
    assert gruppo_di("pz") is None
    assert fattore("teglia", "vasetti") is None


def test_conversione_vietata_solleva():
    with pytest.raises(ValueError):
        converti(60, "pz", "kg")


# ---- RIFIN 51: il ponte peso<->volume, SOLO con densità dichiarata ----

def test_ponte_g_lt_con_densita():
    # 500 g di latte (1,03 g/ml) = 0,485... lt: LA domanda di Nicolas
    f = fattore_liquido("g", "lt", 1.03)
    assert abs(500 * f - 500 / 1.03 / 1000) < 1e-12


def test_ponte_inversi_e_kg_ml():
    assert abs(fattore_liquido("lt", "g", 1.03) - 1030.0) < 1e-9
    assert abs(fattore_liquido("kg", "ml", 1.03) - 1000 / 1.03) < 1e-9


def test_ponte_vietato_senza_densita_o_nello_stesso_gruppo():
    assert fattore_liquido("g", "lt", None) is None      # niente densità, niente ponte
    assert fattore_liquido("g", "lt", 0) is None         # densità non positiva
    assert fattore_liquido("g", "kg", 1.03) is None      # stesso gruppo: quello è fattore
    assert fattore_liquido("pz", "lt", 1.03) is None     # u.m. libere: mai


@pytest.fixture()
def conn():
    # solo per il catalogo PERSONALIZZABILE delle densità (RIFIN 52):
    # le conversioni pure restano testate SENZA banco dati
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    return c


def test_densita_suggerita_per_nome(conn):
    assert densita_suggerita(conn, "Latte intero fresco") == ("latte", 1.03)
    assert densita_suggerita(conn, "Caffè") == ("caffe", 1.00)         # accenti ok
    assert densita_suggerita(conn, "Alcool 95 gradi") == ("alcool", 0.79)
    assert densita_suggerita(conn, "Farina 00") is None
    assert densita_suggerita(conn, "") is None


def test_densita_suggerita_la_parola_piu_lunga_vince(conn):
    # "latte condensato" (1,30) batte "latte" (1,03)
    assert densita_suggerita(conn, "LATTE CONDENSATO zuccherato") == ("latte condensato", 1.30)


def test_densita_suggerita_confini_di_parola_intera(conn):
    # "latteggio" NON è "latte": mai un match su pezzo di parola
    assert densita_suggerita(conn, "Latteggio di cocco") == ("cocco", 1.01)


def test_densita_custom_vince_sul_catalogo(conn):
    # RIFIN 52: la voce dell'utente ha la meglio su quella predefinita
    conn.execute("INSERT INTO densita_custom (parola, densita) VALUES ('latte', 1.02)")
    assert densita_suggerita(conn, "Latte intero") == ("latte", 1.02)


def test_densita_custom_nuova_parola_e_piu_lunga(conn):
    # "latte di riso" è una voce NUOVA e come parola più lunga batte "latte"
    conn.execute("INSERT INTO densita_custom (parola, densita) VALUES ('latte di riso', 1.04)")
    assert densita_suggerita(conn, "Latte di riso biologico") == ("latte di riso", 1.04)
    assert densita_suggerita(conn, "Latte intero") == ("latte", 1.03)  # il resto non cambia


def test_densita_custom_eliminata_torna_il_catalogo(conn):
    conn.execute("INSERT INTO densita_custom (parola, densita) VALUES ('caffe', 0.98)")
    conn.execute("DELETE FROM densita_custom WHERE parola = 'caffe'")
    assert densita_suggerita(conn, "Caffè") == ("caffe", 1.00)  # il default rifiorisce


def test_densita_catalogo_agrumi_e_mandorla(conn):
    # le voci aggiunte su richiesta (RIFIN 52 bis): la frase lunga vince,
    # ma l'elisione italiana "succo d'arancia" cade bene su "arancia"
    # (l'apostrofo è un confine di parola per il matcher)
    assert densita_suggerita(conn, "Succo di arancia 100%") == ("succo di arancia", 1.045)
    assert densita_suggerita(conn, "Succo d'arancia") == ("arancia", 1.045)
    assert densita_suggerita(conn, "Succo di limone bio") == ("succo di limone", 1.03)
    assert densita_suggerita(conn, "Latte di mandorla di Sicilia") == ("latte di mandorla", 1.03)
    # le voci generiche non si fanno buttare fuori banda
    assert densita_suggerita(conn, "Latte fresco") == ("latte", 1.03)
    assert densita_suggerita(conn, "Succo di mela") == ("succo", 1.04)
