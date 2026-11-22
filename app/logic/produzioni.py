"""Produzioni interne: proposta FEFO dalla ricetta e verbale dei consumi.

La produzione è SLAVE della ricetta (MASTER): la proposta nasce dalle
righe della ricetta, l'operatore al massimo corregge. Il verbale finale
sono i consumi: le quantità usate SCARICANO la residua dei lotti in
ingresso (le giacenze non si scrivono mai a mano).

v0.1: i lotti interni consumati (semilavorati) non tracciano la residua:
la loro "disponibilità" è la quantità prodotta.
"""
from datetime import date

from .fefo import copertura_fefo, ordina_fefo
from .lotti import genera_codice
from . import um


class ErroreProduzione(ValueError):
    """Input respinto: il messaggio va mostrato all'utente così com'è."""


def _data_iso(testo, campo):
    try:
        return date.fromisoformat((testo or "").strip()).isoformat()
    except ValueError:
        raise ErroreProduzione(f"Data di {campo} non valida: serve il formato AAAA-MM-GG")


def _oggi(oggi):
    """Normalizza 'oggi': ammette date ISO (stringhe) o oggetti date."""
    if oggi is None:
        return date.today()
    if isinstance(oggi, str):
        return date.fromisoformat(oggi)
    return oggi


def lotti_disponibili(conn, ingrediente_id, oggi=None):
    """Lotti utilizzabili di un ingrediente, già ordinati FEFO.

    - ingrediente acquistato: lotti in ingresso con residua > 0
    - prodotto di laboratorio usato come ingrediente: anche i lotti
      interni non scaduti dello stesso prodotto (residua = qta_prodotta, v0.1)
    """
    oggi = _oggi(oggi)
    lotti = []
    for r in conn.execute(
        "SELECT li.id, li.codice_lotto, li.data_scadenza, li.data_arrivo, "
        "li.quantita_residua, 'ingresso' AS origine, f.nome AS fornitore "
        "FROM lotti_ingresso li JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE li.prodotto_id = ? AND li.quantita_residua > 0",
        (ingrediente_id,),
    ).fetchall():
        lotti.append(dict(r))
    for r in conn.execute(
        "SELECT li.id, li.codice_lotto, li.data_scadenza, "
        "li.data_produzione AS data_arrivo, li.qta_prodotta AS quantita_residua, "
        "'interno' AS origine, NULL AS fornitore "
        "FROM lotti_interni li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "WHERE li.prodotto_id = ? AND li.data_scadenza >= ? "
        # un lotto prodotto in u.m. NON convertibile (es. 6 teglie di un
        # prodotto in pz) non si traduce in giacenza canonica: la FEFO non
        # lo propone (regola di progetto: nessuna conversione fra tipi)
        "AND (li.um_prodotta IS NULL OR li.um_prodotta = p.unita_misura)",
        (ingrediente_id, oggi.isoformat()),
    ).fetchall():
        lotti.append(dict(r))
    return ordina_fefo(lotti)


