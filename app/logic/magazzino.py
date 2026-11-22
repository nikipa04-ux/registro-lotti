"""Il magazzino NON si scrive: si legge.

Regola di progetto: nessuna giacenza si inserisce a mano, è arrivo meno
consumi (il verbale delle produzioni scarica i lotti in ingresso). Questo
modulo calcola tutto il capitolo Magazzino:

  righe - giacenza per ingrediente e MARCA: lo stesso ingrediente può essere
          in casa con più marche senza duplicare l'anagrafica (la marca
          nasce nel lotto consegnato, vedi logic/arrivi.py);
  stat  - statistiche per ingrediente, compresi quelli ESENATI (giacenza 0:
          con un consumo storico sono i primi della lista "Da ordinare"):
          consumo medio/giorno su TUTTO lo storico, dal primo arrivo
          (scelta di Nicolas, 18/11/2026), copertura in giorni e le
          statistiche dei rifornimenti (n. arrivi, cadenza media, ultimo
          arrivo, prossimo rifornimento atteso = ultimo + cadenza).

Soglie della copertura (scelte con Nicolas, 18/11/2026):
  rosso < 3 giorni (urgenza), ambra < 7 giorni; "da ordinare" = sotto i 7.

Le SCADENZE vivono qui (modulo "magazzino e scadenze" dell'endpoint):
  la finestra di default è 7 giorni con selettore 3/7/30/tutte e un filtro
  dedicato "Scaduti" (scelta di Nicolas, 18/11/2026 notte): i lotti già
  scaduti compaiono SOLO lì, mai mischiati a chi scade domani.
"""
from datetime import date, timedelta

SOGLIA_ROSSO = 3   # giorni di copertura: sotto è urgenza
SOGLIA_AMBRA = 7    # giorni di copertura: sotto si ordina
FINESTRE = ("3", "7", "30", "all", "scad")   # finestre di scadenza ammesse


class ErroreMagazzino(ValueError):
    """Input respinto: il messaggio va mostrato all'utente così com'è."""


def _giorni_alla(data_iso, oggi):
    """Giorni interi che mancano alla scadenza (negativo = scaduto)."""
    return (date.fromisoformat(data_iso) - oggi).days


def lista_scadenze(conn, finestra="7", oggi=None):
    """Lotti nella finestra di scadenza scelta, ordinati per urgenza.

    Lotti in INGRESSO solo con giacenza (chi è già consumato non può
    più far male); lotti INTERNI tutti (la v0.1 non traccia la loro
    residua: decide la sola scadenza, come nella dashboard).
    Ogni riga porta "giorni" per il badge colore della UI.
    """
    if finestra not in FINESTRE:
        raise ErroreMagazzino(
            "Finestra non valida: scegli 3, 7, 30, all o scad")
    if oggi is None:
        oggi = date.today()
    if isinstance(oggi, str):
        oggi = date.fromisoformat(oggi)

    oggi_iso = oggi.isoformat()
    if finestra == "scad":
        cond, parametri = "AND li.data_scadenza < ?", (oggi_iso,)
    elif finestra == "all":
        cond, parametri = "", ()
    else:
        tra = (oggi + timedelta(days=int(finestra))).isoformat()
        cond = "AND li.data_scadenza >= ? AND li.data_scadenza <= ?"
        parametri = (oggi_iso, tra)

    ingressi = conn.execute(
        "SELECT 'ingresso' AS tipo, li.id, p.nome AS prodotto, "
        "li.codice_lotto AS lotto, COALESCE(li.marca, p.marca) AS marca, "
        "f.nome AS fornitore, p.conservazione, p.unita_misura AS um, "
        "li.quantita_residua AS quantita, li.data_scadenza AS scadenza "
        "FROM lotti_ingresso li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE li.quantita_residua > 0 " + cond,
        parametri,
    ).fetchall()

    interni = conn.execute(
        "SELECT 'interno' AS tipo, li.id, p.nome AS prodotto, "
        "li.codice_lotto AS lotto, NULL AS marca, NULL AS fornitore, "
        "NULL AS conservazione, COALESCE(li.um_prodotta, p.unita_misura) AS um, "
        "li.qta_prodotta AS quantita, li.data_scadenza AS scadenza "
        "FROM lotti_interni li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "WHERE 1=1 " + cond,
        parametri,
    ).fetchall()

    righe = []
    for r in list(ingressi) + list(interni):
        righe.append({
            "tipo": r["tipo"], "id": r["id"],
            "prodotto": r["prodotto"], "lotto": r["lotto"],
            "marca": r["marca"], "fornitore": r["fornitore"],
            "conservazione": r["conservazione"],
            "quantita": r["quantita"], "um": r["um"],
            "scadenza": r["scadenza"],
            "giorni": _giorni_alla(r["scadenza"], oggi),
        })
    righe.sort(key=lambda r: r["scadenza"])
    return righe


