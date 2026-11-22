"""Il LIBRO RICETTE in PDF: tutte le ricette, ingredienti e allergeni.

Per l'HACCP serve su carta cosa si produce e con cosa: per ogni prodotto
di laboratorio la sua ricetta con le quantità per resa e gli ALLERGENI
dichiarati. Gli allergeni del prodotto finito si CALCOLANO qui:

  - un ingrediente ACQUISTATO dichiara i suoi (prodotti_allergeni);
  - un SEMILAVORATO non dichiara niente: EREDITA dagli ingredienti
    della sua ricetta, in ricorsione (la crema dentro il bignè porta
    latte e uova nel bignè).

Come per l'etichetta: SOLO libreria standard, il PDF nasce pezzo per
pezzo riusingo l'impaginatore di etichetta_pdf.py (font Type1, WinAnsi,
xref, pagine a flusso: la ricetta che non entra nel foglio rimanda
tutta alla pagina dopo).

Il PDF è un documento DATATO (chi produce + data di stampa), come un
manuale HACCP che si ristampa quando cambia una ricetta.
"""
from datetime import date

from .etichetta_pdf import (
    ALTEZZA_A4,
    LARGHEZZA_A4,
    _assembla_pdf,
    _spezza,
    _testo,
)

# ---- geometria: pagina A4 "documento", non etichetta ----
MARGINE_SX, MARGINE_DX = 50.0, 50.0
MARGINE_SUP, MARGINE_INF = 56.0, 50.0
INTERLINEA = 1.32                # righe di lettura: più aria dell'etichetta
SPIRO_BLOCCHI = 4.0              # respiro tra i blocchi di una ricetta
LARGH_UTILE = LARGHEZZA_A4 - MARGINE_SX - MARGINE_DX


def _qt(q):
    """4.0 -> '4', 1.5 -> '1,5': la virgola è quella dei pasticceri."""
    return ("%g" % (q or 0)).replace(".", ",")


def allergeni_ricetta(conn, prodotto_id, _visti=None):
    """Gli allergeni del prodotto finito, EREDITATI in ricorsione.

    L'ingrediente acquistato dichiara i suoi; il semilavorato scende
    nella propria ricetta. Il ciclo (a non finire) si spezza con _visti.
    """
    if _visti is None:
        _visti = set()
    if prodotto_id in _visti:
        return []
    _visti.add(prodotto_id)
    nomi = [r["nome"] for r in conn.execute(
        "SELECT al.nome FROM allergeni al "
        "JOIN prodotti_allergeni pa ON pa.allergene_id = al.id "
        "WHERE pa.prodotto_id = ?", (prodotto_id,),
    ).fetchall()]
    ingredienti = [r["ingrediente_id"] for r in conn.execute(
        "SELECT rr.ingrediente_id "
        "FROM ricette_righe rr JOIN ricette r ON r.id = rr.ricetta_id "
        "WHERE r.prodotto_id = ?", (prodotto_id,),
    ).fetchall()]
    for iid in ingredienti:
        # il semilavorato ha una ricetta sua: eredita da lì
        ha_ricetta = conn.execute(
            "SELECT id FROM ricette WHERE prodotto_id = ?", (iid,),
        ).fetchone()
        if ha_ricetta:
            nomi.extend(allergeni_ricetta(conn, iid, _visti))
        else:
            nomi.extend(r["nome"] for r in conn.execute(
                "SELECT al.nome FROM allergeni al "
                "JOIN prodotti_allergeni pa ON pa.allergene_id = al.id "
                "WHERE pa.prodotto_id = ?", (iid,),
            ).fetchall())
    return sorted(set(nomi))


def schede_ricette(conn):
    """Le schede del libro: [{prodotto, famiglia, resa, righe, allergeni...}].

    righe: [{nome, quantita, um, semilavorato}] nell'ordine della ricetta.
    Questa funzione è il contratto dei test (e del PDF).
    """
    schede = []
    ricette = conn.execute(
        "SELECT r.prodotto_id, r.resa, r.procedimento, "
        "p.nome, p.sigla, f.nome AS famiglia "
        "FROM ricette r "
        "JOIN prodotti p ON p.id = r.prodotto_id "
        "LEFT JOIN famiglie f ON f.id = r.famiglia_id "
        "ORDER BY p.nome COLLATE NOCASE",
    ).fetchall()
    for ric in ricette:
        righe = []
        for r in conn.execute(
            "SELECT rr.ingrediente_id, rr.quantita, p.nome, "
            "p.unita_misura AS um, (SELECT COUNT(*) FROM ricette r2 "
            " WHERE r2.prodotto_id = rr.ingrediente_id) AS n_ricetta "
            "FROM ricette_righe rr "
            "JOIN prodotti p ON p.id = rr.ingrediente_id "
            "WHERE rr.ricetta_id = (SELECT id FROM ricette WHERE prodotto_id = ?) "
            "ORDER BY rr.id",
            (ric["prodotto_id"],),
        ).fetchall():
            righe.append({
                "nome": r["nome"],
                "quantita": r["quantita"],
                "um": r["um"] or "",
                "semilavorato": r["n_ricetta"] > 0,
            })
        schede.append({
            "prodotto_id": ric["prodotto_id"],
            "prodotto": ric["nome"],
            "sigla": ric["sigla"],
            "famiglia": ric["famiglia"],
            "resa": ric["resa"],
            "procedimento": ric["procedimento"],
            "righe": righe,
            "allergeni": allergeni_ricetta(conn, ric["prodotto_id"]),
        })
    return schede


