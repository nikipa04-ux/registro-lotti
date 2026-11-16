import pytest

from app.logic.um import converti, fattore, gruppo_di


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
