"""Ricette MASTER: da qui nasce ciò che si può produrre.

La ricetta è il documento di partenza (resa, righe, procedimento) e il
posto dove nasce la FAMIGLIA (regola di design: famiglia→ricetta).
Le produzioni sono SLAVE: ne leggono le righe e ne fotografano (snapshot)
la famiglia al momento della produzione.

Nessun tag fisso tipo "semilavorato": la famiglia è un'etichetta libera,
l'utente ne crea quante vuole. Un prodotto con ricetta è producibile;
senza ricetta non lo è, che abbia o no una famiglia.
"""
import re

from . import um
from .lotti import genera_codice  # noqa: F401  (usata dai test/seed)
from .anagrafiche import _tipo, _fantasma   # RIFIN 45: candidati e duplicati

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
            "SELECT rr.ingrediente_id, rr.quantita, rr.um_scritta, "
            "rr.facoltativa, p.nome, "
            "p.unita_misura AS um, p.densita, "
            "fr.nome AS famiglia_ingrediente "
            "FROM ricette_righe rr "
            "JOIN prodotti p ON p.id = rr.ingrediente_id "
            "LEFT JOIN ricette ric ON ric.prodotto_id = rr.ingrediente_id "
            "LEFT JOIN famiglie fr ON fr.id = ric.famiglia_id "
            "WHERE rr.ricetta_id = ? ORDER BY rr.id",
            (ricetta["id"],),
        ).fetchall()
    ]
    # RIFIN 51: la riga viaggia con la dose COME L'HAI SCRITTA ('500 g'):
    # quantita resta canonica (0,485 lt), dose_qta/dose_um è il laboratorio
    for r in righe:
        if r["um_scritta"]:
            f = um.fattore(r["um"], r["um_scritta"]) or um.fattore_liquido(
                r["um"], r["um_scritta"], r["densita"]
            ) or 1.0
            r["dose_qta"] = r["quantita"] * f
            r["dose_um"] = r["um_scritta"]
        else:
            r["dose_qta"] = r["quantita"]
            r["dose_um"] = r["um"]
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
    conservazione = (dati.get("conservazione") or "").strip() or None
    if conservazione and conservazione not in ("Frigo", "Freezer", "Magazzino"):
        raise ErroreRicetta("Conservazione: Frigo, Freezer o Magazzino")
    gia = conn.execute(
        "SELECT * FROM prodotti WHERE LOWER(nome) = LOWER(?)", (nome,)
    ).fetchone()
    if gia and not _fantasma(conn, gia):
        # nome già preso da un'anagrafica VERA: il messaggio dice COS'È e
        # DOVE guardarla (prima diceva solo "esiste già" e sembrava un
        # fantasma introvabile: il caso "Torta al cioccolato")
        ingrediente = _tipo(conn, gia) == "ingrediente"
        cosa = "un ingrediente acquistato" if ingrediente else "un prodotto di laboratorio"
        dove = "card Ingredienti" if ingrediente else "card Prodotti"
        raise ErroreRicetta(
            f"'{nome}' esiste già: è {cosa} ({dove} di Anagrafiche)")
    sigla = (dati.get("sigla") or "").strip().upper() or None
    if gia:
        # RIFIN 45: nome di un CANDIDATO abbandonato (➕ senza ricetta,
        # zero storia): lo si COMPLETA riusando la stessa riga. Un nome
        # non resta mai intrappolato da un esperimento finito male
        pid = gia["id"]
        conn.execute(
            "UPDATE prodotti SET nome = ?, sigla = ?, conservazione = ?, "
            "unita_misura = ? WHERE id = ?",
            (nome, sigla, conservazione, um, pid),
        )
    else:
        pid = conn.execute(
            "INSERT INTO prodotti (nome, famiglia_id, conservazione, unita_misura, sigla) "
            "VALUES (?, NULL, ?, ?, ?)",
            (nome, conservazione, um, sigla),
        ).lastrowid
    return {
        "id": pid, "nome": nome, "sigla": sigla,
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


def _um_dalla_resa(conn, resa):
    """RIFIN 50: la resa della ricetta ('5 kg', '12 teglie', '60 pz')
    NOMINA l'u.m. canonica del prodotto, come la famiglia la nomina la
    ricetta: il master scrive l'anagrafica. Solo un nome GIÀ presente
    nell'anagrafica u.m. ( regained: così la tendina di Produzioni
    propone il parco noto e i ➕ creano i nuovi); resa muta o u.m. ignota
    -> None: il prodotto resta esattamente com'era."""
    testo = (resa or "").strip().replace(",", ".")
    if not testo:
        return None
    m = re.match(r"^\d+(?:\.\d+)?\s*([A-Za-zÀ-ÿ]+)", testo)
    if not m:
        return None
    riga = conn.execute(
        "SELECT nome FROM unita_misura WHERE nome = ? COLLATE NOCASE",
        (m.group(1),),
    ).fetchone()
    return riga["nome"] if riga else None


def salva_ricetta(conn, dati):
    """Crea o aggiorna la ricetta di un prodotto (upsert: UNIQUE prodotto_id).

    dati: prodotto_id, famiglia_id | famiglia_nuova, resa?, procedimento?,
          righe [{ingrediente_id, quantita}]
    Righe rimpiazzano le vecchie: la ricetta è il master. RIFIN 56: una
          riga può essere facoltativa (semilavorato facoltativo: crema al pistacchio
          delle brioches): si usa SOLO nelle produzioni che la prevedono.
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
    righe_ok = []
    for r in righe_in:
        ing = conn.execute(
            "SELECT id, nome, unita_misura, densita FROM prodotti WHERE id = ?",
            (r.get("ingrediente_id"),),
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
        # RIFIN 51: la dose si può scrivere nell'u.m. che usa il laboratorio
        # ('500' + 'g'): il fattore è quello di um.py (g<->kg, ml<->lt) OPPURE
        # il ponte peso<->volume, ma SOLO se la scheda dell'ingrediente ha la
        # densità (g/ml). Il verbale e i lotti restano SEMPRE in canonica.
        um_scritta = (r.get("um") or "").strip() or None
        if um_scritta and um_scritta != ing["unita_misura"]:
            f = um.fattore(um_scritta, ing["unita_misura"])
            if f is None:
                f = um.fattore_liquido(
                    um_scritta, ing["unita_misura"], ing["densita"]
                )
            if f is None:
                raise ErroreRicetta(
                    f'"{ing["nome"]}" non ammette la u.m. "{um_scritta}" '
                    f"(canonica '{ing['unita_misura']}'): serve la stessa u.m., "
                    "il suo fratello (g/kg, ml/lt) oppure una densità dichiarata "
                    "nella sua scheda in Anagrafiche"
                )
            qta = qta * f   # in u.m. CANONICA
            righe_ok.append({
                "ingrediente_id": ing["id"], "quantita": qta,
                "um_scritta": um_scritta,
                # RIFIN 56: semilavorato facoltativo (1/0)
                "facoltativa": 1 if r.get("facoltativa") else 0,
            })
        else:
            righe_ok.append({
                "ingrediente_id": ing["id"], "quantita": qta,
                "um_scritta": None,
                "facoltativa": 1 if r.get("facoltativa") else 0,
            })

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
    for r in righe_ok:
        conn.execute(
            "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita, "
            "um_scritta, facoltativa) VALUES (?, ?, ?, ?, ?)",
            (ricetta_id, r["ingrediente_id"], float(r["quantita"]),
             r["um_scritta"], r["facoltativa"]),
        )
    # La famiglia NASCE nella ricetta e l'anagrafica del prodotto la rispecchia
    # (così combo e filtri, che leggono l'anagrafica, la vedono subito).
    conn.execute(
        "UPDATE prodotti SET famiglia_id = ? WHERE id = ?", (famiglia_id, prodotto_id)
    )
    # RIFIN 50: come la famiglia, anche l'U.M. CANONICA nasce dalla ricetta:
    # la resa la nomina ('5 kg' -> kg). È un SUGGERIMENTO che l'utente può
    # sempre cambiare (anagrafica / produzione: tendina con tutto il parco
    # e ➕ crea); toccata SOLO quando la resa nomina un'u.m. dell'anagrafica.
    um_resa = _um_dalla_resa(conn, dati.get("resa"))
    if um_resa:
        conn.execute(
            "UPDATE prodotti SET unita_misura = ? WHERE id = ?",
            (um_resa, prodotto_id),
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