def _blocchi_scheda(s):
    """I blocchi di una ricetta: [(font, taglia, righe)] da impaginare."""
    sotto = " · ".join(parte for parte in (
        s["famiglia"] or "",
        ("resa " + s["resa"]) if s["resa"] else "",
    ) if parte)
    blocchi = [("F2", 13.0, _spezza(s["prodotto"], "F2", 13.0, LARGH_UTILE))]
    if sotto:
        blocchi.append(("F1", 9.0, _spezza(sotto, "F1", 9.0, LARGH_UTILE)))
    blocchi.append(("F2", 9.5, ["Ingredienti"]))
    if s["righe"]:
        righe_ing = []
        for r in s["righe"]:
            righe_ing.extend(_spezza(
                "- " + r["nome"] + " · " + _qt(r["quantita"]) +
                (" " + r["um"] if r["um"] else ""),
                "F1", 9.5, LARGH_UTILE))
        blocchi.append(("F1", 9.5, righe_ing))
    else:
        blocchi.append(("F1", 9.5, ["(ricetta senza ingredienti)"]))
    if s["allergeni"]:
        blocchi.append(("F2", 9.5, _spezza(
            "Contiene: " + ", ".join(s["allergeni"]), "F2", 9.5, LARGH_UTILE)))
    else:
        blocchi.append(("F1", 9.5, ["Nessun allergene dichiarato negli ingredienti"]))
    # niente PROCEDIMENTO su carta (richiesta di Nicolas): resta nell'app,
    # nel PDF ci sono ingredienti e allergeni, il resto è della cucina
    return blocchi


def _altezza(blocchi):
    return sum(taglia * INTERLINEA * len(righe) + SPIRO_BLOCCHI
               for _font, taglia, righe in blocchi)


def libro_ricette_pdf(conn):
    """Il PDF del libro ricette: bytes pronti, una riga di storia per pagina."""
    from .impostazioni import leggi_produttore

    schede = schede_ricette(conn)
    produttore = leggi_produttore(conn)
    parte, pagine, y = [], [], ALTEZZA_A4 - MARGINE_SUP

    def vai_a_capo():
        nonlocal parte, y
        pagine.append(b"\n".join(parte))
        parte = []
        y = ALTEZZA_A4 - MARGINE_SUP

    def riga(font, taglia, testo):
        nonlocal y
        if y - taglia * INTERLINEA < MARGINE_INF:
            vai_a_capo()
        y -= taglia * INTERLINEA
        parte.append(_testo(MARGINE_SX, y, testo, font, taglia))

    def separatore():
        nonlocal y
        if y - 12 < MARGINE_INF:
            vai_a_capo()
        parte.append(
            ("q 0.75 G 0.7 w %.2f %.2f m %.2f %.2f l S Q" %
             (MARGINE_SX, y - 5, LARGHEZZA_A4 - MARGINE_DX, y - 5)).encode())
        y -= 14

    # ---- la copertina del documento (per l'HACCP: chi e quando) ----
    riga("F2", 16.0, "Libro ricette")
    # il NOME DEL NEGOZIO in evidenza, come in etichetta (Reg. UE 1169/2011):
    # neretto sotto il titolo, poi indirizzo e P.IVA in piccolo
    if produttore["ragione_sociale"]:
        for r in _spezza(produttore["ragione_sociale"], "F2", 11.5, LARGH_UTILE):
            riga("F2", 11.5, r)
    recapiti = " · ".join(p for p in (
        produttore["indirizzo"],
        ("P.IVA " + produttore["piva"]) if produttore["piva"] else "",
    ) if p)
    if recapiti:
        for r in _spezza(recapiti, "F1", 9.5, LARGH_UTILE):
            riga("F1", 9.5, r)
    riga("F1", 9.5, "Stampato il " + date.today().isoformat())
    separatore()

    if not schede:
        riga("F1", 10.0, "Nessuna ricetta salvata.")
    for i, s in enumerate(schede):
        blocchi = _blocchi_scheda(s)
        # la ricetta non si spacca: se non entra TUTTA, va alla pagina dopo
        if y - _altezza(blocchi) < MARGINE_INF:
            vai_a_capo()
        for font, taglia, righe in blocchi:
            for r in righe:
                riga(font, taglia, r)
            y -= SPIRO_BLOCCHI
        if i < len(schede) - 1:
            separatore()
    pagine.append(b"\n".join(parte))
    return _assembla_pdf(pagine)
