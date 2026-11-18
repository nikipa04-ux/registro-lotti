"""L'etichetta del lotto interno come PDF, in una GRIGLIA sul foglio.

Un foglio A4 diviso in griglia (2 colonne x 4 righe = 8 etichette):
stampe multiple dello stesso lotto senza sprecare carta, con un bordo
grigio leggero per cella che fa da guida di taglio. Se servono più
copie di quante ne stia una pagina, il foglio successivo arriva da solo.

SOLO LIBRERIA STANDARD: il PDF nasce pezzo per pezzo (oggetti, xref,
stream di testo). Font Type1 di base (Helvetica, Helvetica-Bold,
Courier-Bold) con WinAnsiEncoding: le lettere accentate italiane
(à è ì ò ù é) viaggiano in cp1252, niente font da installare.

Contenuto di ogni etichetta (i dati CALCOLATI, nessuno snapshot):
  - nome del prodotto
  - lotto interno (codice generato dal server)
  - prodotto il / scade il
  - ingredienti: la lista calcolata da logic/etichetta.py
    (denominazioni legali, ordine di quantità d'uso; la quantità NON
    si dichiara, Reg. UE 1169/2011)
  - allergeni: "Contiene:" in neretto, TUTTO NERO su richiesta di
    Nicolas (18/11): l'etichetta stampata resta monocromatica,
    solo se ce ne sono
"""

import unicodedata

# ---- geometria del foglio (punti tipografici, A4 = 595 x 842) ----
LARGHEZZA_A4, ALTEZZA_A4 = 595.28, 841.89
MARGINE = 20.0
INTERVALLO = 12.0            # spazio tra le celle (respira anche il taglio)
COLONNE, RIGHE = 2, 4        # la griglia: 8 etichette per foglio
MARGINE_CELLA = 9.0          # respiro interno tra bordo cella e testo

# Larghezze dei glifi (millesimi di punto) dei font Type1 Helvetica,
# tabelle pubbliche del formato (Adobe AFM). Le lettere accentate usano
# la larghezza della lettera base: scendere di un accento non pesa.
_LARGH_ELG = {  # Helvetica
    " !i": 278, '"': 355, "#$0123456789": 556, "%": 889, "&": 667, "'": 191,
    "()*": 333, "+": 584, ",-.": 278, "/": 278, ":;": 278, "<=>": 584,
    "?": 556, "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667,
    "F": 611, "G": 778, "H": 722, "I": 278, "J": 500, "K": 667, "L": 556,
    "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667,
    "T": 611, "U": 722, "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "[]\\": 278, "^": 469, "_": 556, "`": 333, "a": 556, "b": 556, "c": 500,
    "d": 556, "e": 556, "f": 278, "g": 556, "h": 556, "i": 222, "j": 222,
    "k": 500, "l": 222, "m": 833, "n": 556, "o": 556, "p": 556, "q": 556,
    "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722, "x": 500,
    "y": 500, "z": 500, "{|}~": 334,
}
_LARGH_ELG_NER = {  # Helvetica-Bold
    " ": 278, "!": 333, '"': 474, "#$0123456789": 556, "%": 889, "&": 722,
    "'": 238, "()": 333, "*": 389, "+": 584, ",-.": 278, "/": 278,
    ":;": 333, "<=>": 584, "?": 611, "@": 975, "A": 722, "B": 722, "C": 722,
    "E": 667, "D": 722, "F": 611, "G": 778, "H": 722, "I": 278, "J": 556,
    "K": 722, "L": 611, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778,
    "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944, "X": 667,
    "Y": 667, "Z": 611, "[]": 333, "\\": 278, "^": 584, "_": 556, "`": 333,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611,
    "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611,
    "v": 556, "w": 778, "x": 556, "y": 556, "z": 500, "{|}": 389, "~": 584,
}
_TAVOLE = {
    "F1": {c: w for cs, w in _LARGH_ELG.items() for c in cs},       # Helvetica
    "F2": {c: w for cs, w in _LARGH_ELG_NER.items() for c in cs},  # Helvetica-Bold
    "F3": {c: 600 for c in map(chr, range(32, 127))},               # Courier-Bold
}


class ErroreEtichetta(Exception):
    """Il lotto non esiste: niente etichetta da impaginare."""