def proponi_produzione(conn, prodotto_id, oggi=None):
    """La proposta FEFO partendo dalla ricetta MASTER.

    Ritorna:
      prodotto: {id, nome, um, sigla}
      ricetta:  {resa, procedimento, famiglia}
      righe:    una per riga di ricetta, con i lotti disponibili
                (ordinati FEFO) e la proposta di consumo già calcolata
                sulla quantità della ricetta. 'mancante' > 0 = merce che
                manca per coprire la ricetta (l'operatore lo vede subito).
    """
    prodotto = conn.execute(
        "SELECT * FROM prodotti WHERE id = ?", (prodotto_id,)
    ).fetchone()
    if not prodotto:
        raise ErroreProduzione("Prodotto inesistente")
    ricetta = conn.execute(
        "SELECT * FROM ricette WHERE prodotto_id = ?", (prodotto_id,)
    ).fetchone()
    # Si produce solo ciò che ha una RICETTA master. Se il prodotto non ha
    # famiglia è quasi certamente un ingrediente acquistato: messaggio chiaro.
    if not ricetta:
        if prodotto["famiglia_id"] is None:
            raise ErroreProduzione(
                f'"{prodotto["nome"]}" è un ingrediente acquistato: '
                "si producono solo i prodotti di laboratorio"
            )
        raise ErroreProduzione(
            f'"{prodotto["nome"]}" non ha ancora una ricetta: '
            "creala o correggila nella sezione Ricette (è il master)"
        )
    famiglia = None
    if ricetta["famiglia_id"]:
        riga_fam = conn.execute(
            "SELECT nome FROM famiglie WHERE id = ?", (ricetta["famiglia_id"],)
        ).fetchone()
        famiglia = riga_fam["nome"] if riga_fam else None

    righe = []
    for r in conn.execute(
        "SELECT rr.ingrediente_id, rr.quantita, p.nome, p.unita_misura, "
        "fr.nome AS famiglia "
        "FROM ricette_righe rr "
        "JOIN prodotti p ON p.id = rr.ingrediente_id "
        "LEFT JOIN ricette ric ON ric.prodotto_id = rr.ingrediente_id "
        "LEFT JOIN famiglie fr ON fr.id = ric.famiglia_id "
        "WHERE rr.ricetta_id = ? ORDER BY rr.id",
        (ricetta["id"],),
    ).fetchall():
        lotti = lotti_disponibili(conn, r["ingrediente_id"], oggi)
        assegnazioni, coperto = copertura_fefo(lotti, r["quantita"])
        # NIENTE tag "semilavorato": la riga mostra la FAMIGLIA dell'ingrediente,
        # presa dalla SUA ricetta (la famiglia nasce lì, ed è l'utente a
        # crearne quante vuole). Ingrediente acquistato -> famiglia null.
        righe.append({
            "ingrediente_id": r["ingrediente_id"],
            "nome": r["nome"],
            "um": r["unita_misura"],
            "famiglia": r["famiglia"],
            "qta_ricetta": r["quantita"],
            "lotti": [
                {"id": l["id"], "codice_lotto": l["codice_lotto"],
                 "data_scadenza": l["data_scadenza"], "quantita_residua": l["quantita_residua"],
                 "origine": l["origine"], "fornitore": l["fornitore"]}
                for l in lotti
            ],
            "proposta": [
                {"lotto_id": a["lotto"]["id"], "codice_lotto": a["lotto"]["codice_lotto"],
                 "origine": a["lotto"]["origine"], "quantita": a["quantita"],
                 "data_scadenza": a["lotto"]["data_scadenza"]}
                for a in assegnazioni
            ],
            "mancante": r["quantita"] - coperto,
        })
    return {
        "prodotto": {"id": prodotto["id"], "nome": prodotto["nome"],
                     "um": prodotto["unita_misura"], "sigla": prodotto["sigla"]},
        "ricetta": {"resa": ricetta["resa"], "procedimento": ricetta["procedimento"],
                    "famiglia": famiglia},
        "righe": righe,
    }


