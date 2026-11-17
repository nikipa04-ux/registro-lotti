"""Ricette MASTER: da qui nasce ciò che si può produrre.

La ricetta è il documento di partenza (resa, righe, procedimento) e il
posto dove nasce la FAMIGLIA (regola di design: famiglia→ricetta).
Le produzioni sono SLAVE: ne leggono le righe e ne fotografano (snapshot)
la famiglia al momento della produzione.

Nessun tag fisso tipo "semilavorato": la famiglia è un'etichetta libera,
l'utente ne crea quante vuole. Un prodotto con ricetta è producibile;
senza ricetta non lo è, che abbia o no una famiglia.
"""
from .lotti import genera_codice  # noqa: F401  (usata dai test/seed)


class ErroreRicetta(ValueError):
    """Input respinto: il messaggio va mostrato all'utente così com'è."""


def lista_ricette(conn, testo=""):
    """Tutte le ricette, con prodotto, famiglia, resa e numero di righe."""
    q = f"%{testo.lower()}%"
    return [
        dict(r) for r in conn.execute(
            "SELECT r.id AS ricetta_id, r.prodotto_id, p.nome AS prodotto, "
            "p.sigla, p.unita_misura AS um, f.nome AS famiglia, r.resa, r.procedimento, "
            "(SELECT COUNT(*) FROM ricette_righe rr WHERE rr.ricetta_id = r.id) AS n_righe "
            "FROM ricette r "
            "JOIN prodotti p ON p.id = r.prodotto_id "
            "LEFT JOIN famiglie f ON f.id = r.famiglia_id "
            "WHERE ? = '' OR LOWER(p.nome) LIKE ? "
            "ORDER BY p.nome",
            (testo, q),
        ).fetchall()
    ]


def dettaglio_ricetta(conn, prodotto_id):
    """La ricetta completa di un prodotto (per dettaglio e modifica)."""
    ricetta = conn.execute(
        "SELECT r.*, f.nome AS famiglia "
        "FROM ricette r LEFT JOIN famiglie f ON f.id = r.famiglia_id "
        "WHERE r.prodotto_id = ?", (prodotto_id,)
    ).fetchone()
    if not ricetta:
        return None
    prodotto = conn.execute(
        "SELECT id, nome, sigla, unita_misura FROM prodotti WHERE id = ?",
        (prodotto_id,),
    ).fetchone()
    righe = [
        dict(r) for r in conn.execute(
            "SELECT rr.ingrediente_id, rr.quantita, p.nome, p.unita_misura AS um, "
            "fr.nome AS famiglia_ingrediente "
            "FROM ricette_righe rr "
            "JOIN prodotti p ON p.id = rr.ingrediente_id "
            "LEFT JOIN ricette ric ON ric.prodotto_id = rr.ingrediente_id "
            "LEFT JOIN famiglie fr ON fr.id = ric.famiglia_id "
            "WHERE rr.ricetta_id = ? ORDER BY rr.id",
            (ricetta["id"],),
        ).fetchall()
    ]
    return {
        "prodotto": dict(prodotto),
        "famiglia_id": ricetta["famiglia_id"],
        "famiglia": ricetta["famiglia"],
        "resa": ricetta["resa"],
        "procedimento": ricetta["procedimento"],
        "righe": righe,
    }


def crea_prodotto_lab(conn, dati):
    """Creazione rapida di un PRODOTTO DI LABORATORIO dalla modale ricetta.

    Nasce senza famiglia (gliela dà la ricetta) e senza lotti in ingresso
    (non è un ingrediente acquistato).
    """
    nome = (dati.get("nome") or "").strip()
    # L'u.m. del prodotto di laboratorio NON serve più: la resa della
    # ricetta ('5 kg') è già autosufficiente. Se arriva, la si tiene.
    um = (dati.get("unita_misura") or "").strip() or None
    if not nome:
        raise ErroreRicetta("Il nome del prodotto è obbligatorio")
    gia = conn.execute(
        "SELECT id FROM prodotti WHERE LOWER(nome) = LOWER(?)", (nome,)
    ).fetchone()
    if gia:
        raise ErroreRicetta(f"'{nome}' esiste già in anagrafica")
    conservazione = (dati.get("conservazione") or "").strip() or None
    if conservazione and conservazione not in ("Frigo", "Freezer", "Magazzino"):
        raise ErroreRicetta("Conservazione: Frigo, Freezer o Magazzino")
    cur = conn.execute(
        "INSERT INTO prodotti (nome, famiglia_id, conservazione, unita_misura, sigla) "
        "VALUES (?, NULL, ?, ?, ?)",
        (nome, conservazione, um, (dati.get("sigla") or "").strip().upper() or None),
    )
    return {
        "id": cur.lastrowid, "nome": nome, "sigla": (dati.get("sigla") or "").strip().upper() or None,
        "unita_misura": um, "famiglia": None, "conservazione": conservazione,
    }


