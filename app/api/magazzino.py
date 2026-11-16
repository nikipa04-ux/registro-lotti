"""Magazzino e scadenze: tutto CALCOLATO dalle registrazioni.

Nessuna giacenza si inserisce a mano: è arrivo meno consumi.
"""
from fastapi import APIRouter

from ..db import connessione

router = APIRouter(prefix="/api/magazzino", tags=["magazzino"])


@router.get("")
def giacenze():
    """Giacenza per prodotto e marca: righe figlie quando ci sono più marche.

    TODO v0.1: chip filtro conservazione, colonna 'da ordinare'
    (giacenza vs consumo medio della cadenza arrivi).
    """
    with connessione() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT p.id AS prodotto_id, p.nome, p.conservazione, "
            "COALESCE(li.marca, p.marca, '—') AS marca, p.unita_misura AS um, "
            "SUM(li.quantita_residua) AS giacenza, COUNT(li.id) AS n_lotti "
            "FROM lotti_ingresso li JOIN prodotti p ON p.id = li.prodotto_id "
            "WHERE li.quantita_residua > 0 "
            "GROUP BY p.id, COALESCE(li.marca, p.marca, '—') "
            "ORDER BY p.nome",
        ).fetchall()]


@router.get("/scadenze")
def scadenze(giorni: int = 30):
    """Lotti in ingresso che scadono entro N giorni, in ordine FEFO."""
    with connessione() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT li.id, p.nome AS prodotto, li.marca, li.codice_lotto, "
            "li.data_scadenza, li.quantita_residua, p.unita_misura AS um, f.nome AS fornitore "
            "FROM lotti_ingresso li "
            "JOIN prodotti p ON p.id = li.prodotto_id "
            "JOIN fornitori f ON f.id = li.fornitore_id "
            "WHERE li.quantita_residua > 0 "
            "AND julianday(li.data_scadenza) <= julianday('now', ?) "
            "ORDER BY li.data_scadenza",
            (f"+{giorni} days",),
        ).fetchall()]