def registra_produzione(conn, dati):
    """Salva il verbale: lotto interno + consumi + scarico residua.

    dati: prodotto_id, data_produzione, data_scadenza (ISO), consumi
          [{origine, lotto_origine_id, quantita_usata}], qta_prodotta?,
          famiglia_id? (default: snapshot dalla ricetta).
    Ritorna il dict del lotto interno creato (con nome prodotto e lo
    snapshot ricetta_modificata: 1 se il verbale ha usato un insieme di
    ingredienti diverso dalle righe della ricetta master).
    """
    prodotto_id = dati.get("prodotto_id")
    prodotto = conn.execute(
        "SELECT * FROM prodotti WHERE id = ?", (prodotto_id,)
    ).fetchone() if prodotto_id else None
    if not prodotto:
        raise ErroreProduzione("Prodotto inesistente")
    ricetta = conn.execute(
        "SELECT * FROM ricette WHERE prodotto_id = ?", (prodotto_id,)
    ).fetchone()
    # Si produce solo ciò che ha una RICETTA master (v. proponi_produzione)
    if not ricetta:
        if prodotto["famiglia_id"] is None:
            raise ErroreProduzione(
                f'"{prodotto["nome"]}" è un ingrediente acquistato: non si produce'
            )
        raise ErroreProduzione(
            f'"{prodotto["nome"]}" non ha ancora una ricetta: '
            "creala nella sezione Ricette (è il master)"
        )

    data_produzione = _data_iso(dati.get("data_produzione"), "produzione")
    data_scadenza = _data_iso(dati.get("data_scadenza"), "scadenza")
    if data_scadenza < data_produzione:
        raise ErroreProduzione("La data di scadenza non può precedere quella di produzione")

    qta_prodotta = dati.get("qta_prodotta")
    if qta_prodotta is not None:
        try:
            qta_prodotta = float(qta_prodotta)
        except (TypeError, ValueError):
            qta_prodotta = -1.0
        if qta_prodotta <= 0:
            raise ErroreProduzione("La quantità prodotta deve essere maggiore di zero")

    # SNAPSHOT u.m.: 6 teglie di un prodotto in pz (tipi diversi non si
    # convertono). La conversione g<->kg / ml<->lt spetta a CHI CHIAMA
    # (la UI lo fa da sola): se arriva un'um CONVERTIBILE questa API non
    # converte di nascosto, rifiuta.
    um_prodotta = (dati.get("um_prodotta") or "").strip() or None
    if um_prodotta and um_prodotta == prodotto["unita_misura"]:
        um_prodotta = None
    if um_prodotta and um.fattore(um_prodotta, prodotto["unita_misura"]) is not None:
        raise ErroreProduzione(
            f"La quantità prodotta va CONVERTITA in {prodotto['unita_misura']} "
            f"prima del salvataggio (u.m. '{um_prodotta}' dello stesso tipo)"
        )

    consumi = dati.get("consumi") or []
    if not consumi:
        raise ErroreProduzione(
            "Una produzione senza consumi non è un verbale: indica i lotti usati"
        )

    scarico = {}   # lotto ingresso -> totale prelevato
    visti = set()  # (origine, lotto): il verbale non ripete lo stesso lotto
    usati = set()  # prodotti (ingredienti) toccati dal verbale: serve allo
                   # snapshot "ricetta modificata" qui sotto

    for c in consumi:
        origine = c.get("origine")
        lotto_id = c.get("lotto_origine_id")
        try:
            qta = float(c.get("quantita_usata"))
        except (TypeError, ValueError):
            qta = -1.0
        if origine not in ("ingresso", "interno"):
            raise ErroreProduzione('Origine consumo non valida: "ingresso" o "interno"')
        if qta <= 0:
            raise ErroreProduzione("Le quantità usate devono essere maggiori di zero")
        if (origine, lotto_id) in visti:
            raise ErroreProduzione("Stesso lotto consumato due volte: unisci le quantità in una riga")
        visti.add((origine, lotto_id))
        if origine == "ingresso":
            lotto = conn.execute(
                "SELECT * FROM lotti_ingresso WHERE id = ?", (lotto_id,)
            ).fetchone()
            if not lotto:
                raise ErroreProduzione("Lotto in ingresso inesistente")
            usati.add(lotto["prodotto_id"])
            scarico[lotto_id] = scarico.get(lotto_id, 0.0) + qta
        else:
            lotto = conn.execute(
                "SELECT * FROM lotti_interni WHERE id = ?", (lotto_id,)
            ).fetchone()
            if not lotto:
                raise ErroreProduzione("Lotto interno inesistente")
            usati.add(lotto["prodotto_id"])

    for lotto_id, qta in scarico.items():
        residua = conn.execute(
            "SELECT quantita_residua FROM lotti_ingresso WHERE id = ?", (lotto_id,)
        ).fetchone()["quantita_residua"]
        if qta > (residua or 0) + 1e-9:
            raise ErroreProduzione(
                f"Giacenza insufficiente: servono {qta:g}, nel lotto ce ne sono {residua:g}"
            )

    # RICETTA MODIFICATA (SNAPSHOT): l'insieme degli ingredienti USATI
    # differisce dalle righe della ricetta master? Le quantità corrette non
    # contano (l'operatore corregge di continuo); un ingrediente AGGIUNTO o
    # una riga ESCLUSA sì. Il confronto avviene QUI, al verbale: la ricetta
    # può cambiare nei giorni dopo, il lotto dice com'è andata quel giorno.
    della_ricetta = {
        r["ingrediente_id"] for r in conn.execute(
            "SELECT ingrediente_id FROM ricette_righe WHERE ricetta_id = ?",
            (ricetta["id"],),
        ).fetchall()
    }
    ricetta_modificata = 1 if usati != della_ricetta else 0

    # Famiglia SNAPSHOT: quella della ricetta master (la produzione può
    # dichiararne una diversa, che vale solo per questo lotto)
    famiglia_id = dati.get("famiglia_id")
    if famiglia_id is None:
        ricetta = conn.execute(
            "SELECT famiglia_id FROM ricette WHERE prodotto_id = ?", (prodotto_id,)
        ).fetchone()
        famiglia_id = ricetta["famiglia_id"] if ricetta else prodotto["famiglia_id"]

    codice = genera_codice(conn, dict(prodotto), data_produzione)
    cur = conn.execute(
        "INSERT INTO lotti_interni (prodotto_id, famiglia_id, qta_prodotta, "
        "codice_lotto, data_produzione, data_scadenza, ricetta_modificata, "
        "um_prodotta) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (prodotto_id, famiglia_id, qta_prodotta, codice, data_produzione,
         data_scadenza, ricetta_modificata, um_prodotta),
    )
    lotto_interno_id = cur.lastrowid
    for c in consumi:
        conn.execute(
            "INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, quantita_usata) "
            "VALUES (?, ?, ?, ?)",
            (lotto_interno_id, c["origine"], c["lotto_origine_id"], float(c["quantita_usata"])),
        )
    # Lo SCARICO: le giacenze dei lotti in ingresso si aggiornano qui
    for lotto_id, qta in scarico.items():
        conn.execute(
            "UPDATE lotti_ingresso SET quantita_residua = quantita_residua - ? WHERE id = ?",
            (qta, lotto_id),
        )

    riga = conn.execute(
        "SELECT li.*, p.nome AS prodotto FROM lotti_interni li "
        "JOIN prodotti p ON p.id = li.prodotto_id WHERE li.id = ?",
        (lotto_interno_id,),
    ).fetchone()
    return dict(riga)


