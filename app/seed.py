"""Dati di prova: lo scenario del pasticciere, con date RELATIVE a oggi.

Scopo: vedere il gestionale vivo da subito (dashboard con scadenze vere,
magazzino popolato, etichette calcolabili). Le scadenze sono calcolate
rispetto alla data di esecuzione, così la demo resta sempre significativa.

Esecuzione (dalla root, con l'ambiente attivo):
    python -m app.seed            -> inserisce solo se il DB è vuoto
    python -m app.seed --reset    -> SVUOTA il DB e ricarica la demo
"""
import sys
from datetime import date, timedelta

from .db import inizializza
from .logic.anagrafiche import ALLERGENI_DI_LEGGE
from .logic.lotti import genera_codice

OGGI = date.today()


def _g(giorni):
    """Data ISO a +/- N giorni da oggi."""
    return (OGGI + timedelta(days=giorni)).isoformat()


def seed(conn):
    # ---- Anagrafiche: fornitori ----
    fornitori = [
        ("Casearia Val Tiberina", "IT01234567890", "0575 555111", "ordini@caseariavt.example", "Consegna il martedì"),
        ("Molino Bianchi", "IT09876543210", "0575 555222", "spese@molinobianchi.example", ""),
        ("Dolceria Distribuzione", "IT05555123456", "0575 555333", "info@dolceriadist.example", "Porta anche zucchero e uova"),
    ]
    for nome, piva, tel, email, note in fornitori:
        conn.execute(
            "INSERT INTO fornitori (nome, piva, telefono, email, note) "
            "VALUES (?, ?, ?, ?, ?)", (nome, piva, tel, email, note))

    # ---- Allergeni: i 14 obbligatori da etichetta (Reg. UE 1169/2011) ----
    for nome, descrizione in ALLERGENI_DI_LEGGE:
        conn.execute(
            "INSERT INTO allergeni (nome, descrizione) VALUES (?, ?)",
            (nome, descrizione),
        )

    # ---- Famiglie dei prodotti di laboratorio ----
    for f in ["Creme", "Dolci finiti"]:
        conn.execute("INSERT INTO famiglie (nome) VALUES (?)", (f,))

    # ---- Ingredienti acquistati (famiglia NULL) ----
    # (nome, conservazione, um, sigla, marca, denominazione_legale, allergeni[])
    ingredienti = [
        ("Latte fresco intero", "Frigo", "lt", "LAT", "Val Tiberina",
         "Latte fresco intero pastorizzato", ["Latte"]),
        ("Uova pastorizzate liquide", "Frigo", "kg", "UOV", "Val Tiberina",
         "Uova fresche di gallina intere pastorizzate", ["Uova"]),
        ("Zucchero semolato", "Magazzino", "kg", "ZUC", "Dolceria",
         "Zucchero semolato", []),
        ("Farina 00", "Magazzino", "kg", "FAR", "Molino Bianchi",
         "Farina di grano tenero tipo 00", []),
        ("Panna da pasticceria", "Freezer", "lt", "PAN", "Val Tiberina",
         "Panna da pasticceria (grassi >= 35%)", ["Latte"]),
        ("Mandorle a lamelle", "Magazzino", "kg", "MAN", "Dolceria",
         "Mandorle a lamelle", ["Frutta a guscio"]),
    ]
    ing_id = {}
    for nome, cons, um, sigla, marca, denom, alls in ingredienti:
        cur = conn.execute(
            "INSERT INTO prodotti (nome, conservazione, unita_misura, sigla, "
            "marca, denominazione_legale) VALUES (?, ?, ?, ?, ?, ?)",
            (nome, cons, um, sigla, marca, denom))
        ing_id[nome] = cur.lastrowid
        for a in alls:
            conn.execute(
                "INSERT INTO prodotti_allergeni (prodotto_id, allergene_id) "
                "SELECT ?, id FROM allergeni WHERE nome = ?", (cur.lastrowid, a))

    # ---- Prodotti di laboratorio (con famiglia) ----
    crp = conn.execute("SELECT id FROM famiglie WHERE nome = 'Creme'").fetchone()[0]
    dol = conn.execute("SELECT id FROM famiglie WHERE nome = 'Dolci finiti'").fetchone()[0]
    crema = conn.execute(
        "INSERT INTO prodotti (nome, famiglia_id, unita_misura, sigla) "
        "VALUES (?, ?, 'kg', 'CRP')", ("Crema pasticcera", crp)).lastrowid
    bigne = conn.execute(
        "INSERT INTO prodotti (nome, famiglia_id, unita_misura, sigla) "
        "VALUES (?, ?, 'pz', 'BIG')", ("Bignè", dol)).lastrowid

    # ---- Ricette (master) ----
    ric_crema = conn.execute(
        "INSERT INTO ricette (prodotto_id, famiglia_id, resa, procedimento) "
        "VALUES (?, ?, '5 kg', 'Scaldare il latte con metà zucchero senza bollire. "
        "Montare tuorli, zucchero rimasto e amido. Versare il latte caldo, "
        "riportare in pentola e cuocere girando finché vela il cucchiaio. "
        "Raffreddare veloce, frigo 24-48h max.')", (crema, crp)).lastrowid
    for nome, qta in [("Latte fresco intero", 4), ("Uova pastorizzate liquide", 2),
                      ("Zucchero semolato", 1.5)]:
        conn.execute(
            "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
            "VALUES (?, ?, ?)", (ric_crema, ing_id[nome], qta))

    # Ricetta del bignè: crema 3 kg + uova dirette 0.5 (fusione in etichetta)
    ric_bigne = conn.execute(
        "INSERT INTO ricette (prodotto_id, famiglia_id, resa, procedimento) "
        "VALUES (?, ?, '60 pz', 'Portare acqua, burro e sale a bollore, gettare "
        "la farina e asciugare sul fuoco mescolando. Fuori dal fuoco unire "
        "le uova poco per volta. Farcire con la crema solo a servizio.')",
        (bigne, dol)).lastrowid
    conn.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (?, ?, ?)", (ric_bigne, crema, 3))
    conn.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (?, ?, ?)", (ric_bigne, ing_id["Uova pastorizzate liquide"], 0.5))

    # ---- Arrivi (date relative: la dashboard mostra scadenze vere) ----
    # (ingrediente, fornitore, lotto, giorni_arrivo, giorni_scadenza, qta, prezzo, iva)
    arrivi = [
        ("Latte fresco intero", 1, "LAT2401", -5, 5, 20, 1.35, 4),
        ("Uova pastorizzate liquide", 1, "UOV8812", -5, 20, 10, 4.80, 4),
        ("Zucchero semolato", 3, "ZUC0042", -3, 300, 25, 1.10, 10),
        ("Farina 00", 2, "FAR5519", -2, 180, 10, 0.95, 5),
        ("Panna da pasticceria", 1, "PAN1123", -1, 2, 12, 4.20, 4),
        ("Mandorle a lamelle", 3, "MAN7781", -6, 90, 4, 12.50, 10),
    ]
    arr_id = {}
    for i, (nome, forn, lotto, g_arr, g_scad, qta, prezzo, iva) in enumerate(arrivi, start=1):
        cur = conn.execute(
            "INSERT INTO lotti_ingresso (prodotto_id, fornitore_id, marca, codice_lotto, "
            "data_arrivo, data_scadenza, quantita, quantita_residua, prezzo_unitario, iva) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ing_id[nome], forn, None, lotto, _g(g_arr), _g(g_scad),
             qta, qta, prezzo, iva))
        arr_id[i] = cur.lastrowid

    # ---- Produzioni (slave): crema ieri, bignè oggi ----
    def produzione(prodotto, sigla_padre, famiglia, giorni, giorni_scadenza, qta_prodotta, consumi):
        # famiglia SNAPSHOT dalla ricetta, come fa registra_produzione
        cur = conn.execute(
            "INSERT INTO lotti_interni (prodotto_id, famiglia_id, qta_prodotta, codice_lotto, "
            "data_produzione, data_scadenza) VALUES (?, ?, ?, ?, ?, ?)",
            (prodotto, famiglia, qta_prodotta, genera_codice(
                conn, {"nome": "", "sigla": sigla_padre}, _g(giorni)),
             _g(giorni), _g(giorni_scadenza)))
        lid = cur.lastrowid
        for origine, lotto_id, qta in consumi:
            conn.execute(
                "INSERT INTO consumi (lotto_interno_id, origine, lotto_origine_id, "
                "quantita_usata) VALUES (?, ?, ?, ?)", (lid, origine, lotto_id, qta))
        return lid

    # Crema: latte 4 (lotti in ingresso 1), uova 2 (lotto 2), zucchero 1.5 (lotto 3)
    crema_lotto = produzione(crema, "CRP", crp, -1, 2, 5, [
        ("ingresso", arr_id[1], 4), ("ingresso", arr_id[2], 2), ("ingresso", arr_id[3], 1.5)])

    # Bignè: crema 3 kg + uova dirette 0.5 (dimostra la fusione in etichetta)
    produzione(bigne, "BIG", dol, 0, 3, 60, [
        ("interno", crema_lotto, 3), ("ingresso", arr_id[2], 0.5)])


def main():
    conn = inizializza()
    gia_dati = conn.execute("SELECT COUNT(*) FROM fornitori").fetchone()[0]
    if gia_dati and "--reset" not in sys.argv:
        print("Il database contiene già dati: nessun inserimento.")
        print("Per ricaricare la demo da zero:  python -m app.seed --reset")
        return
    if "--reset" in sys.argv:
        print("Svuoto il database...")
        for tabella in ["consumi", "ricette_righe", "ricette", "lotti_interni",
                        "lotti_ingresso", "prodotti_allergeni", "allegati",
                        "prodotti", "allergeni", "famiglie", "fornitori"]:
            conn.execute(f"DELETE FROM {tabella}")
    print("Inserisco i dati di prova...")
    seed(conn)
    conn.commit()
    print("Fatto: fornitori, ingredienti, ricette, arrivi e produzioni demo sono a database.")
    print("Ora apri http://127.0.0.1:8000 e guarda la dashboard.")


if __name__ == "__main__":
    main()
