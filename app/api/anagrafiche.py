"""Anagrafiche: fornitori, prodotti (ingredienti + laboratorio), famiglie, allergeni.

Regola: i prodotti di laboratorio NON dichiarano allergeni: li ereditano
dalla ricetta. Qui si serve solo ciò che l'anagrafica possiede; la famiglia
nasce nella ricetta (master) e in anagrafica non si tocca.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connessione
from ..logic.anagrafiche import (
    ErroreAnagrafica,
    crea_ingrediente,
    crea_unita,
    dettaglio_fornitore,
    dettaglio_prodotto,
    elimina_fornitore,
    elimina_prodotto,
    elimina_unita,
    lista_ingredienti,
    lista_prodotti as lista_prodotti_lab,
    lista_unita,
    rinomina_famiglia,
    rinomina_unita,
    salva_fornitore,
    salva_prodotto,
)

router = APIRouter(prefix="/api/anagrafiche", tags=["anagrafiche"])


def _errore(e: ErroreAnagrafica):
    raise HTTPException(422, str(e))


@router.get("/fornitori")
def lista_fornitori(testo: str = ""):
    """Con n_arrivi: per la card Anagrafiche e per le combo."""
    with connessione() as conn:
        q = (testo or "").strip().lower()
        return [
            dict(r) for r in conn.execute(
                "SELECT f.*, COUNT(li.id) AS n_arrivi FROM fornitori f "
                "LEFT JOIN lotti_ingresso li ON li.fornitore_id = f.id "
                "GROUP BY f.id ORDER BY f.nome"
            ).fetchall()
            if not q or q in r["nome"].lower()
        ]


@router.get("/ingredienti")
def ingredienti(testo: str = ""):
    """Card 🛒: ingredienti con allergeni dichiarati e n. arrivi."""
    with connessione() as conn:
        return lista_ingredienti(conn, testo)


@router.get("/prodotti-lab")
def prodotti_lab(testo: str = "", famiglia_id: int = 0):
    """Card 🥣: prodotti di laboratorio, allergeni EREDITATI dalla ricetta."""
    with connessione() as conn:
        # NB: qui serve la FUNZIONE della logica, non l'endpoint /prodotti
        # (stesso nome nel modulo): per questo l'import è con alias.
        return lista_prodotti_lab(conn, testo, famiglia_id)


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


# ---- creazione rapida (dalle combo di altre sezioni) ----

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


class NuovoProdotto(BaseModel):
    nome: str
    conservazione: str
    unita_misura: str
    sigla: str | None = None
    marca: str | None = None
    denominazione_legale: str | None = None
    allergeni: list[int] = []


@router.post("/prodotti", status_code=201)
def crea_prodotto(dati: NuovoProdotto):
    """Creazione rapida INGREDIENTE (famiglia NULL) dalle combo delle altre
    schermate. Qui nascono i dati dell'anagrafica (conservazione, u.m.,
    denominazione legale, allergeni): il resto si completa in Anagrafiche.
    I prodotti di laboratorio NON nascono qui: la loro anagrafica è
    la ricetta.
    """
    with connessione() as conn:
        try:
            p = crea_ingrediente(conn, dati.model_dump(), da_anagrafica=False)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return p


# ---- il modulo Anagrafiche ----

class NuovoIngrediente(BaseModel):
    nome: str
    conservazione: str
    unita_misura: str
    sigla: str | None = None
    marca: str | None = None
    denominazione_legale: str | None = None
    note: str | None = None
    allergeni: list[int] = []


@router.post("/ingredienti", status_code=201)
def nuovo_ingrediente(dati: NuovoIngrediente):
    """Il "+ Nuovo" della card Ingredienti: qui la denominazione legale è
    OBBLIGATORIA (finisce nell'etichetta dei prodotti finiti)."""
    with connessione() as conn:
        try:
            p = crea_ingrediente(conn, dati.model_dump(), da_anagrafica=True)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return p


class SalvaProdotto(BaseModel):
    nome: str
    conservazione: str | None = None
    unita_misura: str
    sigla: str | None = None
    marca: str | None = None
    denominazione_legale: str | None = None
    note: str | None = None
    allergeni: list[int] | None = None


@router.get("/prodotti/{prodotto_id}")
def scheda_prodotto(prodotto_id: int):
    with connessione() as conn:
        try:
            return dettaglio_prodotto(conn, prodotto_id)
        except ErroreAnagrafica as e:
            _errore(e)


@router.put("/prodotti/{prodotto_id}")
def modifica_prodotto(prodotto_id: int, dati: SalvaProdotto):
    with connessione() as conn:
        try:
            p = salva_prodotto(conn, {"id": prodotto_id, **dati.model_dump()})
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return p


@router.delete("/prodotti/{prodotto_id}", status_code=204)
def elimina_prodotto_r(prodotto_id: int):
    """Eliminazione protetta: rifiutata se ci sono arrivi, produzioni
    o una ricetta che la usa."""
    with connessione() as conn:
        try:
            elimina_prodotto(conn, prodotto_id)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()


class SalvaFornitore(BaseModel):
    nome: str
    piva: str | None = None
    telefono: str | None = None
    email: str | None = None
    note: str | None = None


@router.get("/fornitori/{fornitore_id}")
def scheda_fornitore(fornitore_id: int):
    with connessione() as conn:
        try:
            return dettaglio_fornitore(conn, fornitore_id)
        except ErroreAnagrafica as e:
            _errore(e)


@router.put("/fornitori/{fornitore_id}")
def modifica_fornitore(fornitore_id: int, dati: SalvaFornitore):
    with connessione() as conn:
        try:
            f = salva_fornitore(conn, {"id": fornitore_id, **dati.model_dump()})
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return f


@router.delete("/fornitori/{fornitore_id}", status_code=204)
def elimina_fornitore_r(fornitore_id: int):
    """Eliminazione protetta: rifiutata se ha arrivi registrati."""
    with connessione() as conn:
        try:
            elimina_fornitore(conn, fornitore_id)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()


class RinominaFamiglia(BaseModel):
    nome: str


@router.put("/famiglie/{famiglia_id}")
def rinomina(famiglia_id: int, dati: RinominaFamiglia):
    """Rinomina inline della famiglia: si propaga ovunque (tutto JOINa per id)."""
    with connessione() as conn:
        try:
            f = rinomina_famiglia(conn, famiglia_id, dati.nome)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return f


class NuovaFamiglia(BaseModel):
    nome: str


@router.post("/famiglie", status_code=201)
def crea_famiglia(dati: NuovaFamiglia):
    with connessione() as conn:
        nome = dati.nome.strip()
        if not nome:
            raise HTTPException(422, "Il nome della famiglia è obbligatorio")
        dup = conn.execute(
            "SELECT id FROM famiglie WHERE LOWER(nome) = LOWER(?)", (nome,)
        ).fetchone()
        if dup:
            raise HTTPException(422, "Esiste già una famiglia con questo nome")
        cur = conn.execute("INSERT INTO famiglie (nome) VALUES (?)", (nome,))
        conn.commit()
        return {"id": cur.lastrowid, "nome": nome}


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


# ---- Unità di misura (RIFIN 34) ----
# Le 4 di sistema (g/kg/ml/lt) sono protette dalla LOGIC: alimentano le
# conversioni di um.py. Rinominare una u.m. libera propaga il nome ai
# prodotti che la usano; i lotti prodotti restano con lo snapshot storico.

@router.get("/unita-misura")
def lista_unita_misura():
    with connessione() as conn:
        return lista_unita(conn)


class NuovaUnita(BaseModel):
    nome: str


@router.post("/unita-misura", status_code=201)
def crea_unita_misura(dati: NuovaUnita):
    with connessione() as conn:
        try:
            u = crea_unita(conn, dati.nome)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return u


class RinominaUnita(BaseModel):
    nome: str


@router.put("/unita-misura/{unita_id}")
def rinomina_unita_misura(unita_id: int, dati: RinominaUnita):
    with connessione() as conn:
        try:
            u = rinomina_unita(conn, unita_id, dati.nome)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
        return u


@router.delete("/unita-misura/{unita_id}", status_code=204)
def elimina_unita_misura(unita_id: int):
    with connessione() as conn:
        try:
            elimina_unita(conn, unita_id)
        except ErroreAnagrafica as e:
            _errore(e)
        conn.commit()
