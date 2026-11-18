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


def garantisci_colonna(conn, tabella, colonna, definizione):
    """Migrazione idempotente dei DB esistenti: aggiunge la colonna se manca.

    Il CREATE TABLE IF NOT EXISTS non tocca le tabelle già presenti, quindi
    le colonne nate dopo la prima versione si aggiungono qui, a ogni start.
    """
    colonne = [r["name"] for r in conn.execute(f"PRAGMA table_info({tabella})")]
    if colonna not in colonne:
        conn.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {definizione}")


def inizializza(db_path=None):
    """Crea il DB e lo schema se non esistono. Idempotente.

    Migra anche i DB creati prima di ogni nuova colonna: l'app si aggiorna
    da sola al riavvio, senza perdere i dati registrati.
    """
    percorso = Path(db_path or DB_PATH)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    conn = connessione(percorso)
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())
    garantisci_colonna(conn, "lotti_interni", "ricetta_modificata",
                       "INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    return conn
