"""Generazione dei codici lotto interno.

Formato: SIGLA-AAAAMMGG-NN (es. CRP-20261113-01).
Generato dal backend: l'utente NON lo digita mai.
NN è un progressivo giornaliero per prodotto.
"""


def genera_codice(conn, prodotto, data_produzione):
    """Genera il prossimo codice per il prodotto nella data indicata.

    prodotto: dict con 'sigla' (facoltativa) e 'nome'.
    data_produzione: ISO 'YYYY-MM-DD'.

    RIFIN 54: il progressivo è MAX(coda) + 1, NON il conteggio delle
    righe: eliminare la produzione -01 di una giornata con anche la -02
    non deve far nascere una seconda -02 (il codice lotto è UNIQUE:
    lo scontro impediva di registrare). Il codice di un lotto eliminato
    si riusa solo se era l'ultimo della serie.
    """
    sigla = (prodotto.get("sigla") or prodotto["nome"][:3]).strip().upper()
    prefisso = f"{sigla}-{data_produzione.replace('-', '')}"
    n = 0
    for riga in conn.execute(
        "SELECT codice_lotto FROM lotti_interni WHERE codice_lotto LIKE ?",
        (prefisso + "-%",),
    ).fetchall():
        coda = riga["codice_lotto"].rsplit("-", 1)[-1]
        if coda.isdigit():
            n = max(n, int(coda))
    return f"{prefisso}-{n + 1:02d}"