def _base_ascii(testo):
    """L'accento NON cambia la larghezza: à -> a, è -> e (per misurare)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", testo)
        if not unicodedata.combining(c)
    )


def _larghezza(testo, font="F1", taglia=10.0):
    """Larghezza del testo in punti (per andare a capo con criterio)."""
    tavola = _TAVOLE[font]
    return sum(tavola.get(c, 556) for c in _base_ascii(testo)) / 1000.0 * taglia


def _spezza(testo, font="F1", taglia=10.0, max_larg=250.0):
    """Manda il testo a capo senza superare max_larg (greedy sulle parole)."""
    righe = []
    corrente = ""
    for parola in testo.split():
        prova = parola if not corrente else corrente + " " + parola
        if _larghezza(prova, font, taglia) <= max_larg or not corrente:
            corrente = prova
        else:
            righe.append(corrente)
            corrente = parola
    if corrente:
        righe.append(corrente)
    return righe or [""]


def _escape(testo):
    """Le parentesi e la barra sbagliano il pdf: si zittiscono qui."""
    return testo.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _testo(x, y, riga, font="F1", taglia=10.0, colore=None):
    """Un blocco di testo nel content stream (colore: (r, g, b) opzionale)."""
    if colore:
        colore_testo = "%.3f %.3f %.3f rg " % colore
    else:
        colore_testo = ""
    corpo = "BT /%s %.2f Tf %s1 0 0 1 %.2f %.2f Tm (%s) Tj ET" % (
        font, taglia, colore_testo, x, y, _escape(riga))
    return corpo.encode("cp1252", errors="replace")


def _blocchi_etichetta(dati, scala, max_larg):
    """Le righe dell'etichetta: lista di (font, taglia, righe, colore).

    Ogni riga di blocco è già spezzata per la larghezza utile della cella.
    """
    nome = _spezza(dati["prodotto"], "F2", 13 * scala, max_larg)
    ing = _spezza(
        ", ".join(r["denominazione"] for r in dati["righe"]),
        "F1", 8.2 * scala, max_larg,
    )
    blocchi = [
        ("F2", 13 * scala, nome, None),
        ("F1", 9.0 * scala,
         ["Lotto: " + dati["codice_lotto"]], None),
        ("F1", 9.0 * scala,
         ["Prodotto il: " + dati["data_produzione"] +
          "    Scade il: " + dati["data_scadenza"]], None),
        ("F2", 8.0 * scala, ["Ingredienti"], None),
        ("F1", 8.2 * scala, ing, None),
    ]
    if dati["allergeni"]:
        contiene = _spezza(
            "Contiene: " + ", ".join(dati["allergeni"]),
            "F2", 8.8 * scala, max_larg,
        )
        # NERO anche gli allergeni (richiesta di Nicolas): il colore è
        # solo del cicchetto, non serve alla stampa
        blocchi.append(
            ("F2", 8.8 * scala, contiene, None))
    return blocchi


def _altezza_blocchi(blocchi):
    """Quanto spazio verticale occupano i blocchi (interlinea 1.25)."""
    return sum(
        taglia * 1.25 * (len(righe) + 0.35)
        for _font, taglia, righe, _colore in blocchi
    )


def _celle_etichetta(dati, cella_h, max_larg):
    """I blocchi dell'etichetta alla prima scala che sta dentro la cella.

    Se anche la scala minima non basta (ricetta chilometrica) si va con
    quella e pazienza: meglio un'etichetta fitta che ingredienti tagliati.
    """
    for scala in (1.0, 0.92, 0.85, 0.78):
        blocchi = _blocchi_etichetta(dati, scala, max_larg)
        if _altezza_blocchi(blocchi) <= cella_h - 2 * MARGINE_CELLA:
            return blocchi
    return _blocchi_etichetta(dati, 0.78, max_larg)


def etichetta_pdf(conn, lotto_interno_id, copie=8):
    """Il PDF del foglio A4 con una griglia di etichette identiche.

    Ritorna i bytes del PDF (copie etichette, 8 per foglio: oltre, pagina
    dopo pagina, senza sprecare né carta né fiato).
    """
    lotto = conn.execute(
        "SELECT li.*, p.nome AS prodotto, p.unita_misura AS um "
        "FROM lotti_interni li JOIN prodotti p ON p.id = li.prodotto_id "
        "WHERE li.id = ?", (lotto_interno_id,),
    ).fetchone()
    if not lotto:
        raise ErroreEtichetta("Lotto interno non trovato")

    # La lista CALCOLATA: fusioni fatte, denominazioni legali, ordine di legge
    from .etichetta import etichetta

    comp = etichetta(conn, lotto_interno_id)
    dati = {
        "prodotto": lotto["prodotto"],
        "codice_lotto": lotto["codice_lotto"],
        "data_produzione": lotto["data_produzione"],
        "data_scadenza": lotto["data_scadenza"],
        "righe": comp["righe"],
        "allergeni": comp["allergeni"],
    }

    if copie < 1:
        copie = 1
    per_pagina = COLONNE * RIGHE
    n_pagine = (copie + per_pagina - 1) // per_pagina

    cella_l = (LARGHEZZA_A4 - 2 * MARGINE - INTERVALLO * (COLONNE - 1)) / COLONNE
    cella_h = (ALTEZZA_A4 - 2 * MARGINE - INTERVALLO * (RIGHE - 1)) / RIGHE
    max_larg = cella_l - 2 * (MARGINE_CELLA + 1.5)

    # L'etichetta si impagina UNA volta, poi si ripete identica in ogni cella.
    blocchi = _celle_etichetta(dati, cella_h, max_larg)
    righe_testo = []          # (offset_x, offset_y dal FONDO cella, riga, ...)
    y = cella_h - MARGINE_CELLA          # prima riga: sotto il bordo superiore
    for font, taglia, righe, colore in blocchi:
        for riga in righe:
            y -= taglia * 1.15
            righe_testo.append((MARGINE_CELLA + 1.5, y, riga, font, taglia, colore))
            y -= taglia * 0.10
        y -= taglia * 0.25               # respiro tra un blocco e l'altro

    # ---- i fogli ----
    pagine = []
    disegnate = 0
    for _pagina in range(n_pagine):
        parti = []
        for cella in range(per_pagina):
            if disegnate >= copie:
                break
            riga, col = divmod(cella, COLONNE)
            # origine del pdf in basso a sinistra: noi ragioniamo dall'alto
            x_angolo = MARGINE + col * (cella_l + INTERVALLO)
            y_angolo = ALTEZZA_A4 - MARGINE - riga * (cella_h + INTERVALLO) - cella_h
            # bordo grigio leggero: guida di taglio che non urla
            bordo = "q 0.85 G 0.8 w %.2f %.2f %.2f %.2f re S Q" % (
                x_angolo, y_angolo, cella_l, cella_h)
            parti.append(bordo.encode("cp1252"))
            for dx, dy, riga_testo, font, taglia, colore in righe_testo:
                parti.append(_testo(
                    x_angolo + dx, y_angolo + dy,
                    riga_testo, font, taglia, colore,
                ))
            disegnate += 1
        pagine.append(b"\n".join(parti))
    return _assembla_pdf(pagine)


def _assembla_pdf(contenuti):
    """Oggetti, xref e trailer: un PDF completo, bytes pronti."""
    oggetti = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,   # segnaposto: il tree delle pagine (serve il numero di figli)
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>",
    ]
    figli = []
    prossima_pagina = 6        # dopo catalog, pages e i tre font
    for contenuto in contenuti:
        n_pagina = prossima_pagina + 2 * len(figli)
        figli.append(n_pagina)
        oggetti.append(
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] "
             "/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
             "/Contents %d 0 R >>" %
             (LARGHEZZA_A4, ALTEZZA_A4, n_pagina + 1)).encode())
        oggetti.append(
            b"<< /Length " + str(len(contenuto)).encode() +
            b" >>\nstream\n" + contenuto + b"\nendstream")
    oggetti[1] = ("<< /Type /Pages /Kids [" +
                  " ".join("%d 0 R" % f for f in figli) +
                  "] /Count %d >>" % len(figli)).encode()

    byte = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offset = [0] * (len(oggetti) + 1)
    for n, corpo in enumerate(oggetti, start=1):
        offset[n] = sum(len(p) for p in byte)
        byte.append(str(n).encode() + b" 0 obj\n" + corpo + b"\nendobj\n")
    inizio_xref = sum(len(p) for p in byte)
    byte.append(b"xref\n0 " + str(len(oggetti) + 1).encode() + b"\n")
    byte.append(b"0000000000 65535 f \n")
    for n in range(1, len(oggetti) + 1):
        byte.append(("%010d 00000 n \n" % offset[n]).encode())
    byte.append(
        b"trailer\n<< /Size " + str(len(oggetti) + 1).encode() +
        b" /Root 1 0 R >>\nstartxref\n" + str(inizio_xref).encode() +
        b"\n%%EOF\n")
    return b"".join(byte)


def nome_file_pdf(codice_lotto):
    """Il nome del file: etichetta-CODICE.pdf (il codice nasce dal server)."""
    return "etichetta-" + (codice_lotto or "lotto") + ".pdf"
