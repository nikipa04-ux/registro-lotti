"""Endpoint della dashboard: chiama la logica e restituisce il quadro."""
from fastapi import APIRouter

from ..db import connessione
from ..logic.dashboard import calcola_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard():
    with connessione() as conn:
        return calcola_dashboard(conn)
