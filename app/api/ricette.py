"""Ricette: il MASTER delle produzioni. Lista, dettaglio, salvataggio.

Le regole vivono in app/logic/ricette.py; qui si ricevono le richieste.
Route /candidati dichiarata PRIMA di /{prodotto_id} (FastAPI fa match dei
path param per ordine di dichiarazione).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connessione
from ..logic.ricette import (
    ErroreRicetta,
    candidati,
    dettaglio_ricetta,
    elimina_ricetta,
    lista_ricette,
    salva_ricetta,
)

router = APIRouter(prefix="/api/ricette", tags=["ricette"])


@router.get("")
def lista(testo: str = ""):
    """Tutte le ricette (ricerca per nome prodotto)."""
    with connessione() as conn:
        return lista_ricette(conn, testo)


@router.get("/candidati")
def prodotti_candidati():
    """Prodotti a cui si può dare una ricetta (senza una e senza arrivi)."""
    with connessione() as conn:
        return candidati(conn)


@router.get("/{prodotto_id}")
def dettaglio(prodotto_id: int):
    """La ricetta di un prodotto, con le righe complete."""
    with connessione() as conn:
        r = dettaglio_ricetta(conn, prodotto_id)
        if not r:
            return {"errore": "Nessuna ricetta per questo prodotto"}
        return r


class NuovoProdottoLab(BaseModel):
    nome: str
    unita_misura: str
    sigla: str | None = None
    conservazione: str | None = None


@router.post("/nuovo-prodotto", status_code=201)
def crea_prodotto_lab(dati: NuovoProdottoLab):
    """Creazione rapida PRODOTTO DI LABORATORIO dalla modale ricetta.
    Nasce senza famiglia: gliela dà la ricetta che lo aspetta
    (se l'operatore annulla, il prodotto resta in anagrafica come tale)."""
    from ..logic.ricette import crea_prodotto_lab as _crea

    try:
        with connessione() as conn:
            p = _crea(conn, dati.model_dump())
            conn.commit()
            return p
    except ErroreRicetta as e:
        raise HTTPException(422, str(e))


class RigaRicetta(BaseModel):
    ingrediente_id: int
    quantita: float


class RicettaIn(BaseModel):
    prodotto_id: int
    famiglia_id: int | None = None
    famiglia_nuova: str | None = None   # se compilato, la famiglia nasce qui
    resa: str | None = None
    procedimento: str | None = None
    righe: list[RigaRicetta]


@router.post("", status_code=201)
def salva(dati: RicettaIn):
    """Crea o aggiorna la ricetta (upsert per prodotto)."""
    with connessione() as conn:
        try:
            r = salva_ricetta(conn, dati.model_dump())
        except ErroreRicetta as e:
            raise HTTPException(422, str(e))
        conn.commit()
        return r


@router.delete("/{prodotto_id}", status_code=204)
def elimina(prodotto_id: int):
    """Eliminazione protetta: rifiutata se il prodotto ha produzioni."""
    with connessione() as conn:
        try:
            elimina_ricetta(conn, prodotto_id)
        except ErroreRicetta as e:
            raise HTTPException(422, str(e))
        conn.commit()
