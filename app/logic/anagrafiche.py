"""Anagrafiche: la casa dei dati che nascono qui.

Regole di design (fisse):
- i dati si chiedono DOVE nascono: la conservazione e la denominazione legale
  nascono con l'INGREDIENTE, i contatti con il FORNITORE, la famiglia con la
  RICETTA (master). In anagrafiche la famiglia NON si tocca.
- i prodotti di laboratorio NON dichiarano allergeni: li EREDITANO dalla
  ricetta (unione ricorsiva, calcolata qui, mai salvata).
- eliminazioni PROTETTE: un'anagrafica usata (arrivi, produzioni, ricetta)
  non si elimina: la tracciabilità non si riscrive.
"""

CONSERVAZIONI = ("Frigo", "Freezer", "Magazzino")


class ErroreAnagrafica(ValueError):
    pass


def _tipo(conn, p):
    """'ingrediente' o 'prodotto': il discriminante dell'app.

    La famiglia la dà la ricetta; un prodotto di laboratorio appena creato
    (dalla modale ricette o dal form produzione) non ce l'ha ancora, ma NON ha
    conservazione né lotti in arrivo: è un 'prodotto' in attesa di ricetta.
    Un ingrediente ha sempre la conservazione (obbligatoria alla nascita).
    """
    if p["famiglia_id"] is not None:
        return "prodotto"
    if p["conservazione"] is not None:
        return "ingrediente"
    arrivato = conn.execute(
        "SELECT 1 FROM lotti_ingresso WHERE prodotto_id = ? LIMIT 1", (p["id"],)
    ).fetchone()
    return "ingrediente" if arrivato else "prodotto"


def allergeni_prodotto(conn, prodotto_id):
    """Gli allergeni DICHIARATI di un ingrediente (m2m)."""
    return [
        dict(r) for r in conn.execute(
            "SELECT a.id, a.nome, a.descrizione FROM allergeni a "
            "JOIN prodotti_allergeni pa ON pa.allergene_id = a.id "
            "WHERE pa.prodotto_id = ? ORDER BY a.id", (prodotto_id,)
        ).fetchall()
    ]


def allergeni_da_ricetta(conn, prodotto_id, _visti=None):
    """Gli allergeni EREDITATI di un prodotto di laboratorio: unione ricorsiva
    degli ingredienti della sua ricetta (un semilavorato porta i suoi)."""
    if _visti is None:
        _visti = set()
    if prodotto_id in _visti:
        return []          # parascenico: una ricetta non può autocontenersi
    _visti.add(prodotto_id)
    nomi = set()
    for r in conn.execute(
        "SELECT ingrediente_id FROM ricette_righe rr "
        "JOIN ricette r ON r.id = rr.ricetta_id WHERE r.prodotto_id = ?",
        (prodotto_id,),
    ).fetchall():
        ing = conn.execute(
            "SELECT * FROM prodotti WHERE id = ?", (r["ingrediente_id"],)
        ).fetchone()
        if ing is None:
            continue
        if _tipo(conn, ing) == "prodotto":
            nomi.update(allergeni_da_ricetta(conn, ing["id"], _visti))
        else:
            for a in allergeni_prodotto(conn, ing["id"]):
                nomi.add(a["nome"])
    return sorted(nomi)


def _totali(r):
    """Totale e totale+IVA: CALCOLATI (nel DB solo prezzo e IVA)."""
    totale = (r["quantita"] or 0) * (r["prezzo_unitario"] or 0)
    return totale, totale * (1 + (r["iva"] or 0) / 100)


def _arrivi_recenti(conn, where, param):
    righe = []
    for r in conn.execute(
        "SELECT li.*, p.nome AS prodotto, p.unita_misura AS um "
        "FROM lotti_ingresso li JOIN prodotti p ON p.id = li.prodotto_id "
        "WHERE " + where + " ORDER BY li.data_arrivo DESC, li.id DESC LIMIT 20",
        param,
    ).fetchall():
        r = dict(r)
        r["totale"], r["totale_iva"] = _totali(r)
        righe.append(r)
    return righe


# ---- liste delle quattro card ----

