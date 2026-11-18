"""Produzioni: lotti interni, consumi (il verbale), etichetta calcolata.

La produzione è SLAVE della ricetta: la FEFO propone i consumi, l'operatore
al massimo corregge, il verbale finale sono i consumi salvati.
La ricetta non si tocca mai.
"""
from datetime import date

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..db import connessione
from ..logic.etichetta import etichetta
from ..logic.etichetta_pdf import (
    ErroreEtichetta,
    etichetta_pdf,
    nome_file_pdf,
)
from ..logic.produzioni import (
    ErroreProduzione,
    elimina_produzione,
    lotti_disponibili,
    proponi_produzione,
    registra_produzione,
)

router = APIRouter(prefix="/api/produzioni", tags=["produzioni"])


@router.get("/proposta")
def proposta(prodotto_id: int):
    """La ricetta propone: righe + lotti disponibili FEFO + consumo suggerito.

    L'UI mostra la proposta, l'operatore al massimo corregge.
    """
    with connessione() as conn:
        try:
            return proponi_produzione(conn, prodotto_id)
        except ErroreProduzione as e:
            raise HTTPException(422, str(e))


@router.get("/lotti")
def lotti_di_un_ingrediente(ingrediente_id: int):
    """Lotti utilizzabili di un ingrediente, ordinati FEFO (per le righe
    aggiunte fuori ricetta: stesso ordine con cui la proposta lavora)."""
    with connessione() as conn:
        return lotti_disponibili(conn, ingrediente_id)


@router.get("")
def lista_produzioni(testo: str = ""):
    """Ricerca per prodotto o lotto interno (una sola casella).

    'giorni' calcolato dal server: l'UI colora solo in base a quello.
    """
    q = f"%{testo.lower()}%"
    with connessione() as conn:
        righe = [dict(r) for r in conn.execute(
            "SELECT li.*, p.nome AS prodotto, f.nome AS famiglia "
            "FROM lotti_interni li "
            "JOIN prodotti p ON p.id = li.prodotto_id "
            "LEFT JOIN famiglie f ON f.id = li.famiglia_id "
            "WHERE ? = '' OR LOWER(p.nome) LIKE ? OR LOWER(li.codice_lotto) LIKE ? "
            "ORDER BY li.data_produzione DESC, li.id DESC",
            (testo, q, q),
        ).fetchall()]
        for r in righe:
            r["giorni"] = (date.fromisoformat(r["data_scadenza"]) - date.today()).days
            r["n_consumi"] = conn.execute(
                "SELECT COUNT(*) AS n FROM consumi WHERE lotto_interno_id = ?",
                (r["id"],),
            ).fetchone()["n"]
        return righe


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


@router.get("/{lotto_id}/etichetta.pdf")
def etichetta_pdf_lotto(lotto_id: int, copie: int = 8):
    """Il foglio A4 con la GRIGLIA di etichette da stampare e tagliare.

    2 colonne x 4 righe = 8 etichette per foglio; 'copie' decide quante
    (oltre 8 la pagina successiva arriva da sola). Il PDF nasce dalla
    sola libreria standard: nessuna dipendenza da installare.
    """
    with connessione() as conn:
        try:
            pdf = etichetta_pdf(conn, lotto_id, copie)
            codice = conn.execute(
                "SELECT codice_lotto AS c FROM lotti_interni WHERE id = ?",
                (lotto_id,),
            ).fetchone()["c"]
        except ErroreEtichetta as e:
            raise HTTPException(404, str(e))
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                    'inline; filename="%s"' % nome_file_pdf(codice),
            },
        )


