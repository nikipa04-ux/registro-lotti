"""Generazione dei codici lotto interno.

Formato: SIGLA-AAAAMMGG-NN (es. CRP-20261113-01).
Generato dal backend: l'utente NON lo digita mai.
NN è un progressivo giornaliero per prodotto.
"""


def genera_codice(conn, prodotto, data_produzione):
    """Genera il prossimo codice per il prodotto nella data indicata.

    prodotto: dict con 'sigla' (facoltativa) e 'nome'.
    data_produzione: ISO 'YYYY-MM-DD'.
    """
    sigla = (prodotto.get("sigla") or prodotto["nome"][:3]).strip().upper()
    prefisso = f"{sigla}-{data_produzione.replace('-', '')}"
    n = conn.execute(
        "SELECT COUNT(*) FROM lotti_interni WHERE codice_lotto LIKE ?",
        (prefisso + "-%",),
    ).fetchone()[0]
    return f"{prefisso}-{n + 1:02d}"