def lotti_giacenza(conn, prodotto_id, oggi=None):
    """Lotti di un ingrediente ancora IN GIACENZA (residua > 0), in ordine
    FEFO: lo stesso ordine con cui la proposta di produzione li consuma.
    Serve al pannello laterale del Magazzino: click su una giacenza → i
    lotti che la compongono (la UI li raggruppa per marca).
    """
    if not conn.execute(
        "SELECT 1 FROM prodotti WHERE id = ?", (prodotto_id,)
    ).fetchone():
        raise ErroreMagazzino("Prodotto inesistente.")
    if oggi is None:
        oggi = date.today()
    if isinstance(oggi, str):
        oggi = date.fromisoformat(oggi)

    righe = [dict(r) for r in conn.execute(
        "SELECT li.id, li.codice_lotto, "
        "COALESCE(li.marca, p.marca, '—') AS marca, f.nome AS fornitore, "
        "li.quantita, li.quantita_residua, li.data_arrivo, li.data_scadenza, "
        "li.prezzo_unitario, li.iva, p.unita_misura AS um "
        "FROM lotti_ingresso li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE li.prodotto_id = ? AND li.quantita_residua > 0 "
        "ORDER BY li.data_scadenza, li.data_arrivo, li.id",
        (prodotto_id,),
    ).fetchall()]
    for r in righe:
        r["giorni"] = _giorni_alla(r["data_scadenza"], oggi)
    return righe