def _risolvi_famiglia(conn, dati):
    """La famiglia nasce qui: id esistente OPPURE nome nuovo da creare."""
    famiglia_id = dati.get("famiglia_id")
    nome_nuovo = (dati.get("famiglia_nuova") or "").strip()
    if nome_nuovo:
        gia = conn.execute(
            "SELECT id FROM famiglie WHERE LOWER(nome) = LOWER(?)",
            (nome_nuovo,),
        ).fetchone()
        if gia:
            return gia["id"]
        cur = conn.execute("INSERT INTO famiglie (nome) VALUES (?)", (nome_nuovo,))
        return cur.lastrowid
    if famiglia_id:
        gia = conn.execute(
            "SELECT id FROM famiglie WHERE id = ?", (famiglia_id,)
        ).fetchone()
        if not gia:
            raise ErroreRicetta("Famiglia inesistente")
        return famiglia_id
    raise ErroreRicetta(
        "Scegli una famiglia (o scrivi il nome di una nuova): "
        "è il tag del prodotto e nasce dalla ricetta"
    )


def salva_ricetta(conn, dati):
    """Crea o aggiorna la ricetta di un prodotto (upsert: UNIQUE prodotto_id).

    dati: prodotto_id, famiglia_id | famiglia_nuova, resa?, procedimento?,
          righe [{ingrediente_id, quantita}]
    Le righe rimpiazzano le vecchie: la ricetta è il master.
    """
    prodotto_id = dati.get("prodotto_id")
    prodotto = conn.execute(
        "SELECT * FROM prodotti WHERE id = ?", (prodotto_id,)
    ).fetchone() if prodotto_id else None
    if not prodotto:
        raise ErroreRicetta("Prodotto inesistente")
    ha_arrivi = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_ingresso WHERE prodotto_id = ?",
        (prodotto_id,),
    ).fetchone()["n"]
    if ha_arrivi:
        raise ErroreRicetta(
            f'"{prodotto["nome"]}" ha lotti in arrivo: è un ingrediente '
            "acquistato, non si produce in negozio"
        )

    righe_in = dati.get("righe") or []
    if not righe_in:
        raise ErroreRicetta("Una ricetta senza ingredienti non è una ricetta")
    visti = set()
    for r in righe_in:
        ing = conn.execute(
            "SELECT id, nome FROM prodotti WHERE id = ?", (r.get("ingrediente_id"),)
        ).fetchone()
        if not ing:
            raise ErroreRicetta("Ingrediente inesistente in una riga della ricetta")
        try:
            qta = float(r.get("quantita"))
        except (TypeError, ValueError):
            qta = -1.0
        if qta <= 0:
            raise ErroreRicetta(
                f'Le quantità devono essere maggiori di zero: riga "{ing["nome"]}"'
            )
        if ing["id"] in visti:
            raise ErroreRicetta(
                f'"{ing["nome"]}" compare due volte: unisci le quantità in una riga'
            )
        visti.add(ing["id"])

    famiglia_id = _risolvi_famiglia(conn, dati)

    ricetta = conn.execute(
        "SELECT * FROM ricette WHERE prodotto_id = ?", (prodotto_id,)
    ).fetchone()
    if ricetta:
        conn.execute(
            "UPDATE ricette SET famiglia_id = ?, resa = ?, procedimento = ? "
            "WHERE id = ?",
            (famiglia_id, (dati.get("resa") or "").strip() or None,
             (dati.get("procedimento") or "").strip() or None, ricetta["id"]),
        )
        conn.execute("DELETE FROM ricette_righe WHERE ricetta_id = ?", (ricetta["id"],))
        ricetta_id = ricetta["id"]
    else:
        cur = conn.execute(
            "INSERT INTO ricette (prodotto_id, famiglia_id, resa, procedimento) "
            "VALUES (?, ?, ?, ?)",
            (prodotto_id, famiglia_id, (dati.get("resa") or "").strip() or None,
             (dati.get("procedimento") or "").strip() or None),
        )
        ricetta_id = cur.lastrowid
    for r in righe_in:
        conn.execute(
            "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
            "VALUES (?, ?, ?)",
            (ricetta_id, r["ingrediente_id"], float(r["quantita"])),
        )
    # La famiglia NASCE nella ricetta e l'anagrafica del prodotto la rispecchia
    # (così combo e filtri, che leggono l'anagrafica, la vedono subito).
    conn.execute(
        "UPDATE prodotti SET famiglia_id = ? WHERE id = ?", (famiglia_id, prodotto_id)
    )
    return dettaglio_ricetta(conn, prodotto_id)


def elimina_ricetta(conn, prodotto_id):
    """Eliminazione PROTETTA: se il prodotto ha produzioni, la ricetta è la
    master di un documento già registrato e non si tocca."""
    ha_prod = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_interni WHERE prodotto_id = ?",
        (prodotto_id,),
    ).fetchone()["n"]
    if ha_prod:
        raise ErroreRicetta(
            "Eliminazione protetta: il prodotto ha già produzioni registrate "
            "(la ricetta è il loro master)"
        )
    ricetta = conn.execute(
        "SELECT id FROM ricette WHERE prodotto_id = ?", (prodotto_id,)
    ).fetchone()
    if not ricetta:
        raise ErroreRicetta("Nessuna ricetta per questo prodotto")
    conn.execute("DELETE FROM ricette_righe WHERE ricetta_id = ?", (ricetta["id"],))
    conn.execute("DELETE FROM ricette WHERE id = ?", (ricetta["id"],))
    # Senza ricetta il prodotto non è più producibile: la famiglia, che era
    # nata qui, torna libera anche in anagrafica.
    conn.execute(
        "UPDATE prodotti SET famiglia_id = NULL WHERE id = ?", (prodotto_id,)
    )