@router.get("/{lotto_id}")
def dettaglio_produzione(lotto_id: int):
    """Lotto interno con tracciabilità INDIETRO (deriva da: i lotti consumati,
    con le quantità) e AVANTI (usato in), più l'etichetta calcolata."""
    with connessione() as conn:
        lotto = conn.execute(
            "SELECT li.*, p.nome AS prodotto, p.unita_misura AS um, f.nome AS famiglia "
            "FROM lotti_interni li "
            "JOIN prodotti p ON p.id = li.prodotto_id "
            "LEFT JOIN famiglie f ON f.id = li.famiglia_id "
            "WHERE li.id = ?", (lotto_id,),
        ).fetchone()
        if not lotto:
            return {"errore": "Lotto interno non trovato"}
        riga = dict(lotto)
        riga["giorni"] = (date.fromisoformat(riga["data_scadenza"]) - date.today()).days

        # INDIETRO: da dove viene (il verbale)
        deriva = conn.execute(
            "SELECT c.origine, c.lotto_origine_id, c.quantita_usata "
            "FROM consumi c WHERE c.lotto_interno_id = ?",
            (lotto_id,),
        ).fetchall()
        deriva_da = []
        for c in deriva:
            if c["origine"] == "ingresso":
                src = conn.execute(
                    "SELECT li.codice_lotto, p.nome AS ingrediente, p.unita_misura AS um, "
                    "f.nome AS fornitore FROM lotti_ingresso li "
                    "JOIN prodotti p ON p.id = li.prodotto_id "
                    "JOIN fornitori f ON f.id = li.fornitore_id WHERE li.id = ?",
                    (c["lotto_origine_id"],),
                ).fetchone()
                tipo = "arrivo"
            else:
                src = conn.execute(
                    "SELECT li.codice_lotto, p.nome AS ingrediente, p.unita_misura AS um, "
                    "NULL AS fornitore FROM lotti_interni li "
                    "JOIN prodotti p ON p.id = li.prodotto_id WHERE li.id = ?",
                    (c["lotto_origine_id"],),
                ).fetchone()
                tipo = "produzione interna"
            if src:
                deriva_da.append({**dict(src), "origine": tipo, "quantita_usata": c["quantita_usata"]})

        # AVANTI: chi ha consumato questo lotto
        usato_in = [dict(u) for u in conn.execute(
            "SELECT li.id, li.codice_lotto, li.data_produzione, c.quantita_usata "
            "FROM consumi c JOIN lotti_interni li ON li.id = c.lotto_interno_id "
            "WHERE c.origine = 'interno' AND c.lotto_origine_id = ?",
            (lotto_id,),
        ).fetchall()]

        risultato = etichetta(conn, lotto_id)
        return {
            "lotto": riga,
            "deriva_da": deriva_da,
            "usato_in": usato_in,
            "etichetta": {
                "righe": [{"denominazione": r["denominazione"]} for r in risultato["righe"]],
                "allergeni": risultato["allergeni"],
            },
        }


class Consumo(BaseModel):
    origine: str          # 'ingresso' | 'interno'
    lotto_origine_id: int
    quantita_usata: float


class NuovaProduzione(BaseModel):
    prodotto_id: int
    data_produzione: str  # ISO YYYY-MM-DD
    data_scadenza: str
    qta_prodotta: float | None = None
    famiglia_id: int | None = None
    consumi: list[Consumo]


@router.post("", status_code=201)
def crea_produzione(dati: NuovaProduzione):
    """Salva il verbale: codice auto-generato, consumi indicati,
    SCARICO della residua dei lotti in ingresso consumati."""
    with connessione() as conn:
        try:
            lotto = registra_produzione(conn, dati.model_dump())
        except ErroreProduzione as e:
            # Nessuna scrittura parziale: il with esce con l'eccezione e annulla
            raise HTTPException(422, str(e))
        conn.commit()
        return lotto


@router.delete("/{lotto_id}", status_code=204)
def elimina(lotto_id: int):
    """Eliminazione protetta: rifiutata se il lotto è usato in altre
    produzioni; altrimenti ripristina le giacenze dei lotti consumati."""
    with connessione() as conn:
        try:
            elimina_produzione(conn, lotto_id)
        except ErroreProduzione as e:
            raise HTTPException(422, str(e))
        conn.commit()
