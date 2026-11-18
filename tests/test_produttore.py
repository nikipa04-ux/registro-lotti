import pytest

from app import db
from app.logic.etichetta_pdf import etichetta_pdf
from app.logic.impostazioni import leggi_produttore, salva_produttore


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    # scenario minimo: un lotto interno con un ingrediente
    c.execute("INSERT INTO prodotti (id, nome, sigla) VALUES (1, 'Latte fresco', 'LAT')")
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Fornitore test')")
    c.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (1, 1, 1, 'L1', '2026-11-01', '2026-12-01', 10, 10)")
    c.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, qta_prodotta, codice_lotto, "
        "data_produzione, data_scadenza) VALUES (1, 1, 5, 'LAT-20261118-01', "
        "'2026-11-18', '2026-11-22')")
    c.execute(
        "INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
        "VALUES (1, 'ingresso', 1, 4)")
    c.commit()
    yield c
    c.close()


def test_produttore_vuoto_di_default(conn):
    """Mai compilato: stringhe vuote, niente righe di produttore in etichetta."""
    assert leggi_produttore(conn) == {
        "ragione_sociale": "", "indirizzo": "", "piva": ""}
    pdf = etichetta_pdf(conn, 1, copie=1)
    assert b"Pasticceria" not in pdf
    assert b"Via Roma" not in pdf
    assert b"P.IVA" not in pdf


def test_salva_e_rilegge_produttore(conn):
    salva_produttore(conn, "  Pasticceria Dolce Vita di N. Panichi  ",
                     "  Via Roma 12, 00100 Roma  ", " 01234567890 ")
    conn.commit()
    assert leggi_produttore(conn) == {
        "ragione_sociale": "Pasticceria Dolce Vita di N. Panichi",
        "indirizzo": "Via Roma 12, 00100 Roma",
        "piva": "01234567890",
    }
    # il secondo giro sovrascrive (il produttore è UNO)
    salva_produttore(conn, "Pasticceria Nuova", "")
    conn.commit()
    assert leggi_produttore(conn) == {
        "ragione_sociale": "Pasticceria Nuova",
        "indirizzo": "",   # l'indirizzo svuotato sparisce davvero
        "piva": "",        # e la P.IVA anche
    }


def test_etichetta_pdf_porta_il_produttore(conn):
    """Ragione sociale in cima, recapito (indirizzo · P.IVA) in fondo:
    su OGNI etichetta."""
    salva_produttore(conn, "Pasticceria Dolce Vita di N. Panichi",
                     "Via Roma 12, 00100 Roma", "01234567890")
    conn.commit()
    pdf = etichetta_pdf(conn, 1, copie=8)
    testo = pdf.decode("cp1252")
    assert testo.count("Pasticceria Dolce Vita di N. Panichi") == 8
    assert testo.count("Via Roma 12, 00100 Roma \xb7 P.IVA 01234567890") == 8
    # la ragione sociale sta PRIMA del nome del prodotto, il recapito DOPO
    # gli ingredienti (la riga 'Contiene' non c'è: il latte non ha allergeni
    # dichiarati in questo scenario)
    assert testo.index("Pasticceria Dolce Vita") < testo.index("Lotto: ")
    assert testo.index("Via Roma 12") > testo.index("Ingredienti")


def test_etichetta_pdf_produttore_solo_ragione(conn):
    """Indirizzo e P.IVA facoltativi: la ragione sociale da sola regge."""
    salva_produttore(conn, "Dolce Vita", "")
    conn.commit()
    pdf = etichetta_pdf(conn, 1, copie=1)
    assert b"Dolce Vita" in pdf
    assert b"Via Roma" not in pdf
    assert b"P.IVA" not in pdf


def test_etichetta_pdf_solo_piva(conn):
    """P.IVA senza indirizzo: il recapito è comunque una riga sola."""
    salva_produttore(conn, "", "", "01234567890")
    conn.commit()
    pdf = etichetta_pdf(conn, 1, copie=1)
    testo = pdf.decode("cp1252")
    assert "P.IVA 01234567890" in testo
    assert "Via Roma" not in testo
