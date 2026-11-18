import re

import pytest

from app import db
from app.logic.etichetta_pdf import (
    ErroreEtichetta,
    _spezza,
    etichetta_pdf,
    nome_file_pdf,
)


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
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Fornitore test')")
    for aid, pid in [(1, 1), (2, 2), (3, 3)]:
        c.execute(
            "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
            "data_arrivo, data_scadenza, quantita, quantita_residua) "
            "VALUES (?, ?, 1, 'L1', '2026-11-01', '2026-12-01', 10, 10)", (aid, pid))
    c.execute("INSERT INTO allergeni (id, nome) VALUES (1, 'Latte'), (2, 'Uova')")
    c.execute("INSERT INTO prodotti_allergeni VALUES (1, 1), (2, 2)")
    c.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (1, 4, 5, 'CRP-20261113-01', "
        "'2026-11-13', '2026-11-16')")
    for from_id, qta in [(1, 4), (2, 2), (3, 1.5)]:
        c.execute("INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
                  "VALUES (1, 'ingresso', ?, ?)", (from_id, qta))
    c.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (2, 5, 60, 'BIG-20261113-01', "
        "'2026-11-13', '2026-11-20')")
    c.execute("INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
              "VALUES (2, 'interno', 1, 3), (2, 'ingresso', 2, 0.5)")
    c.commit()
    yield c
    c.close()


def _n_pagine(pdf):
    # "/Type /Page " con lo spazio: per non contare anche "/Type /Pages"
    return len(re.findall(b"/Type /Page ", pdf))


def test_pdf_intestazione_e_fine(conn):
    """Un PDF vero si riconosce: header, xref, trailer, %%EOF."""
    pdf = etichetta_pdf(conn, 2)
    assert pdf.startswith(b"%PDF-1.4\n")
    assert pdf.count(b"\nxref\n") == 1
    assert b"trailer" in pdf
    assert pdf.rstrip().endswith(b"%%EOF")
    # gli offset della xref puntano davvero agli oggetti
    offsets = [int(m) for m in re.findall(rb"(\d{10}) 00000 n", pdf)]
    for n, posizione in enumerate(offsets, start=1):
        assert pdf[posizione:posizione + len(b"%d 0 obj" % n)] == \
            b"%d 0 obj" % n


def test_pdf_griglia_una_copia_per_cella(conn):
    """8 etichette per foglio: il codice lotto compare UNA volta per cella."""
    pdf = etichetta_pdf(conn, 2, copie=8)
    assert pdf.count(b"BIG-20261113-01") == 8
    assert _n_pagine(pdf) == 1
    # il foglio è una griglia: 8 celle, tutte dentro i margini dell'A4
    celle = [(float(a), float(b), float(w), float(h))
             for a, b, w, h in
             re.findall(rb"([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+) re S", pdf)]
    assert len(celle) == 8
    for x, y, larghezza, altezza in celle:
        assert 0 <= x and x + larghezza <= 595.29
        assert 0 <= y and y + altezza <= 841.90
        assert larghezza == pytest.approx(round((595.28 - 40 - 12) / 2, 2))
        assert altezza == pytest.approx(round((841.89 - 40 - 36) / 4, 2))


def test_pdf_piu_copie_piu_pagine(conn):
    """Oltre 8 copie il foglio successivo arriva da solo, niente carta sprecata."""
    pdf = etichetta_pdf(conn, 2, copie=9)
    assert pdf.count(b"BIG-20261113-01") == 9
    assert _n_pagine(pdf) == 2
    pdf2 = etichetta_pdf(conn, 2, copie=40)
    assert pdf2.count(b"BIG-20261113-01") == 40
    assert _n_pagine(pdf2) == 5
    # e con copie < 1 si stampa ALMENO l'etichetta che si è chiesta
    pdf3 = etichetta_pdf(conn, 2, copie=0)
    assert pdf3.count(b"BIG-20261113-01") == 1
    assert _n_pagine(pdf3) == 1


def test_pdf_contenuto_dell_etichetta(conn):
    """L'etichetta accompagna il prodotto: lotto, date, ingredienti (CALCOLATI),
    allergeni in evidenza."""
    pdf = etichetta_pdf(conn, 2, copie=1)
    assert b"Prodotto il: 2026-11-13" in pdf
    assert b"Scade il: 2026-11-20" in pdf
    # il bignè contiene la crema SCESA a ingredienti d'origine: latte, uova,
    # zucchero. "Crema pasticcera" NON è ingrediente: si ricorre dentro.
    testo = pdf.decode("cp1252")
    assert "Ingredienti" in testo
    assert "Latte fresco" in testo
    assert "Crema pasticcera" not in testo.rsplit("Ingredienti", 1)[1]
    # gli allergeni si dichiarano in NERETTO: e TUTTO il pdf è MONOCROMO
    assert b"Contiene:" in pdf
    assert pdf.count(b"Contiene: Latte, Uova") == 1
    assert b"0.720 0.050 0.050 rg" not in pdf    # niente rosso: tutto nero
    # la data e gli ingredienti SONO nella cella (bordi): guida di taglio


def test_pdf_accenti_e_parentesi(conn):
    """Le lettere accentate (Bignè) viaggiano in cp1252; le parentesi della
    denominazione legale si zittiscono, il pdf non si rompe."""
    conn.execute(
        "UPDATE prodotti SET denominazione_legale = 'Latte fresco ( pastorizzato à è )' "
        "WHERE id = 1")
    conn.commit()
    pdf = etichetta_pdf(conn, 2, copie=1)
    # Bignè: la è esiste SOLO in cp1252 dentro il pdf
    assert b"\xe8" in pdf
    testo = pdf.decode("cp1252")
    assert "Bignè" in testo
    # la denominazione con le parentesi: escapate, tutte appaiate
    assert "Latte fresco \\( pastorizzato" in testo
    for riga in testo.split("\n"):
        if "( pastorizzato" in riga:
            assert riga.count("\\(") == 1 and riga.count("\\)") == 1


def test_pdf_lotto_inesistente(conn):
    with pytest.raises(ErroreEtichetta):
        etichetta_pdf(conn, 999)


def test_spezza_rispetta_la_larghezza():
    """Ogni riga spezzata sta dentro la larghezza concessa."""
    lungo = ("farina di grano tenero tipo 00, zucchero, burro, uova fresche "
             "di gallina, latte intero fresco pastorizzato, lievito per dolci")
    righe = _spezza(lungo, "F1", 8.2, 200.0)
    assert len(righe) > 1
    from app.logic.etichetta_pdf import _larghezza
    for riga in righe:
        assert _larghezza(riga, "F1", 8.2) <= 200.0 + 1e-6


def test_nome_file_pdf():
    assert nome_file_pdf("BIG-20261113-01") == "etichetta-BIG-20261113-01.pdf"
    assert nome_file_pdf(None) == "etichetta-lotto.pdf"
