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
- RIFIN 44, ingredienti COMPOSTI: un ingrediente acquistato come il
  cioccolato e' a sua volta composto di piu' ingredienti; la sua
  denominazione legale contiene SOLO le parti separate da virgola
  ('zucchero, pasta di cacao, burro di cacao'). In etichetta ogni parte
  diventa una RIGA DISTINTA appiattita con le altre (il nome del composto
  non compare: conta chi c'e' dentro), e i DOPPIONI si eliminano: parti
  uguali scritte uguale (senza badare a maiuscole) compaiono UNA volta
  sola. L'ingrediente in anagrafica resta uno, con il suo nome singolo.
"""


def parti_denominazione(denominazione):
    """Le parti di una denominazione legale, splittate sulla virgola.

    Denominazione semplice ('Latte fresco pastorizzato') -> 1 elemento.
    Denominazione COMPOSTA ('zucchero, pasta di cacao, burro di cacao')
    -> i singoli ingredienti del composto, in ordine di dichiarazione.
    Vuoi spazi e parti vuote vengono via; le maiuscole non contano per il
    confronto (chi confronta usa .casefold()).
    """
    return [p.strip() for p in (denominazione or "").split(",") if p.strip()]


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
                 di quantità (che NON si mostra: ordina soltanto). Un
                 ingrediente COMPOSTO (denominazione con virgole) si
                 espande: una riga per parte, appiattita con le altre
                 (RIFIN 44), senza doppioni (prima occorrenza vince:
                 le parti dell'ingrediente piu' pesante restano davanti)
      allergeni: [nomi] ordinati alfabeticamente, dichiarati dagli
                 ingredienti D'ORIGINE (anche se una parte deduplica via:
                 chi c'e' dentro conta, ma l'allergene si e' comunque usato)
    """
    accumulo = ingredienti_lotto(conn, lotto_interno_id)

    # prima gli ingredienti: nome e denominazione, in ordine di peso
    ordinati = []
    for pid, qta in accumulo.items():
        p = conn.execute(
            "SELECT nome, denominazione_legale FROM prodotti WHERE id = ?", (pid,)
        ).fetchone()
        if p is not None:
            ordinati.append((pid, qta, p["nome"], p["denominazione_legale"]))
    ordinati.sort(key=lambda t: -t[1])

    # poi le RIGHE: una per denominazione, con i composti SPLITTATI in
    # parti distinte (nessun doppione: si confronta senza maiuscole)
    righe = []
    visti = set()
    for pid, qta, nome, denominazione in ordinati:
        parti = parti_denominazione(denominazione)
        if len(parti) >= 2:
            # ingrediente composto: appaiono le PARTI, il nome sparisce
            elementi = [(parte, pid) for parte in parti]
        elif parti:
            # denominazione semplice: resta la denominazione legale
            elementi = [(parti[0], pid)]
        else:
            # niente denominazione: vale il nome dell'ingrediente
            elementi = [(nome, pid)]
        for testo, _pid in elementi:
            chiave = testo.casefold()
            if chiave in visti:
                continue
            visti.add(chiave)
            righe.append({"prodotto_id": pid, "denominazione": testo, "qta": qta})

    # gli allergeni si dichiarano sugli ingredienti ORIGINE, non sulle
    # righe: anche un composto tutto deduplicato ha comunque messo i suoi
    # allergeni dentro il prodotto finito
    nomi_allergeni = set()
    for pid in accumulo:
        for a in conn.execute(
            "SELECT al.nome FROM allergeni al "
            "JOIN prodotti_allergeni pa ON pa.allergene_id = al.id "
            "WHERE pa.prodotto_id = ?",
            (pid,),
        ).fetchall():
            nomi_allergeni.add(a["nome"])
    return {"righe": righe, "allergeni": sorted(nomi_allergeni)}
