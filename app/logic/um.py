"""Conversioni fra unità di misura.

Regola di progetto: NESSUNA conversione implicita fra tipi diversi.
Solo dentro lo stesso gruppo si converte (massa: g<->kg, volume: ml<->lt).
Pezzi, teglie, vasetti restano inconvertibili: 60 pz NON diventano kg,
e una teglia non si traduce in grammi.
"""

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
    if g_da is None or g_da != g_a:
        return None
    tabella = GRUPPI[g_da]
    return tabella[da_um] / tabella[a_um]


def converti(qta, da_um, a_um):
    """Converte, o solleva ValueError se la conversione è vietata."""
    f = fattore(da_um, a_um)
    if f is None:
        raise ValueError(
            f"Conversione non ammessa: {da_um} -> {a_um} "
            "(nessuna conversione implicita fra tipi diversi)"
        )
    return qta * f
