"""Arrivi: lotti in ingresso da fornitori.

La marca nasce QUI (nel lotto consegnato), con default dall'anagrafica.
Gli allegati sono opzionali: il DB salva solo il percorso su disco.
TODO v0.1: POST arrivo con quantita_residua = quantita; dettaglio lotto;
endpoint allegati (dialog nativo lato client pywebview/tkinter in fase 2).
"""
from fastapi import APIRouter

from ..db import connessione

router = APIRouter(prefix="/api/arrivi", tags=["arrivi"])


@router.get("")
def lista_arrivi(testo: str = ""):
    """Ricerca per nome prodotto, lotto o fornitore (una sola casella)."""
    q = f"%{testo.lower()}%"
    with connessione() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT li.*, p.nome AS prodotto, p.unita_misura AS um, f.nome AS fornitore "
            "FROM lotti_ingresso li "
            "JOIN prodotti p ON p.id = li.prodotto_id "
            "JOIN fornitori f ON f.id = li.fornitore_id "
            "WHERE ? = '' OR LOWER(p.nome) LIKE ? OR LOWER(li.codice_lotto) LIKE ? "
            "OR LOWER(f.nome) LIKE ? OR LOWER(li.marca) LIKE ? "
            "ORDER BY li.data_arrivo DESC, li.id DESC",
            (testo, q, q, q, q),
        ).fetchall()]


@router.get("/{arrivo_id}")
def dettaglio_arrivo(arrivo_id: int):
    """Dettaglio lotto con consumi (tracciabilità avanti: chi l'ha usato)."""
    with connessione() as conn:
        lotto = conn.execute(
            "SELECT li.*, p.nome AS prodotto, f.nome AS fornitore "
            "FROM lotti_ingresso li "
            "JOIN prodotti p ON p.id = li.prodotto_id "
            "JOIN fornitori f ON f.id = li.fornitore_id "
            "WHERE li.id = ?", (arrivo_id,),
        ).fetchone()
        if not lotto:
            return {"errore": "Lotto non trovato"}
        usato_in = conn.execute(
            "SELECT li2.codice_lotto, li2.data_produzione, c.quantita_usata "
            "FROM consumi c JOIN lotti_interni li2 ON li2.id = c.lotto_interno_id "
            "WHERE c.origine = 'ingresso' AND c.lotto_origine_id = ?",
            (arrivo_id,),
        ).fetchall()
        return {"lotto": dict(lotto), "usato_in": [dict(u) for u in usato_in]}
