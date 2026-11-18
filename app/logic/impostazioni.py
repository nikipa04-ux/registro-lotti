"""Impostazioni dell'attività: chi PRODUCE (e firma le etichette).

Il produttore è UNO: la pasticceria stessa. Niente anagrafica a più
righe, due soli dati bastano all'etichetta che accompagna il prodotto:

  - ragione sociale: il nome che va in cima all'etichetta
  - indirizzo:      dove si trova l'operatore (Reg. UE 1169/2011)
  - P.IVA:          l'identificativo fiscale dell'attività (facoltativa)

Nessun dato calcolato: si legge, si salva, si mette in etichetta.
Se sono vuoti l'etichetta semplicemente non porta le righe del
produttore (la cella resta quella che è).
"""

CHIAVE_RAGIONE = "produttore_ragione_sociale"
CHIAVE_INDIRIZZO = "produttore_indirizzo"
CHIAVE_PIVA = "produttore_piva"


def _leggi(conn, chiave):
    riga = conn.execute(
        "SELECT valore FROM impostazioni WHERE chiave = ?", (chiave,)
    ).fetchone()
    return riga["valore"] if riga else ""


def _scrivi(conn, chiave, valore):
    """UPSERT di una chiave: valore vuoto = chiave eliminata."""
    if valore:
        conn.execute(
            "INSERT INTO impostazioni (chiave, valore) VALUES (?, ?) "
            "ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore",
            (chiave, valore),
        )
    else:
        conn.execute("DELETE FROM impostazioni WHERE chiave = ?", (chiave,))


def leggi_produttore(conn):
    """I dati del produttore così come sono (stringhe vuote se mai compilati)."""
    return {
        "ragione_sociale": _leggi(conn, CHIAVE_RAGIONE),
        "indirizzo": _leggi(conn, CHIAVE_INDIRIZZO),
        "piva": _leggi(conn, CHIAVE_PIVA),
    }


def salva_produttore(conn, ragione_sociale, indirizzo, piva=""):
    """Salva i dati del produttore e li restituisce normalizzati.

    Tutti facoltativi: vuoti = l'etichetta non porta le righe del
    produttore. Il chiamante decide il commit.
    """
    ragione_sociale = (ragione_sociale or "").strip()
    indirizzo = (indirizzo or "").strip()
    piva = (piva or "").strip()
    _scrivi(conn, CHIAVE_RAGIONE, ragione_sociale)
    _scrivi(conn, CHIAVE_INDIRIZZO, indirizzo)
    _scrivi(conn, CHIAVE_PIVA, piva)
    return leggi_produttore(conn)
