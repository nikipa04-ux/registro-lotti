"""Dashboard: il quadro riassuntivo della giornata, TUTTO calcolato.

Stessa logica del prototipo: lotti in scadenza entro 7 giorni (sia ingressi
con giacenza sia produzioni interne), ordinati per urgenza; tre contatori
(scadenze critiche <=3 giorni, arrivi ultima settimana, produzioni totali).
"""
from datetime import date, timedelta


def _giorni_a(data_iso, oggi):
    """Giorni interi che mancano alla scadenza (negativo = scaduto)."""
    return (date.fromisoformat(data_iso) - oggi).days


def calcola_dashboard(conn, oggi=None):
    """Ritorna stats e lista delle scadenze imminenti.

      stats.scadenze_critiche: scadenze <=3 giorni e non scadute
      stats.arrivi_settimana: arrivi degli ultimi 7 giorni
      stats.produzioni: produzioni interne registrate
      in_scadenza: [{prodotto, lotto, origine, fornitore, scadenza, giorni}]
    """
    oggi = oggi or date.today()
    tra = (oggi + timedelta(days=7)).isoformat()

    # Lotti in ingresso con giacenza, in scadenza entro 7 giorni
    ingressi = conn.execute(
        "SELECT p.nome AS prodotto, li.codice_lotto AS lotto, "
        "f.nome AS fornitore, li.data_scadenza AS scadenza "
        "FROM lotti_ingresso li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE li.quantita_residua > 0 "
        "AND li.data_scadenza >= ? AND li.data_scadenza <= ?",
        (oggi.isoformat(), tra),
    ).fetchall()

    # Lotti interni in scadenza entro 7 giorni (le produzioni non hanno
    # giacenza: la data di scadenza decide se sono ancora utilizzabili)
    interni = conn.execute(
        "SELECT p.nome AS prodotto, li.codice_lotto AS lotto, "
        "NULL AS fornitore, li.data_scadenza AS scadenza "
        "FROM lotti_interni li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "WHERE li.data_scadenza >= ? AND li.data_scadenza <= ?",
        (oggi.isoformat(), tra),
    ).fetchall()

    righe = []
    for r in list(ingressi) + list(interni):
        righe.append({
            "prodotto": r["prodotto"],
            "lotto": r["lotto"],
            "origine": "ingresso" if r["fornitore"] is not None else "interno",
            "fornitore": r["fornitore"] or "produzione interna",
            "scadenza": r["scadenza"],
            "giorni": _giorni_a(r["scadenza"], oggi),
        })
    righe.sort(key=lambda r: r["scadenza"])

    settimana_fa = (oggi - timedelta(days=7)).isoformat()
    return {
        "oggi": oggi.isoformat(),
        "stats": {
            "scadenze_critiche": sum(1 for r in righe if r["giorni"] <= 3),
            "arrivi_settimana": conn.execute(
                "SELECT COUNT(*) FROM lotti_ingresso WHERE data_arrivo >= ?",
                (settimana_fa,),
            ).fetchone()[0],
            "produzioni": conn.execute(
                "SELECT COUNT(*) FROM lotti_interni"
            ).fetchone()[0],
        },
        "in_scadenza": righe,
    }