def elimina_produzione(conn, lotto_id):
    """Eliminazione PROTETTA di una produzione (errore di registrazione).

    - se il lotto interno è consumato da altre produzioni: rifiutata
    - altrimenti: il verbale si annulla e le giacenze TORNANO come prima
      (quantita_residua dei lotti in ingresso ripristinata dai consumi):
      le giacenze si scrivono solo qui, quindi si ripristinano solo qui.
    """
    lotto = conn.execute(
        "SELECT * FROM lotti_interni WHERE id = ?", (lotto_id,)
    ).fetchone()
    if not lotto:
        raise ErroreProduzione("Lotto interno inesistente")
    usato_da = conn.execute(
        "SELECT COUNT(*) AS n FROM consumi "
        "WHERE origine = 'interno' AND lotto_origine_id = ?",
        (lotto_id,),
    ).fetchone()["n"]
    if usato_da:
        raise ErroreProduzione(
            "Eliminazione protetta: il lotto è già usato in "
            f"{usato_da} produzione/i"
        )
    for c in conn.execute(
        "SELECT lotto_origine_id, quantita_usata FROM consumi "
        "WHERE lotto_interno_id = ? AND origine = 'ingresso'",
        (lotto_id,),
    ).fetchall():
        conn.execute(
            "UPDATE lotti_ingresso SET quantita_residua = quantita_residua + ? "
            "WHERE id = ?",
            (c["quantita_usata"], c["lotto_origine_id"]),
        )
    conn.execute("DELETE FROM consumi WHERE lotto_interno_id = ?", (lotto_id,))
    conn.execute("DELETE FROM lotti_interni WHERE id = ?", (lotto_id,))
