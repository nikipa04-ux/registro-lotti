"""Registro Lotti - server FastAPI.

L'UI è "stupida" di proposito: mostra e raccoglie, non decide.
Tutte le regole vivono in app/logic, tutte le query nella logica,
il DB si raggiunge solo da lì.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api import (
    anagrafiche,
    arrivi,
    dashboard,
    impostazioni,
    magazzino,
    produzioni,
    ricette,
)
from .logic.anagrafiche import garantisci_allergeni_di_legge

app = FastAPI(
    title="Registro Lotti",
    version="0.1.0",
    description="Gestionale lotti per piccole aziende della ristorazione",
)

app.include_router(anagrafiche.router)
app.include_router(arrivi.router)
app.include_router(produzioni.router)
app.include_router(ricette.router)
app.include_router(impostazioni.router)
app.include_router(magazzino.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def avvio():
    conn = db.inizializza()
    # i 14 allergeni di legge (Reg. UE 1169/2011) sono dati di riferimento:
    # assicurati a ogni avvio, anche sui DB nati col vecchio seed demo a 4
    garantisci_allergeni_di_legge(conn)


@app.get("/api/health")
def health():
    """Il client lo chiama all'avvio per confermare che il server risponde."""
    return {"stato": "ok", "app": "registro-lotti", "versione": "0.1.0"}


# L'interfaccia: index servita sulla root, asset statici in app/ui/
_UI = Path(__file__).resolve().parent / "ui"
app.mount("/static", StaticFiles(directory=_UI), name="static")


@app.get("/")
def home():
    return FileResponse(_UI / "index.html")
