"""Produzioni: lotti interni, consumi (il verbale), etichetta calcolata.

La produzione è SLAVE della ricetta: proporziona e fa confermare i consumi
(FEFO), poi salva ciò che è successo davvero. La ricetta non si tocca.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..db import connessione
from ..logic.etichetta import etichetta
from ..logic.lotti import genera_codice

router = APIRouter(prefix="/api/produzioni", tags=["produzioni"])


@router.get("")
def lista_produzioni(testo: str = ""):
    q = f"%{testo.lower()}%"
    with connessione() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT li.*, p.nome AS prodotto, p.sigla "
            "FROM lotti_interni li JOIN prodotti p ON p.id = li.prodotto_id "
            "WHERE ? = '' OR LOWER(p.nome) LIKE ? OR LOWER(li.codice_lotto) LIKE ? "
            "ORDER BY li.data_produzione DESC, li.id DESC",
            (testo, q, q),
        ).fetchall()]


@router.get("/{lotto_id}/etichetta")
def etichetta_lotto(lotto_id: int):
    """Lista ingredienti + allergeni CALCOLATA dai consumi (nessuno snapshot)."""
    with connessione() as conn:
        esiste = conn.execute(
            "SELECT id FROM lotti_interni WHERE id = ?", (lotto_id,)
        ).fetchone()
        if not esiste:
            return {"errore": "Lotto interno non trovato"}
        risultato = etichetta(conn, lotto_id)
        # La quantità NON si mostra in etichetta: decide solo l'ordine.
        righe = [{"denominazione": r["denominazione"]} for r in risultato["righe"]]
        return {"righe": righe, "allergeni": risultato["allergeni"]}


class Consumo(BaseModel):
    origine: str          # 'ingresso' | 'interno'
    lotto_origine_id: int
    quantita_usata: float


class NuovaProduzione(BaseModel):
    prodotto_id: int
    data_produzione: str  # ISO YYYY-MM-DD
    data_scadenza: str
    qta_prodotta: float | None = None
    consumi: list[Consumo]


@router.post("", status_code=201)
def crea_produzione(dati: NuovaProduzione):
    """Salva il verbale: codice auto-generato + consumi indicati.

    TODO v0.1: proporre i consumi via FEFO partendo dalla ricetta,
    scaricare quantita_residua dei lotti consumati.
    """
    with connessione() as conn:
        prodotto = conn.execute(
            "SELECT * FROM prodotti WHERE id = ?", (dati.prodotto_id,)
        ).fetchone()
        if not prodotto:
            return {"errore": "Prodotto non trovato"}
        codice = genera_codice(conn, dict(prodotto), dati.data_produzione)
        cur = conn.execute(
            "INSERT INTO lotti_interni (prodotto_id, qta_prodotta, codice_lotto, "
            "data_produzione, data_scadenza) VALUES (?, ?, ?, ?, ?)",
            (dati.prodotto_id, dati.qta_prodotta, codice,
             dati.data_produzione, dati.data_scadenza),
        )
        lotto_id = cur.lastrowid
        for c in dati.consumi:
            conn.execute(
                "INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, "
                "quantita_usata) VALUES (?, ?, ?, ?)",
                (lotto_id, c.origine, c.lotto_origine_id, c.quantita_usata),
            )
        conn.commit()
        return {"id": lotto_id, "codice_lotto": codice}