def lista_ingredienti(conn, testo=""):
    """Card 🛒: ingredienti acquistati con allergeni dichiarati e n. arrivi."""
    q = (testo or "").strip().lower()
    righe = []
    for p in conn.execute(
        "SELECT p.*, f.nome AS famiglia FROM prodotti p "
        "LEFT JOIN famiglie f ON f.id = p.famiglia_id ORDER BY p.nome"
    ).fetchall():
        p = dict(p)
        if _tipo(conn, p) != "ingrediente":
            continue
        if q and q not in p["nome"].lower() and q not in (p["marca"] or "").lower():
            continue
        p["allergeni"] = allergeni_prodotto(conn, p["id"])
        p["n_arrivi"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotti_ingresso WHERE prodotto_id = ?",
            (p["id"],),
        ).fetchone()["n"]
        righe.append(p)
    return righe


def lista_prodotti(conn, testo="", famiglia_id=0):
    """Card 🥣: SOLO prodotti con ricetta (gerarchia stretta voluta da Nicolas:
    il prodotto esiste attraverso la sua ricetta, che è il master. Un prodotto
    nato dal ➕ ma rimasto senza ricetta NON si vede qui: lo si completa dalla
    sezione Ricette). Allergeni EREDITATI dalla ricetta: mai scritti a mano."""
    q = (testo or "").strip().lower()
    righe = []
    for p in conn.execute(
        "SELECT p.*, f.nome AS famiglia FROM prodotti p "
        "LEFT JOIN famiglie f ON f.id = p.famiglia_id ORDER BY p.nome"
    ).fetchall():
        p = dict(p)
        if _tipo(conn, p) != "prodotto":
            continue
        if not conn.execute(
            "SELECT 1 FROM ricette WHERE prodotto_id = ?", (p["id"],)
        ).fetchone():
            continue          # senza ricetta non è (ancora) un prodotto
        if famiglia_id and p["famiglia_id"] != famiglia_id:
            continue
        if q and q not in p["nome"].lower():
            continue
        p["allergeni"] = allergeni_da_ricetta(conn, p["id"])
        p["ha_ricetta"] = True
        p["n_produzioni"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotti_interni WHERE prodotto_id = ?",
            (p["id"],),
        ).fetchone()["n"]
        righe.append(p)
    return righe


# ---- dettagli (le schede di modifica) ----

def dettaglio_prodotto(conn, prodotto_id):
    p = conn.execute("SELECT * FROM prodotti WHERE id = ?", (prodotto_id,)).fetchone()
    if not p:
        raise ErroreAnagrafica("Prodotto inesistente")
    p = dict(p)
    p["tipo"] = _tipo(conn, p)
    p["famiglia"] = conn.execute(
        "SELECT nome FROM famiglie WHERE id = ?", (p["famiglia_id"],)
    ).fetchone()["nome"] if p["famiglia_id"] else None
    if p["tipo"] == "ingrediente":
        p["allergeni"] = allergeni_prodotto(conn, p["id"])
        p["n_arrivi"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotti_ingresso WHERE prodotto_id = ?",
            (p["id"],),
        ).fetchone()["n"]
        p["arrivi"] = _arrivi_recenti(conn, "li.prodotto_id = ?", (p["id"],))
    else:
        p["allergeni"] = allergeni_da_ricetta(conn, p["id"])
        p["ha_ricetta"] = conn.execute(
            "SELECT id FROM ricette WHERE prodotto_id = ?", (p["id"],)
        ).fetchone() is not None
        p["n_produzioni"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotti_interni WHERE prodotto_id = ?",
            (p["id"],),
        ).fetchone()["n"]
        p["produzioni"] = [
            dict(r) for r in conn.execute(
                "SELECT li.id, li.codice_lotto, li.data_produzione, "
                "li.data_scadenza, li.qta_prodotta, p2.unita_misura AS um "
                "FROM lotti_interni li JOIN prodotti p2 ON p2.id = li.prodotto_id "
                "WHERE li.prodotto_id = ? ORDER BY li.data_produzione DESC, "
                "li.id DESC LIMIT 20", (p["id"],)
            ).fetchall()
        ]
    return p


def dettaglio_fornitore(conn, fornitore_id):
    f = conn.execute(
        "SELECT * FROM fornitori WHERE id = ?", (fornitore_id,)
    ).fetchone()
    if not f:
        raise ErroreAnagrafica("Fornitore inesistente")
    f = dict(f)
    f["arrivi"] = _arrivi_recenti(conn, "li.fornitore_id = ?", (fornitore_id,))
    f["n_arrivi"] = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_ingresso WHERE fornitore_id = ?",
        (fornitore_id,),
    ).fetchone()["n"]
    return f


# ---- creazione e modifica ----

def _valida_allergeni(conn, ids):
    ids = list(dict.fromkeys(int(i) for i in ids))     # unici, nell'ordine dato
    validi = {r["id"] for r in conn.execute("SELECT id FROM allergeni").fetchall()}
    for i in ids:
        if i not in validi:
            raise ErroreAnagrafica("Allergene sconosciuto")
    return ids


