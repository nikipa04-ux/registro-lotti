import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from app import db
from app.logic.impostazioni import esporta_backup


def _db_con_dati():
    """Un DB con dentro rossa VERA: un prodotto, un fornitore, un arrivo."""
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio')")
    c.execute(
        "INSERT INTO prodotti (id, nome, conservazione, unita_misura, "
        "denominazione_legale) VALUES (10, 'Latte intero', 'Frigo', 'lt', 'Latte')"
    )
    c.execute(
        "INSERT INTO lotti_ingresso (prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua) "
        "VALUES (10, 1, 'LAT-A', '2026-11-27', '2026-12-05', 5, 5)"
    )
    c.commit()
    return c


def test_backup_valido_con_dentro_gli_stessi_dati():
    conn = _db_con_dati()
    nome, dati = esporta_backup(conn)
    # i bytes sono un file SQLite VERO: si riapre e contiene i dati
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(dati)
        percorso = Path(f.name)
    try:
        copia = sqlite3.connect(percorso)
        n_prodotti = copia.execute(
            "SELECT COUNT(*) FROM prodotti WHERE nome = 'Latte intero'"
        ).fetchone()[0]
        n_arrivi = copia.execute(
            "SELECT COUNT(*) FROM lotti_ingresso WHERE codice_lotto = 'LAT-A'"
        ).fetchone()[0]
        tabelle = {r[0] for r in copia.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        copia.close()
        assert n_prodotti == 1 and n_arrivi == 1
        assert "lotti_ingresso" in tabelle and "consumi" in tabelle
    finally:
        percorso.unlink()


def test_backup_nome_file_con_la_data_di_oggi():
    conn = _db_con_dati()
    nome, dati = esporta_backup(conn)
    assert nome == f"registro-lotti-backup-{date.today().isoformat()}.db"
    assert dati[:16] == b"SQLite format 3\x00"
