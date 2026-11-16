"""Assegnazione FEFO (First Expired, First Out).

FEFO PROPOSTA, l'operatore conferma: al massimo corregge. La UI mostra
i 2 lotti migliori, il resto si trova via typeahead. Mai liste di checkbox.
"""


def ordina_fefo(lotti):
    """Ordina i lotti utilizzabili per scadenza crescente, poi per arrivo.

    Esclude i lotti esauriti (quantita_residua <= 0).
    Ogni lotto: dict con data_scadenza, data_arrivo, quantita_residua.
    """
    utilizzabili = [l for l in lotti if (l.get("quantita_residua") or 0) > 0]
    return sorted(
        utilizzabili,
        key=lambda l: (l["data_scadenza"], l.get("data_arrivo") or ""),
    )


def copertura_fefo(lotti, qta_richiesta):
    """Distribuisce la quantità richiesta sui lotti in ordine FEFO.

    Ritorna (assegnazioni, copertura):
      assegnazioni: lista di {lotto, quantita} in ordine di consumo
      copertura:     quantità totale coperta (<= qta_richiesta se manca merce)
    """
    assegnazioni = []
    residuo = qta_richiesta
    for lotto in ordina_fefo(lotti):
        if residuo <= 0:
            break
        presa = min(residuo, lotto["quantita_residua"])
        assegnazioni.append({"lotto": lotto, "quantita": presa})
        residuo -= presa
    return assegnazioni, qta_richiesta - residuo
