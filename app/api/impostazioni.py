"""Impostazioni dell'attività: i dati del produttore che vanno in etichetta.

GET  /api/impostazioni      -> {ragione_sociale, indirizzo}
PUT  /api/impostazioni      -> salva (facoltativi: vuoto = via)
GET  /api/impostazioni/backup -> scarica una copia .db (RIFIN 59)
"""
from fastapi import APIRouter, Response
from pydantic import BaseModel

from ..db import connessione
from ..logic.impostazioni import esporta_backup, leggi_produttore, salva_produttore

router = APIRouter(prefix="/api/impostazioni", tags=["impostazioni"])


@router.get("")
def leggi():
    """I dati del produttore (se mai compilati: stringhe vuote)."""
    with connessione() as conn:
        return leggi_produttore(conn)


@router.get("/backup")
def backup():
    """RIFIN 59: scarica una copia .db completa del registro (backup:
    chiavetta, cloud, dove vuole l'utente). Copia COERENTE anche a
    server acceso, grazie all'API di backup di SQLite."""
    with connessione() as conn:
        nome, dati = esporta_backup(conn)
    return Response(
        content=dati,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


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
