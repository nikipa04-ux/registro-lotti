"""Magazzino e scadenze: tutto CALCOLATO dalle registrazioni.

Nessuna giacenza si inserisce a mano: è arrivo meno consumi. Le regole di
calcolo (consumo medio, copertura, finestre di scadenza) vivono in
logic/magazzino.py, testate senza HTTP: qui si apre la connessione, si
valida l'input e si delega.
"""
from fastapi import APIRouter, HTTPException

from ..db import connessione
from ..logic.magazzino import FINESTRE, lista_scadenze, magazzino

router = APIRouter(prefix="/api/magazzino", tags=["magazzino"])


@router.get("")
def giacenze():
    """Giacenze per prodotto e marca + statistiche di copertura.

    righe: una riga per prodotto+marca in giacenza (residua > 0);
    stat: una riga per prodotto con almeno un arrivo, anche esenato
          (giacenza 0: con consumo storico è "da ordinare").
    """
    with connessione() as conn:
        return magazzino(conn)


@router.get("/scadenze")
def scadenze(finestra: str = "7"):
    """Lotti nella finestra di scadenza scelta, ordinati per urgenza.

    finestra: '3' | '7' (default) | '30' | 'all' | 'scad' (solo scaduti,
    con giacenza gli ingressi: vanno buttati, non nascosti).
    """
    if finestra not in FINESTRE:
        raise HTTPException(
            422, "Finestra non valida: scegli 3, 7, 30, all o scad")
    with connessione() as conn:
        return lista_scadenze(conn, finestra)
