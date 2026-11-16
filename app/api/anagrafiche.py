"""Anagrafiche: fornitori, prodotti (ingredienti + laboratorio), famiglie, allergeni.

Regola: i prodotti di laboratorio NON dichiarano allergeni: li ereditano
dalla ricetta. Qui si serve solo ciò che l'anagrafica possiede.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connessione

router = APIRouter(prefix="/api/anagrafiche", tags=["anagrafiche"])


@router.get("/fornitori")
def lista_fornitori():
    with connessione() as conn:
        return [
            dict(r) for r in conn.execute(
                "SELECT f.*, COUNT(li.id) AS n_arrivi FROM fornitori f "
                "LEFT JOIN lotti_ingresso li ON li.fornitore_id = f.id "
                "GROUP BY f.id ORDER BY f.nome"
            ).fetchall()
        ]


@router.get("/prodotti")
def lista_prodotti(ingrediente: bool | None = None):
    """Un'unica tabella, due identità: ingrediente=True filtra famiglia NULL."""
    with connessione() as conn:
        sql = ("SELECT p.*, f.nome AS famiglia FROM prodotti p "
               "LEFT JOIN famiglie f ON f.id = p.famiglia_id")
        if ingrediente is True:
            sql += " WHERE p.famiglia_id IS NULL"
        elif ingrediente is False:
            sql += " WHERE p.famiglia_id IS NOT NULL"
        return [dict(r) for r in conn.execute(sql + " ORDER BY p.nome").fetchall()]


@router.get("/famiglie")
def lista_famiglie():
    with connessione() as conn:
        return [
            dict(r) for r in conn.execute(
                "SELECT f.*, (SELECT COUNT(*) FROM prodotti p "
                "WHERE p.famiglia_id = f.id) AS n_prodotti "
                "FROM famiglie f ORDER BY f.nome"
            ).fetchall()
        ]


@router.get("/allergeni")
def lista_allergeni():
    """I 14 allergeni obbligatori (Reg. UE 1169/2011), già a database."""
    with connessione() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM allergeni ORDER BY id").fetchall()]


class NuovoFornitore(BaseModel):
    nome: str
    piva: str | None = None
    telefono: str | None = None
    email: str | None = None
    note: str | None = None


@router.post("/fornitori", status_code=201)
def crea_fornitore(dati: NuovoFornitore):
    with connessione() as conn:
        cur = conn.execute(
            "INSERT INTO fornitori (nome, piva, telefono, email, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (dati.nome.strip(), dati.piva, dati.telefono, dati.email, dati.note),
        )
        conn.commit()
        return {"id": cur.lastrowid, **dati.model_dump()}


class NuovaFamiglia(BaseModel):
    nome: str


@router.post("/famiglie", status_code=201)
def crea_famiglia(dati: NuovaFamiglia):
    """Eliminazione protetta: la famiglia si cancella solo se nessun prodotto la usa."""
    with connessione() as conn:
        cur = conn.execute(
            "INSERT INTO famiglie (nome) VALUES (?)", (dati.nome.strip(),)
        )
        conn.commit()
        return {"id": cur.lastrowid, "nome": dati.nome.strip()}


@router.delete("/famiglie/{famiglia_id}", status_code=204)
def elimina_famiglia(famiglia_id: int):
    """Protegge: rifiuta se un prodotto (o ricetta) usa ancora la famiglia."""
    with connessione() as conn:
        usata = conn.execute(
            "SELECT COUNT(*) AS n FROM prodotti WHERE famiglia_id = ?",
            (famiglia_id,),
        ).fetchone()["n"]
        if usata:
            raise HTTPException(409, f"Famiglia in uso da {usata} prodotti: eliminazione bloccata")
        conn.execute("DELETE FROM famiglie WHERE id = ?", (famiglia_id,))
        conn.commit()
