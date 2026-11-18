"""Impostazioni dell'attività: i dati del produttore che vanno in etichetta.

GET  /api/impostazioni      -> {ragione_sociale, indirizzo}
PUT  /api/impostazioni      -> salva (facoltativi: vuoto = via)
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..db import connessione
from ..logic.impostazioni import leggi_produttore, salva_produttore

router = APIRouter(prefix="/api/impostazioni", tags=["impostazioni"])


@router.get("")
def leggi():
    """I dati del produttore (se mai compilati: stringhe vuote)."""
    with connessione() as conn:
        return leggi_produttore(conn)


class DatiProduttore(BaseModel):
    ragione_sociale: str = ""
    indirizzo: str = ""
    piva: str = ""


@router.put("")
def salva(dati: DatiProduttore):
    """Salva i dati dell'attività: finiscono sull'etichetta del PDF."""
    with connessione() as conn:
        risultato = salva_produttore(
            conn, dati.ragione_sociale, dati.indirizzo, dati.piva)
        conn.commit()
        return risultato
