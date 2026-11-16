"""Connessione al database SQLite.

Regola architetturale: la UI non tocca MAI il DB direttamente, passa sempre
dalla logica. Ogni richiesta apre la propria connessione (v0.1 monoutente:
nessun pool necessario), il file vive in data/ (fuori da git).
"""
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "registro-lotti.db"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connessione(db_path=None):
    """Apre una connessione con foreign keys attive e righe dizionario."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inizializza(db_path=None):
    """Crea il DB e lo schema se non esistono. Idempotente."""
    percorso = Path(db_path or DB_PATH)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    conn = connessione(percorso)
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn
