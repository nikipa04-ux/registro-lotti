"""Food cost: lo storico prezzi NON si inserisce a mano.

Nasce dagli arrivi: data + prezzo unitario. Il costo di un ingrediente
è il prezzo dell'ultimo arrivo; il costo di un semilavorato/prodotto
si calcola dalla ricetta (ricorsione con cache, per catene lunghe).
"""


def costo_unita_ingrediente(conn, prodotto_id, alla_data=None):
    """Prezzo unitario dell'ultimo arrivo (opzionalmente fino a una data)."""
    if alla_data:
        riga = conn.execute(
            "SELECT prezzo_unitario FROM lotti_ingresso "
            "WHERE prodotto_id = ? AND data_arrivo <= ? "
            "ORDER BY data_arrivo DESC, id DESC LIMIT 1",
            (prodotto_id, alla_data),
        ).fetchone()
    else:
        riga = conn.execute(
            "SELECT prezzo_unitario FROM lotti_ingresso "
            "WHERE prodotto_id = ? ORDER BY data_arrivo DESC, id DESC LIMIT 1",
            (prodotto_id,),
        ).fetchone()
    return riga["prezzo_unitario"] if riga else None


def costo_ricetta(conn, ricetta_id, cache=None, alla_data=None):
    """Costo della dose base della ricetta, ricorsivo sui semilavorati.

    TODO v0.1 avanzata: conversioni fra u.m. (prodotto in kg usato in g):
    per ora le quantità si sommano solo quando le u.m. coincidono,
    la conversione esplicita arriva con logic.um.
    """
    cache = {} if cache is None else cache
    if ricetta_id in cache:
        return cache[ricetta_id]
    tot = 0.0
    righe = conn.execute(
        "SELECT ingrediente_id, quantita FROM ricette_righe WHERE ricetta_id = ?",
        (ricetta_id,),
    ).fetchall()
    for r in righe:
        sub = conn.execute(
            "SELECT id FROM ricette WHERE prodotto_id = ?", (r["ingrediente_id"],)
        ).fetchone()
        if sub:
            # Semilavorato: costo per unità = costo dose / resa numerica
            resa = conn.execute(
                "SELECT resa FROM ricette WHERE id = ?", (sub["id"],)
            ).fetchone()["resa"]
            numero = _resa(resa)
            if numero:
                tot += (costo_ricetta(conn, sub["id"], cache, alla_data) / numero) * r["quantita"]
        else:
            prezzo = costo_unita_ingrediente(conn, r["ingrediente_id"], alla_data)
            if prezzo is not None:
                tot += prezzo * r["quantita"]
    cache[ricetta_id] = tot
    return tot


def _resa(resa):
    if not resa:
        return None
    try:
        return float(resa.split()[0].replace(",", "."))
    except (ValueError, IndexError):
        return None
