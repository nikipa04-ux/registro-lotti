"""Conversioni fra unità di misura.

Regola di progetto: NESSUNA conversione implicita fra tipi diversi.
Solo dentro lo stesso gruppo si converte (massa: g<->kg, volume: ml<->lt),
con UNA eccezione dichiarata (RIFIN 51): il ponte peso<->volume è ammesso
SOLO per gli ingredienti con DENSITÀ scritta in anagrafica (g/ml).
Pezzi, teglie, vasetti restano inconvertibili: 60 pz NON diventano kg,
e una teglia non si traduce in grammi.
"""

import re
import unicodedata

MASSA = {"g": 1.0, "kg": 1000.0}
VOLUME = {"ml": 1.0, "lt": 1000.0}
GRUPPI = {"massa": MASSA, "volume": VOLUME}


def gruppo_di(um):
    """Ritorna il nome del gruppo ('massa', 'volume') o None se u.m. libera."""
    for nome, tabella in GRUPPI.items():
        if um in tabella:
            return nome
    return None


def fattore(da_um, a_um):
    """Fattore moltiplicativo per andare da da_um a a_um.

    Ritorna None se la conversione non è ammessa (tipi diversi o u.m. libere):
    il chiamante deve chiedere all'utente, NON convertire di nascosto.
    """
    if da_um == a_um:
        return 1.0
    g_da = gruppo_di(da_um)
    g_a = gruppo_di(a_um)
    if g_da is None or g_a is None or g_da != g_a:
        return None
    tabella = GRUPPI[g_da]
    return tabella[da_um] / tabella[a_um]


def fattore_liquido(da_um, a_um, densita):
    """RIFIN 51: il ponte PESO<->VOLUME, ammesso SOLO con la densità (g/ml)
    dichiarata in anagrafica dall'utente (mai implicita: 500 g di latte e
    500 g di olio NON sono lo stesso volume). g<->ml, g<->lt, kg<->ml,
    kg<->lt e inversi. None se: densità mancante, u.m. libere, stesso
    gruppo (quello è il lavoro di fattore, non il ponte).
    """
    if da_um == a_um:
        return 1.0
    if not densita or densita <= 0:
        return None
    g_da = gruppo_di(da_um)
    g_a = gruppo_di(a_um)
    if g_da is None or g_a is None or g_da == g_a:
        return None
    if g_da == "massa":        # grammi -> millilitri (volume)
        return MASSA[da_um] / densita / VOLUME[a_um]
    return VOLUME[da_um] * densita / MASSA[a_um]   # volume -> massa


def converti(qta, da_um, a_um):
    """Converte, o solleva ValueError se la conversione è vietata."""
    f = fattore(da_um, a_um)
    if f is None:
        raise ValueError(
            f"Conversione non ammessa: {da_um} -> {a_um} "
            "(nessuna conversione implicita fra tipi diversi)"
        )
    return qta * f


# ---- RIFIN 51: densità TIPICHE (g/ml, ~20°C) per il SUGGERIMENTO in
# anagrafica. Il valore resta SEMPRE dell'utente: l'app lo propone alla
# creazione in base al nome, lui conferma o cambia, e da lì viaggia con
# la scheda (l'id), non col nome. La parola PIÙ LUNGA vince: "latte
# condensato" (1,30) batte "latte" (1,03). Confronto casefold e senza
# accenti, a confini di parola intera ("latte" non matcha "latteggio").
DENSITA_TIPICHE = [
    ("latte condensato", 1.30),
    ("latte di mandorla", 1.03),
    ("succo di arancia", 1.045),
    ("succo di limone", 1.03),
    ("uova pastorizzate", 1.03),
    ("arancia", 1.045),   # pesca anche l'elisione: "succo d'arancia"
    ("limone", 1.03),     # idem: "spremuta d'arancia", "scorza di limone"...
    ("albume", 1.03),
    ("sciroppo", 1.35),
    ("glucosio", 1.35),
    ("alchermes", 0.95),
    ("liquore", 0.95),
    ("marsala", 1.02),
    ("grappa", 0.85),
    ("alcool", 0.79),
    ("alcohol", 0.79),
    ("alcol", 0.79),
    ("latte", 1.03),
    ("panna", 1.00),
    ("acqua", 1.00),
    ("olio", 0.92),
    ("succo", 1.04),
    ("aceto", 1.01),
    ("cocco", 1.01),
    ("aroma", 1.00),
    ("vino", 0.99),
    ("rum", 0.80),
    ("caffe", 1.00),
]


def _normalizza(testo):
    """Minuscolo, senza accenti, spazi singoli: per confrontare i nomi."""
    testo = (testo or "").strip().casefold()
    testo = "".join(
        c for c in unicodedata.normalize("NFD", testo)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(testo.split())


def _catalogo_densita(conn):
    """RIFIN 52: le DENSITA_TIPICHE del codice con le voci PERSONALI
    dell'utente che vincono (stessa parola = la sua densità)."""
    catalogo = dict(DENSITA_TIPICHE)
    if conn is not None:
        for r in conn.execute("SELECT parola, densita FROM densita_custom"):
            catalogo[r["parola"]] = r["densita"]
    return catalogo


def densita_suggerita(conn, nome):
    """RIFIN 51: densità TIPICA suggerita per NOME, alla creazione
    dell'ingrediente. RIFIN 52: prima le voci dell'utente, poi il
    catalogo. Ritorna (parola, densita) della prima corrispondenza
    (la parola più lunga vince) o None se nessuna corrisponde."""
    n = _normalizza(nome)
    if not n:
        return None
    catalogo = _catalogo_densita(conn)
    for parola in sorted(catalogo, key=len, reverse=True):
        if re.search(r"\b" + re.escape(parola) + r"\b", n):
            return parola, catalogo[parola]
    return None