def magazzino(conn, oggi=None):
    """Ritorna {"righe": [...], "stat": [...], "esauriti": [...]} pronte per la UI.

    esauriti (RIFIN 38): i lotti chiusi a zero, azzerati a mano (es. il
    latte del bar) o consumati dalle produzioni: restano leggibili per
    la tracciabilità. L'unica "scrittura" ammessa sul magazzino è per
    l'appunto l'azzeramento manuale (data_esaurimento).

    oggi: date o ISO stringa, serve SOLO nei test per date deterministiche;
    a produzione si lascia None (oggi reale del server).
    """
    if oggi is None:
        oggi = date.today()
    if isinstance(oggi, str):
        oggi = date.fromisoformat(oggi)

    righe = [dict(r) for r in conn.execute(
        "SELECT p.id AS prodotto_id, p.nome, p.conservazione, "
        "COALESCE(li.marca, p.marca, '—') AS marca, p.unita_misura AS um, "
        "SUM(li.quantita_residua) AS giacenza, COUNT(li.id) AS n_lotti "
        "FROM lotti_ingresso li JOIN prodotti p ON p.id = li.prodotto_id "
        "WHERE li.quantita_residua > 0 "
        "GROUP BY p.id, COALESCE(li.marca, p.marca, '—') "
        "ORDER BY p.nome, marca",
    ).fetchall()]

    stat = []
    grezze = conn.execute(
        "SELECT p.id AS prodotto_id, p.nome, p.conservazione, p.unita_misura AS um, "
        "MIN(li.data_arrivo) AS primo_arrivo, MAX(li.data_arrivo) AS ultimo_arrivo, "
        "COUNT(li.id) AS n_arrivi, COALESCE(SUM(li.quantita_residua), 0) AS giacenza_tot, "
        "COALESCE((SELECT SUM(c.quantita_usata) FROM consumi c "
        "  WHERE c.origine = 'ingresso' AND c.lotto_origine_id IN "
        "  (SELECT id FROM lotti_ingresso WHERE prodotto_id = p.id)), 0) AS consumo_totale "
        "FROM prodotti p JOIN lotti_ingresso li ON li.prodotto_id = p.id "
        "GROUP BY p.id ORDER BY p.nome",
    ).fetchall()
    for r in grezze:
        primo = date.fromisoformat(r["primo_arrivo"])
        ultimo = date.fromisoformat(r["ultimo_arrivo"])
        giorni = max(1, (oggi - primo).days)
        consumo_medio = r["consumo_totale"] / giorni if r["consumo_totale"] else None
        giacenza_tot = r["giacenza_tot"] or 0.0
        copertura = round(giacenza_tot / consumo_medio, 1) if consumo_medio else None
        livello = None
        if copertura is not None:
            if copertura < SOGLIA_ROSSO:
                livello = "rosso"
            elif copertura < SOGLIA_AMBRA:
                livello = "ambra"
        if r["n_arrivi"] > 1:
            cadenza = (ultimo - primo).days / (r["n_arrivi"] - 1)
            prossimo_atteso = (ultimo + timedelta(days=cadenza)).isoformat()
        else:
            cadenza = None
            prossimo_atteso = None
        stat.append({
            "prodotto_id": r["prodotto_id"], "nome": r["nome"],
            "conservazione": r["conservazione"], "um": r["um"],
            "giacenza_tot": giacenza_tot, "n_arrivi": r["n_arrivi"],
            "consumo_medio": consumo_medio, "copertura": copertura,
            "livello": livello,
            "da_ordinare": copertura is not None and copertura < SOGLIA_AMBRA,
            "ultimo_arrivo": r["ultimo_arrivo"],
            "cadenza": cadenza, "prossimo_atteso": prossimo_atteso,
        })

    # ESAURITI (RIFIN 38): lotti chiusi a zero, per la tracciabilità. Due
    # vite possibili: consumati dalle produzioni (esaurito_il = data del
    # VERBALE più recente che li ha scaricati) o azzerati a mano (es. il
    # latte del bar: data_esaurimento). Ordinati dal più recente.
    esauriti = [dict(r) for r in conn.execute(
        "SELECT p.id AS prodotto_id, p.nome AS prodotto, p.conservazione, "
        "COALESCE(li.marca, p.marca, '—') AS marca, f.nome AS fornitore, "
        "li.id, li.codice_lotto, li.quantita, li.data_arrivo, li.data_scadenza, "
        "COALESCE(li.data_esaurimento, "
        "  (SELECT MAX(li2.data_produzione) FROM consumi c "
        "   JOIN lotti_interni li2 ON li2.id = c.lotto_interno_id "
        "   WHERE c.origine = 'ingresso' AND c.lotto_origine_id = li.id) "
        ") AS esaurito_il, "
        "CASE WHEN li.data_esaurimento IS NOT NULL "
        "     THEN 'azzerato' ELSE 'consumato' END AS come "
        "FROM lotti_ingresso li "
        "JOIN prodotti p ON p.id = li.prodotto_id "
        "JOIN fornitori f ON f.id = li.fornitore_id "
        "WHERE li.quantita_residua <= 0 "
        "ORDER BY esaurito_il DESC, li.data_arrivo DESC",
    ).fetchall()]

    return {"righe": righe, "stat": stat, "esauriti": esauriti}