def crea_ingrediente(conn, dati, da_anagrafica=False):
    """Nasce l'INGREDIENTE: conservazione, denominazione legale (obbligatoria
    se richiesta dall'anagrafica), allergeni. La creazione rapida dalle combo
    di altre sezioni resta più lasca (si completa in Anagrafiche)."""
    nome = (dati.get("nome") or "").strip()
    if not nome:
        raise ErroreAnagrafica("Il nome dell'ingrediente è obbligatorio")
    conservazione = (dati.get("conservazione") or "").strip()
    if conservazione not in CONSERVAZIONI:
        raise ErroreAnagrafica("Conservazione: Frigo, Freezer o Magazzino")
    um = (dati.get("unita_misura") or "").strip()
    if not um:
        raise ErroreAnagrafica("Unità di misura obbligatoria (es. kg)")
    denominazione = (dati.get("denominazione_legale") or "").strip() or None
    if da_anagrafica and not denominazione:
        raise ErroreAnagrafica(
            "La denominazione legale è obbligatoria: finisce nell'etichetta "
            "dei prodotti finiti (es. farina 00 → Farina di grano tenero tipo 00)"
        )
    allergeni = _valida_allergeni(conn, dati.get("allergeni") or [])
    cur = conn.execute(
        "INSERT INTO prodotti (nome, famiglia_id, conservazione, unita_misura, "
        "sigla, marca, denominazione_legale, note) "
        "VALUES (?, NULL, ?, ?, ?, ?, ?, ?)",
        (nome, conservazione, um,
         (dati.get("sigla") or "").strip().upper() or None,
         (dati.get("marca") or "").strip() or None,
         denominazione, (dati.get("note") or "").strip() or None),
    )
    pid = cur.lastrowid
    for a in allergeni:
        conn.execute(
            "INSERT INTO prodotti_allergeni (prodotto_id, allergene_id) "
            "VALUES (?, ?)", (pid, a)
        )
    return dettaglio_prodotto(conn, pid)


def salva_prodotto(conn, dati):
    """Modifica di un'anagrafica prodotto. La FAMIGLIA NON si tocca qui:
    nasce dalla ricetta (master). I prodotti di laboratorio non dichiarano
    allergeni: li ereditano (rifiuto esplicito, così non passa in silenzio)."""
    pid = dati.get("id")
    p = conn.execute("SELECT * FROM prodotti WHERE id = ?", (pid,)).fetchone()
    if not p:
        raise ErroreAnagrafica("Prodotto inesistente")
    tipo = _tipo(conn, p)
    nome = (dati.get("nome") or "").strip()
    if not nome:
        raise ErroreAnagrafica("Il nome è obbligatorio")
    um = (dati.get("unita_misura") or "").strip()
    if not um:
        raise ErroreAnagrafica("Unità di misura obbligatoria (es. kg)")
    sigla = (dati.get("sigla") or "").strip().upper() or None
    note = (dati.get("note") or "").strip() or None
    if tipo == "ingrediente":
        conservazione = (dati.get("conservazione") or "").strip()
        if conservazione not in CONSERVAZIONI:
            raise ErroreAnagrafica("Conservazione: Frigo, Freezer o Magazzino")
        denominazione = (dati.get("denominazione_legale") or "").strip()
        if not denominazione:
            raise ErroreAnagrafica(
                "La denominazione legale è obbligatoria: finisce nell'etichetta "
                "dei prodotti finiti"
            )
        marca = (dati.get("marca") or "").strip() or None
        allergeni = _valida_allergeni(conn, dati.get("allergeni") or [])
        conn.execute(
            "UPDATE prodotti SET nome = ?, conservazione = ?, unita_misura = ?, "
            "sigla = ?, marca = ?, denominazione_legale = ?, note = ? WHERE id = ?",
            (nome, conservazione, um, sigla, marca, denominazione, note, pid),
        )
        conn.execute(
            "DELETE FROM prodotti_allergeni WHERE prodotto_id = ?", (pid,)
        )
        for a in allergeni:
            conn.execute(
                "INSERT INTO prodotti_allergeni (prodotto_id, allergene_id) "
                "VALUES (?, ?)", (pid, a)
            )
    else:
        if dati.get("allergeni"):
            raise ErroreAnagrafica(
                "I prodotti di laboratorio non dichiarano allergeni: "
                "li ereditano dalla ricetta"
            )
        # i dati del laboratorio non si scrivono qui (marca, conservazione,
        # denominazione restano quelli dell'ingrediente/ricetta)
        conn.execute(
            "UPDATE prodotti SET nome = ?, unita_misura = ?, sigla = ?, note = ? "
            "WHERE id = ?",
            (nome, um, sigla, note, pid),
        )
    return dettaglio_prodotto(conn, pid)


