from app.logic.fefo import copertura_fefo, ordina_fefo


def lotto(i, scad, residua, arrivo="2026-11-01"):
    return {"id": i, "data_scadenza": scad, "quantita_residua": residua,
            "data_arrivo": arrivo}


def test_ordina_per_scadenza_crescente():
    lotti = [lotto(1, "2026-12-31", 5), lotto(2, "2026-11-20", 5), lotto(3, "2026-12-01", 5)]
    assert [l["id"] for l in ordina_fefo(lotti)] == [2, 3, 1]


def test_esclude_lotti_esauriti():
    lotti = [lotto(1, "2026-11-20", 0), lotto(2, "2026-12-31", 3)]
    assert [l["id"] for l in ordina_fefo(lotti)] == [2]


def test_copertura_su_piu_lotti():
    lotti = [lotto(1, "2026-12-01", 2), lotto(2, "2026-11-20", 3)]
    assegnazioni, coperto = copertura_fefo(lotti, 4)
    # FEFO: prima il lotto che scade prima (2), poi il prossimo (1)
    assert [(a["lotto"]["id"], a["quantita"]) for a in assegnazioni] == [(2, 3), (1, 1)]
    assert coperto == 4


def test_copertura_parziale_se_merce_mancante():
    lotti = [lotto(1, "2026-11-20", 3)]
    _, coperto = copertura_fefo(lotti, 5)
    assert coperto == 3
