"""Il libro ricette PDF (HACCP): schede, allergeni ereditati, pagine vere."""
import re

import pytest

from app import db
from app.logic.libro_ricette_pdf import (
    allergeni_ricetta,
    libro_ricette_pdf,
    schede_ricette,
)


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    # latte/uova/zucchero acquistati, crema e bignè di laboratorio
    for pid, nome in [(1, "Latte fresco"), (2, "Uova"), (3, "Zucchero"),
                      (4, "Crema pasticcera"), (5, "Bignè")]:
        c.execute("INSERT INTO prodotti (id, nome) VALUES (?, ?)", (pid, nome))
    c.execute("INSERT INTO famiglie (id, nome) VALUES (1, 'Creme')")
    c.execute("UPDATE prodotti SET unita_misura = 'lt' WHERE id = 1")
    c.execute("UPDATE prodotti SET unita_misura = 'kg' WHERE id = 3")
    c.execute("UPDATE prodotti SET famiglia_id = 1 WHERE id IN (4, 5)")
    c.execute("INSERT INTO allergeni (id, nome) VALUES (1, 'Latte'), (2, 'Uova')")
    c.execute("INSERT INTO prodotti_allergeni VALUES (1, 1), (2, 2)")
    # ricetta della crema: 4 lt latte, 2 kg uova, 1,5 kg zucchero
    c.execute("INSERT INTO ricette (id, prodotto_id, famiglia_id, resa, procedimento) "
              "VALUES (10, 4, 1, '5 kg', 'Bollire il latte.')")
    for iid, qta in [(1, 4), (2, 2), (3, 1.5)]:
        c.execute("INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
                  "VALUES (10, ?, ?)", (iid, qta))
    # ricetta del bignè: USA LA CREMA (semilavorato: niente allergeni diretti)
    c.execute("INSERT INTO ricette (id, prodotto_id, famiglia_id, resa) "
              "VALUES (11, 5, 1, '60 pz')")
    c.execute("INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
              "VALUES (11, 4, 3)")
    c.commit()
    yield c
    c.close()


def _n_pagine(pdf):
    return len(re.findall(b"/Type /Page ", pdf))


# ---- le schede: il contratto (dati) prima della carta (PDF) ----

def test_schede_alfabetiche_con_righe_e_rese(conn):
    schede = schede_ricette(conn)
    assert [s["prodotto"] for s in schede] == ["Bignè", "Crema pasticcera"]
    crema = schede[1]
    assert crema["famiglia"] == "Creme"
    assert crema["resa"] == "5 kg"
    assert [(r["nome"], r["quantita"], r["um"]) for r in crema["righe"]] == [
        ("Latte fresco", 4, "lt"), ("Uova", 2, ""), ("Zucchero", 1.5, "kg")]
    assert crema["procedimento"] == "Bollire il latte."
    # il bignè dichiara la crema come SEMILAVORATO
    assert schede[0]["righe"][0]["semilavorato"] is True


def test_allergeni_ereditati_dal_semilavorato(conn):
    # il bignè non dichiara niente ma la crema porta latte e uova
    assert allergeni_ricetta(conn, 5) == ["Latte", "Uova"]
    assert allergeni_ricetta(conn, 4) == ["Latte", "Uova"]
    assert schede_ricette(conn)[0]["allergeni"] == ["Latte", "Uova"]


def test_allergeni_senza_ricetta_dichiarano_e_non_ereditano(conn):
    # un ingrediente acquistato: SOLO la sua dichiarazione, niente ricorsione
    assert allergeni_ricetta(conn, 1) == ["Latte"]


# ---- il PDF ----

def test_libro_pdf_valido_e_pieno(conn):
    pdf = libro_ricette_pdf(conn)
    assert pdf.startswith(b"%PDF-1.4\n")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"\nxref\n") == 1
    offsets = [int(m) for m in re.findall(rb"(\d{10}) 00000 n", pdf)]
    for n, posizione in enumerate(offsets, start=1):
        assert pdf[posizione:posizione + len(b"%d 0 obj" % n)] == \
            b"%d 0 obj" % n
    # il contenuto viaggia in cp1252 dentro gli stream: si trova a parole
    assert b"Libro ricette" in pdf
    assert b"Crema pasticcera" in pdf
    assert b"Latte fresco \xb7 4 lt" in pdf            # ingrediente + quantità
    assert b"Contiene: Latte, Uova" in pdf           # allergeni (il bignè EREDA)
    assert b"Stampato il" in pdf                       # documento datato
    assert b"Procedimento" not in pdf                   # su carta NON serve
    assert b"Bollire il latte." not in pdf              # e infatti non c'è
    assert _n_pagine(pdf) == 1


def test_libro_pdf_vuoto_resta_un_documento_onesto(conn):
    conn.execute("DELETE FROM ricette_righe")
    conn.execute("DELETE FROM ricette")
    conn.commit()
    pdf = libro_ricette_pdf(conn)
    assert pdf.startswith(b"%PDF-1.4\n")
    assert b"Nessuna ricetta salvata." in pdf
    assert _n_pagine(pdf) == 1


def test_libro_pdf_molte_ricette_vanno_a_capo(conn):
    # 40 ricette di fila: il foglio finisce, le pagine dopo arrivano da sole
    for i in range(40):
        conn.execute("INSERT INTO prodotti (id, nome) VALUES (?, ?)",
                  (100 + i, f"Torta n.{i}"))
        conn.execute("INSERT INTO ricette (id, prodotto_id, resa) "
                  "VALUES (?, ?, '1 pz')", (100 + i, 100 + i))
        conn.execute("INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
                  "VALUES (?, 1, 0.5)", (100 + i,))
    conn.commit()
    pdf = libro_ricette_pdf(conn)
    assert _n_pagine(pdf) > 1
    # e ogni ricetta è rimasta INTERA: il titolo non sparisce nel rimescolo
    assert pdf.count(b"Torta n.") == 40


def test_libro_pdf_negozio_in_vista_come_in_etichetta(conn):
    # Impostazioni -> Produttore: il nome del negozio va IN EVIDENZA (F2
    # neretto) e la P.IVA nel PDF, come nelle etichette dei lotti
    from app.logic.impostazioni import salva_produttore
    salva_produttore(conn, "Pasticceria Delizia", "Via Roma 1, Grosseto",
                     "IT01234567890")
    conn.commit()
    pdf = libro_ricette_pdf(conn)
    assert b"Pasticceria Delizia" in pdf
    assert b"P.IVA IT01234567890" in pdf
    assert b"Via Roma 1, Grosseto" in pdf
    # il nome va in neretto (F2), come in etichetta: si vede dallo stream
    righe = [m.group(1).decode("cp1252")
             for m in re.finditer(rb"/F2 [\d.]+ Tf.*?\((.*?)\) Tj", pdf, re.S)]
    assert any("Pasticceria Delizia" in r for r in righe), \
        "il nome del negozio non sta nel font neretto (F2)"


def test_libro_pdf_senza_produttore_nessuna_righe_in_piu(conn):
    # Produttore mai compilato: la copertina resta onesta, senza P.IVA
    pdf = libro_ricette_pdf(conn)
    assert b"P.IVA" not in pdf
    assert b"Libro ricette" in pdf