def salva_fornitore(conn, dati):
    fid = dati.get("id")
    f = conn.execute("SELECT * FROM fornitori WHERE id = ?", (fid,)).fetchone()
    if not f:
        raise ErroreAnagrafica("Fornitore inesistente")
    nome = (dati.get("nome") or "").strip()
    if not nome:
        raise ErroreAnagrafica("La ragione sociale è obbligatoria")
    conn.execute(
        "UPDATE fornitori SET nome = ?, piva = ?, telefono = ?, email = ?, "
        "note = ? WHERE id = ?",
        (nome,
         (dati.get("piva") or "").strip() or None,
         (dati.get("telefono") or "").strip() or None,
         (dati.get("email") or "").strip() or None,
         (dati.get("note") or "").strip() or None,
         fid),
    )
    return dettaglio_fornitore(conn, fid)


def rinomina_famiglia(conn, famiglia_id, nome):
    """Rinomina inline: si PROPAGA ovunque perché tutto JOINa per id."""
    nome = (nome or "").strip()
    if not nome:
        raise ErroreAnagrafica("Il nome della famiglia è obbligatorio")
    f = conn.execute(
        "SELECT * FROM famiglie WHERE id = ?", (famiglia_id,)
    ).fetchone()
    if not f:
        raise ErroreAnagrafica("Famiglia inesistente")
    dup = conn.execute(
        "SELECT id FROM famiglie WHERE LOWER(nome) = LOWER(?) AND id != ?",
        (nome, famiglia_id),
    ).fetchone()
    if dup:
        raise ErroreAnagrafica("Esiste già una famiglia con questo nome")
    conn.execute("UPDATE famiglie SET nome = ? WHERE id = ?", (nome, famiglia_id))
    return {"id": famiglia_id, "nome": nome}


# ---- eliminazioni PROTETTE ----

def elimina_prodotto(conn, prodotto_id):
    """Un'anagrafica usata non si elimina: la tracciabilità non si riscrive."""
    p = conn.execute(
        "SELECT * FROM prodotti WHERE id = ?", (prodotto_id,)
    ).fetchone()
    if not p:
        raise ErroreAnagrafica("Prodotto inesistente")
    n_arrivi = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_ingresso WHERE prodotto_id = ?",
        (prodotto_id,),
    ).fetchone()["n"]
    if n_arrivi:
        raise ErroreAnagrafica(
            f"Eliminazione protetta: {n_arrivi} arrivi registrati con questo "
            "prodotto. La tracciabilità non si riscrive."
        )
    n_prod = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_interni WHERE prodotto_id = ?",
        (prodotto_id,),
    ).fetchone()["n"]
    if n_prod:
        raise ErroreAnagrafica(
            f"Eliminazione protetta: {n_prod} produzioni registrate con questo "
            "prodotto. La tracciabilità non si riscrive."
        )
    if conn.execute(
        "SELECT 1 FROM ricette WHERE prodotto_id = ?", (prodotto_id,)
    ).fetchone():
        raise ErroreAnagrafica(
            "Eliminazione protetta: il prodotto ha una ricetta (è il master). "
            "Elimina prima la ricetta, se non ha produzioni."
        )
    conn.execute(
        "DELETE FROM prodotti_allergeni WHERE prodotto_id = ?", (prodotto_id,)
    )
    conn.execute("DELETE FROM prodotti WHERE id = ?", (prodotto_id,))


def elimina_fornitore(conn, fornitore_id):
    n_arrivi = conn.execute(
        "SELECT COUNT(*) AS n FROM lotti_ingresso WHERE fornitore_id = ?",
        (fornitore_id,),
    ).fetchone()["n"]
    if n_arrivi:
        raise ErroreAnagrafica(
            f"Eliminazione protetta: {n_arrivi} arrivi registrati con questo "
            "fornitore. La tracciabilità non si riscrive."
        )
    f = conn.execute(
        "SELECT * FROM fornitori WHERE id = ?", (fornitore_id,)
    ).fetchone()
    if not f:
        raise ErroreAnagrafica("Fornitore inesistente")
    conn.execute("DELETE FROM fornitori WHERE id = ?", (fornitore_id,))
