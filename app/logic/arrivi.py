"""Registrazione di un arrivo: le regole con cui un lotto entra in magazzino.

L'arrivo è l'UNICO punto in cui nasce un lotto in ingresso:
  - quantita_residua parte UGUALE a quantita (saranno i consumi delle
    produzioni a scaricarla: le giacenze non si scrivono mai a mano);
  - la marca nasce QUI, nel lotto consegnato, con default dall'anagrafica
    (regola di design: i dati vivono dove nascono);
  - il codice lotto è quello ESTERNO del fornitore, trascritto
    dall'etichetta della confezione.
"""
from datetime import date


class ErroreArrivo(ValueError):
    """Input respinto: il messaggio va mostrato all'utente così com'è."""


def _data_iso(testo, campo):
    """Accetta solo date ISO 'YYYY-MM-DD' vere."""
    try:
        return date.fromisoformat((testo or "").strip()).isoformat()
    except ValueError:
        raise ErroreArrivo(f"Data di {campo} non valida: serve il formato AAAA-MM-GG")


def registra_arrivo(conn, dati):
    """Valida e registra un lotto in ingresso, immettendolo in magazzino.

    dati: dict con prodotto_id, fornitore_id, codice_lotto, data_arrivo,
          data_scadenza (ISO), quantita; facoltativi marca, prezzo_unitario,
          iva, nota (descrittiva di QUESTA consegna, RIFIN 55).
    Ritorna il dict della riga inserita (con nome prodotto, um e fornitore).
    Solleva ErroreArrivo con messaggio pronto per l'utente se l'input è respinto.
    """
    prodotto_id = dati.get("prodotto_id")
    fornitore_id = dati.get("fornitore_id")
    if not prodotto_id or not fornitore_id:
        raise ErroreArrivo("Scegli sia l'ingrediente sia il fornitore")

    prodotto = conn.execute(
        "SELECT * FROM prodotti WHERE id = ?", (prodotto_id,)
    ).fetchone()
    if not prodotto:
        raise ErroreArrivo("Ingrediente inesistente")
    if prodotto["famiglia_id"] is not None:
        raise ErroreArrivo(
            f'"{prodotto["nome"]}" è un prodotto di laboratorio: nasce da una '
            "produzione, non da un arrivo"
        )
    fornitore = conn.execute(
        "SELECT * FROM fornitori WHERE id = ?", (fornitore_id,)
    ).fetchone()
    if not fornitore:
        raise ErroreArrivo("Fornitore inesistente")

    codice = (dati.get("codice_lotto") or "").strip()
    if not codice:
        raise ErroreArrivo("Codice lotto del fornitore obbligatorio")

    data_arrivo = _data_iso(dati.get("data_arrivo"), "arrivo")
    data_scadenza = _data_iso(dati.get("data_scadenza"), "scadenza")
    if data_scadenza < data_arrivo:
        raise ErroreArrivo("La data di scadenza non può precedere quella di arrivo")

    try:
        quantita = float(dati.get("quantita"))
    except (TypeError, ValueError):
        quantita = 0.0
    if quantita <= 0:
        raise ErroreArrivo("La quantità deve essere maggiore di zero")

    duplicato = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_ingresso "
        "WHERE prodotto_id = ? AND codice_lotto = ? AND fornitore_id = ?",
        (prodotto_id, codice, fornitore_id),
    ).fetchone()["n"]
    if duplicato:
        raise ErroreArrivo(
            f'Lotto "{codice}" già registrato per "{prodotto["nome"]}" '
            f'da {fornitore["nome"]}'
        )

    # La marca del lotto consegnato vince; se manca, quella abituale dell'anagrafica
    marca = (dati.get("marca") or "").strip() or prodotto["marca"]

    cur = conn.execute(
        "INSERT INTO lotti_ingresso "
        "(prodotto_id, fornitore_id, marca, codice_lotto, data_arrivo, "
        " data_scadenza, quantita, quantita_residua, prezzo_unitario, iva, nota) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (prodotto_id, fornitore_id, marca, codice, data_arrivo, data_scadenza,
         quantita, quantita, dati.get("prezzo_unitario"), dati.get("iva"),
         (dati.get("nota") or "").strip() or None),
    )
    riga = conn.execute(
        "SELECT li.*, p.nome AS prodotto, p.unita_misura AS um, f.nome AS fornitore "
        "FROM lotti_ingresso li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE li.id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return dict(riga)


def elimina_arrivo(conn, arrivo_id):
    """Eliminazione PROTETTA di un lotto in ingresso (errore di registrazione).

    Rifiutata se il lotto è già nel verbale di una produzione (consumi):
    la tracciabilità non si riscrive. Senza consumi il lotto si elimina.
    """
    lotto = conn.execute(
        "SELECT * FROM lotti_ingresso WHERE id = ?", (arrivo_id,)
    ).fetchone()
    if not lotto:
        raise ErroreArrivo("Lotto in arrivo inesistente")
    usato = conn.execute(
        "SELECT COUNT(*) AS n FROM consumi "
        "WHERE origine = 'ingresso' AND lotto_origine_id = ?",
        (arrivo_id,),
    ).fetchone()["n"]
    if usato:
        raise ErroreArrivo(
            "Eliminazione protetta: il lotto è già consumato in "
            f"{usato} produzione/i (è nel verbale). "
            "Correggi piuttosto annullando quella produzione."
        )
    conn.execute("DELETE FROM lotti_ingresso WHERE id = ?", (arrivo_id,))


def azzera_lotto(conn, arrivo_id, oggi=None):
    """Azzeramento MANUALE della residua di un lotto in ingresso (RIFIN 38).

    Deroga controllata alla regola "il magazzino si legge": l'ingrediente
    è uscito dal circuito del registro con un consumo NON di produzione
    (il classico: il latte finito anche al bar per i cappuccini). La
    residua va a 0 ma il lotto NON si cancella: resta per la tracciabilità,
    con la data di chiusura scritta qui. La residua che c'era PRIMA si
    fotografa in residua_pre_azzeramento (RIFIN 39): serve al ripristino
    se l'azzeramento era stato uno sbaglio.
    """
    lotto = conn.execute(
        "SELECT codice_lotto, quantita_residua FROM lotti_ingresso WHERE id = ?",
        (arrivo_id,),
    ).fetchone()
    if not lotto:
        raise ErroreArrivo("Lotto in arrivo inesistente")
    if not lotto["quantita_residua"]:
        raise ErroreArrivo("Il lotto è già a zero: niente da azzerare.")
    if oggi is None:
        oggi = date.today()
    if isinstance(oggi, str):
        oggi = date.fromisoformat(oggi)
    # nel SET gli expression leggono i valori VECCHI: la foto parte dalla
    # residua com'era prima di questo UPDATE, tutto in una sola scrittura
    conn.execute(
        "UPDATE lotti_ingresso SET residua_pre_azzeramento = quantita_residua, "
        "quantita_residua = 0, data_esaurimento = ? WHERE id = ?",
        (oggi.isoformat(), arrivo_id),
    )


def ripristina_lotto(conn, arrivo_id):
    """RIPRISTINO di un lotto azzerato a mano (RIFIN 39): eri stato tu.

    Annulla l'azzeramento riportando la residua com'era prima (la foto in
    residua_pre_azzeramento); se la foto manca (lotti azzerati prima
    della RIFIN 39) si torna alla quantità originale d'arrivo. La data di esaurimento si pulisce: il
    lotto esce da "Esauriti" e rientra in giacenza.

    Rifiutato se il lotto NON è stato azzerato a mano: un lotto chiuso
    dai consumi delle produzioni si corregge annullando quella produzione
    (la tracciabilità non si riscrive).
    """
    lotto = conn.execute(
        "SELECT codice_lotto, quantita, data_esaurimento, residua_pre_azzeramento "
        "FROM lotti_ingresso WHERE id = ?",
        (arrivo_id,),
    ).fetchone()
    if not lotto:
        raise ErroreArrivo("Lotto in arrivo inesistente")
    if lotto["data_esaurimento"] is None:
        raise ErroreArrivo(
            "Questo lotto non è stato azzerato a mano: niente da ripristinare."
        )
    residua = lotto["residua_pre_azzeramento"]
    if residua is None:
        residua = lotto["quantita"] or 0
    conn.execute(
        "UPDATE lotti_ingresso SET quantita_residua = ?, data_esaurimento = NULL, "
        "residua_pre_azzeramento = NULL WHERE id = ?",
        (residua, arrivo_id),
    )
