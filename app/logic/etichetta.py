"""Etichetta ingredienti CALCOLATA dal verbale (opzione A, 13/11/2026).

La lista NON si salva in nessuna tabella: si calcola ogni volta partendo
dai consumi del lotto interno e scendendo per ricorsione lungo i lotti
interni consumati (la crema pasticcera dentro il bignè).

Regole:
- FUSIONE per ingrediente d'origine: le uova nella crema + le uova dirette
  compaiono in UNA riga sola, con quantità sommata. Mai duplicati.
- La quantità NON si mostra in etichetta (non serve): decide solo l'ORDINE
  delle righe, per legge decrescente di peso all'uso (Reg. UE 1169/2011).
- Denominazione legale dell'ingrediente (o il nome come fallback).
- Gli allergeni viaggiano insieme: un'unica funzione li restituisce.
"""


def _resa_numerica(resa):
    """Estrae il numero dalla resa testuale della ricetta ('5 kg' -> 5.0)."""
    if not resa:
        return None
    parti = resa.split()
    try:
        return float(parti[0].replace(",", "."))
    except ValueError:
        return None


def ingredienti_lotto(conn, lotto_interno_id, accumulo=None, fattore=1.0):
    """Accumula gli ingredienti d'origine del lotto, per ricorsione.

    Ritorna un dict {prodotto_id: quantita_totale} con la fusione già fatta.
    """
    if accumulo is None:
        accumulo = {}
    righe = conn.execute(
        "SELECT origine, lotto_origine_id, quantita_usata "
        "FROM consumi WHERE lotto_interno_id = ?",
        (lotto_interno_id,),
    ).fetchall()
    for r in righe:
        usata = r["quantita_usata"] or 0.0
        if r["origine"] == "ingresso":
            lotto = conn.execute(
                "SELECT prodotto_id FROM lotti_ingresso WHERE id = ?",
                (r["lotto_origine_id"],),
            ).fetchone()
            if lotto is None:
                continue
            accumulo[lotto["prodotto_id"]] = (
                accumulo.get(lotto["prodotto_id"], 0.0) + usata * fattore
            )
        else:
            # Lotto interno consumato: si scala per la frazione usata,
            # dividendo per la quantità PRODOTTA del lotto (qta_prodotta).
            lotto = conn.execute(
                "SELECT prodotto_id, qta_prodotta FROM lotti_interni WHERE id = ?",
                (r["lotto_origine_id"],),
            ).fetchone()
            if lotto is None:
                continue
            prodotta = lotto["qta_prodotta"]
            if not prodotta:
                # Fallback: resa della ricetta del prodotto di quel lotto
                ricetta = conn.execute(
                    "SELECT resa FROM ricette WHERE prodotto_id = ?",
                    (lotto["prodotto_id"],),
                ).fetchone()
                prodotta = _resa_numerica(ricetta["resa"] if ricetta else None) or 1.0
            ingredienti_lotto(
                conn, r["lotto_origine_id"], accumulo, fattore * (usata / prodotta)
            )
    return accumulo


def etichetta(conn, lotto_interno_id):
    """Composizione dell'etichetta: righe ordinate + allergeni.

    Ritorna dict:
      righe:     [{prodotto_id, denominazione, qta}] in ordine decrescente
                 di quantità (che NON si mostra: ordina soltanto)
      allergeni: [nomi] ordinati alfabeticamente
    """
    accumulo = ingredienti_lotto(conn, lotto_interno_id)
    righe = []
    for pid, qta in accumulo.items():
        p = conn.execute(
            "SELECT nome, denominazione_legale FROM prodotti WHERE id = ?", (pid,)
        ).fetchone()
        if p is None:
            continue
        righe.append({
            "prodotto_id": pid,
            "denominazione": p["denominazione_legale"] or p["nome"],
            "qta": qta,
        })
    righe.sort(key=lambda r: -r["qta"])

    nomi_allergeni = set()
    for r in righe:
        for a in conn.execute(
            "SELECT al.nome FROM allergeni al "
            "JOIN prodotti_allergeni pa ON pa.allergene_id = al.id "
            "WHERE pa.prodotto_id = ?",
            (r["prodotto_id"],),
        ).fetchall():
            nomi_allergeni.add(a["nome"])
    return {"righe": righe, "allergeni": sorted(nomi_allergeni)}
