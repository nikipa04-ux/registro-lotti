"""Arrivi: lotti in ingresso da fornitori.

La marca nasce QUI (nel lotto consegnato), con default dall'anagrafica.
La quantità residua nasce QUI uguale alla quantità: i consumi la scaricano.
TODO v0.1: endpoint allegati (dialog nativo lato client pywebview/tkinter in fase 2).
"""
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connessione
from ..logic.arrivi import ErroreArrivo, registra_arrivo

router = APIRouter(prefix="/api/arrivi", tags=["arrivi"])


@router.get("")
def lista_arrivi(testo: str = "", fornitore_id: int = 0,
                prodotto_id: int = 0, finestra: str = "all"):
    """Filtri a cascata come nella demo (prototipo, vista Arrivi):

    - testo: cerca in prodotto, lotto, fornitore o marca (una sola casella)
    - fornitore_id / prodotto_id: 0 = tutti
    - finestra: 'all' | '3' | '7' | 'scad'
    Totale e totale+IVA sono CALCOLATI qui (nel DB solo prezzo e IVA);
    'giorni' e 'esaurito' pure: l'UI non decide niente, colora solo in base
    ai valori che il server riporta.
    """
    q = f"%{testo.lower()}%"
    sql = (
        "SELECT li.*, COALESCE(li.marca, p.marca) AS marca_effettiva, "
        "p.nome AS prodotto, p.unita_misura AS um, f.nome AS fornitore "
        "FROM lotti_ingresso li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE (? = '' OR LOWER(p.nome) LIKE ? OR LOWER(li.codice_lotto) LIKE ? "
        "OR LOWER(f.nome) LIKE ? OR LOWER(COALESCE(li.marca, p.marca)) LIKE ?) "
        "AND (? = 0 OR li.fornitore_id = ?) "
        "AND (? = 0 OR li.prodotto_id = ?) "
        "ORDER BY li.data_arrivo DESC, li.id DESC"
    )
    args = (testo, q, q, q, q, fornitore_id, fornitore_id, prodotto_id, prodotto_id)
    with connessione() as conn:
        righe = [dict(r) for r in conn.execute(sql, args).fetchall()]
    n_totale = len(righe)

    oggi = date.today()
    for r in righe:
        r["giorni"] = (date.fromisoformat(r["data_scadenza"]) - oggi).days
        r["esaurito"] = (r["quantita_residua"] or 0) <= 0
        r["totale"], r["totale_iva"] = _totali(r)

    # Finestra di scadenza, come la demo: "3"/"7" includono gli scaduti
    if finestra == "scad":
        righe = [r for r in righe if r["giorni"] < 0]
    elif finestra in ("3", "7"):
        righe = [r for r in righe if r["giorni"] <= int(finestra)]

    return {"righe": righe, "n_filtrati": len(righe), "n_totale": n_totale}


def _totali(r):
    """Totale e totale+IVA: CALCOLATI (nel DB solo prezzo e IVA)."""
    if r["prezzo_unitario"] is None:
        return None, None
    totale = r["quantita"] * r["prezzo_unitario"]
    return totale, totale * (1 + (r["iva"] or 0) / 100)


@router.get("/{arrivo_id}")
def dettaglio_arrivo(arrivo_id: int):
    """Dettaglio lotto con consumi (tracciabilità avanti: chi l'ha usato)."""
    with connessione() as conn:
        lotto = conn.execute(
            "SELECT li.*, COALESCE(li.marca, p.marca) AS marca_effettiva, "
            "p.nome AS prodotto, p.unita_misura AS um, f.nome AS fornitore "
            "FROM lotti_ingresso li "
            "JOIN prodotti p ON p.id = li.prodotto_id "
            "JOIN fornitori f ON f.id = li.fornitore_id "
            "WHERE li.id = ?", (arrivo_id,),
        ).fetchone()
        if not lotto:
            return {"errore": "Lotto non trovato"}
        riga = dict(lotto)
        riga["giorni"] = (date.fromisoformat(riga["data_scadenza"]) - date.today()).days
        riga["totale"], riga["totale_iva"] = _totali(riga)
        usato_in = conn.execute(
            "SELECT li2.codice_lotto, li2.data_produzione, c.quantita_usata "
            "FROM consumi c JOIN lotti_interni li2 ON li2.id = c.lotto_interno_id "
            "WHERE c.origine = 'ingresso' AND c.lotto_origine_id = ?",
            (arrivo_id,),
        ).fetchall()
        return {"lotto": riga, "usato_in": [dict(u) for u in usato_in]}


class NuovoArrivo(BaseModel):
    prodotto_id: int
    fornitore_id: int
    codice_lotto: str
    data_arrivo: str
    data_scadenza: str
    quantita: float
    marca: str | None = None
    prezzo_unitario: float | None = None
    iva: float | None = None


@router.post("", status_code=201)
def crea_arrivo(dati: NuovoArrivo):
    """Registra un arrivo: le regole vivono in app/logic/arrivi.py."""
    with connessione() as conn:
        try:
            lotto = registra_arrivo(conn, dati.model_dump())
        except ErroreArrivo as e:
            # Nessuna scrittura parziale: il with esce con l'eccezione e annulla
            raise HTTPException(422, str(e))
        conn.commit()
        return lotto


@router.delete("/{arrivo_id}", status_code=204)
def elimina(arrivo_id: int):
    """Eliminazione protetta: rifiutata se il lotto ha consumi."""
    from ..logic.arrivi import elimina_arrivo

    with connessione() as conn:
        try:
            elimina_arrivo(conn, arrivo_id)
        except ErroreArrivo as e:
            raise HTTPException(422, str(e))
        conn.commit()


@router.post("/{arrivo_id}/azzera", status_code=204)
def azzera(arrivo_id: int):
    """Azzeramento manuale della residua (RIFIN 38): consumo NON di
    produzione (es. il latte finito al bar). Il lotto resta per la
    tracciabilità, con la data di chiusura. Recapita in "Esauriti".
    """
    from ..logic.arrivi import azzera_lotto

    with connessione() as conn:
        try:
            azzera_lotto(conn, arrivo_id)
        except ErroreArrivo as e:
            raise HTTPException(422, str(e))
        conn.commit()


@router.post("/{arrivo_id}/ripristina", status_code=204)
def ripristina(arrivo_id: int):
    """Ripristino di un lotto azzerato a mano (RIFIN 39): l'azzeramento
    era uno sbaglio. La residua torna com'era prima, il lotto esce da
    "Esauriti" e rientra in giacenza.
    """
    from ..logic.arrivi import ripristina_lotto

    with connessione() as conn:
        try:
            ripristina_lotto(conn, arrivo_id)
        except ErroreArrivo as e:
            raise HTTPException(422, str(e))
        conn.commit()
