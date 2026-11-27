import pytest

from app import db
from app.logic.anagrafiche import (
    ErroreAnagrafica,
    aggiungi_densita_custom,
    allergeni_da_ricetta,
    crea_ingrediente,
    crea_unita,
    dettaglio_fornitore,
    dettaglio_prodotto,
    elimina_densita_custom,
    elimina_fornitore,
    elimina_prodotto,
    elimina_unita,
    garantisci_allergeni_di_legge,
    lista_anagrafica,
    lista_candidati,
    lista_densita_custom,
    lista_ingredienti,
    lista_prodotti,
    lista_unita,
    rinomina_famiglia,
    rinomina_unita,
    salva_fornitore,
    salva_prodotto,
)


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    for i, (nome, desc) in enumerate([
        ("Latte", "latte e derivati"), ("Uova", "uova e prodotti a base di uova"),
        ("Frutta a guscio", "mandorle, nocciole, ecc."),
    ], start=1):
        c.execute("INSERT INTO allergeni (id, nome, descrizione) VALUES (?, ?, ?)",
                  (i, nome, desc))
    c.execute("INSERT INTO fornitori (id, nome, piva) VALUES (1, 'Caseificio', 'IT012')")
    c.execute("INSERT INTO fornitori (id, nome) VALUES (2, 'Libero')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (1, 'Creme')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (2, 'Dolci finiti')")
    # ingrediente con conservazione (obbligatoria alla nascita) e allergene
    c.execute(
        "INSERT INTO prodotti (id, nome, conservazione, unita_misura, sigla, "
        "marca, denominazione_legale) "
        "VALUES (1, 'Latte intero', 'Frigo', 'lt', 'LAT', 'Mucca', 'Latte fresco intero')"
    )
    c.execute(
        "INSERT INTO prodotti_allergeni (prodotto_id, allergene_id) VALUES (1, 1)"
    )
    c.execute(
        "INSERT INTO prodotti (id, nome, conservazione, unita_misura, marca, "
        "denominazione_legale) VALUES (2, 'Uova', 'Frigo', 'pz', 'Gallina', 'Uova fresche')"
    )
    c.execute(
        "INSERT INTO prodotti_allergeni (prodotto_id, allergene_id) VALUES (2, 2)"
    )
    # prodotti di laboratorio con famiglia
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, unita_misura, sigla) "
        "VALUES (3, 'Crema pasticcera', 1, 'kg', 'CRP')"
    )
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, unita_misura, sigla) "
        "VALUES (4, 'Bignè', 2, 'pz', 'BGN')"
    )
    # candidato: nato da "nuovo prodotto", senza famiglia e senza ricetta
    c.execute(
        "INSERT INTO prodotti (id, nome, unita_misura, sigla) "
        "VALUES (5, 'Tortina', 'pz', 'TOR')"
    )
    # ricette: la crema usa latte, il bignè usa la crema (ricorsione allergeni)
    c.execute("INSERT INTO ricette (id, prodotto_id, famiglia_id, resa) VALUES (10, 3, 1, '2 kg')")
    c.execute("INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) VALUES (10, 1, 2)")
    c.execute("INSERT INTO ricette (id, prodotto_id, famiglia_id, resa) VALUES (11, 4, 2, '60 pz')")
    c.execute("INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) VALUES (11, 3, 1)")
    # un arrivo del latte (prezzo e IVA per i totali CALCOLATI)
    c.execute(
        "INSERT INTO lotti_ingresso (id, prodotto_id, fornitore_id, codice_lotto, "
        "data_arrivo, data_scadenza, quantita, quantita_residua, prezzo_unitario, iva) "
        "VALUES (100, 1, 1, 'LAT-A', '2026-11-10', '2026-11-20', 10, 10, 2, 10)"
    )
    # il seed delle u.m. come fa il server a ogni avvio (RIFIN 34)
    db.popola_unita_misura(c)
    c.commit()
    yield c
    c.close()


INGREDIENTE = {
    "id": 1, "nome": "Latte intero", "conservazione": "Frigo",
    "unita_misura": "lt", "sigla": "LAT", "marca": "Mucca",
    "denominazione_legale": "Latte fresco intero", "note": None,
    "allergeni": [1],
}


# ---- liste: il discriminante ingrediente / prodotto / candidato ----

def test_le_card_separano_ingredienti_prodotti_e_candidati(conn):
    assert [p["nome"] for p in lista_ingredienti(conn)] == ["Latte intero", "Uova"]
    # GERARCHIA STRETTA: senza ricetta non è (ancora) un prodotto,
    # la card lo nasconde finché non nasce la sua ricetta
    lab = lista_prodotti(conn)
    assert [p["nome"] for p in lab] == ["Bignè", "Crema pasticcera"]
    assert all(p["ha_ricetta"] is True for p in lab)


def test_il_candidato_senza_ricetta_e_nel_mondo_ma_non_in_card(conn):
    # Tortina (nato dal "➕", mai completato) resta a database ed è raggiungibile
    # dalla sezione Ricette (candidati), ma la card Prodotti non lo mostra
    assert conn.execute(
        "SELECT nome FROM prodotti WHERE id = 5"
    ).fetchone()["nome"] == "Tortina"
    assert "Tortina" not in [p["nome"] for p in lista_prodotti(conn)]


def test_lista_anagrafica_classifica_per_tipo_non_per_famiglia(conn):
    # RIFIN 46, il caso "Torta al cioccolato tra gli ingredienti": il pool
    # grezzo che alimenta le tendine filtra per TIPO vero, non per famiglia:
    # il candidato senza ricetta (famiglia NULL) NON è un ingrediente
    ing = [p["nome"] for p in lista_anagrafica(conn, "ingrediente")]
    assert ing == ["Latte intero", "Uova"]        # Tortina NON c'è più
    prod = [p["nome"] for p in lista_anagrafica(conn, "prodotto")]
    assert "Tortina" in prod                      # è un prodotto in attesa:
    # raggiungibile dal combo "Prodotto" della Nuova ricetta per completarlo
    assert "Crema pasticcera" in prod
    assert not set(ing) & set(prod)               # ogni riga: UNA identità
    assert len(lista_anagrafica(conn)) == len(ing) + len(prod)


def test_lista_prodotti_filtro_famiglia(conn):
    assert [p["nome"] for p in lista_prodotti(conn, famiglia_id=1)] == ["Crema pasticcera"]


def test_lista_ingredienti_trova_anche_per_marca(conn):
    assert [p["nome"] for p in lista_ingredienti(conn, "mucca")] == ["Latte intero"]


# ---- allergeni: dichiarati dall'ingrediente, EREDITATI dal prodotto ----

def test_allergeni_ereditati_con_ricorsione(conn):
    # il bignè non dichiara niente: eredita dalla ricetta, scendendo nella crema
    assert allergeni_da_ricetta(conn, 4) == ["Latte"]
    assert allergeni_da_ricetta(conn, 3) == ["Latte"]
    assert allergeni_da_ricetta(conn, 5) == []            # senza ricetta: niente


def test_allergeni_sommati_senza_ripetizioni(conn):
    # il Latte arriva al bignè da TRE strade: latte diretto, panna (che
    # dichiara Latte) e la crema (che contiene latte): si SOMMANO le
    # fonti ma l'allergene compare UNA volta sola
    conn.execute(
        "INSERT INTO prodotti (id, nome, conservazione, unita_misura) "
        "VALUES (10, 'Panna', 'Frigo', 'lt')"
    )
    conn.execute(
        "INSERT INTO prodotti_allergeni (prodotto_id, allergene_id) VALUES (10, 1)"
    )
    conn.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (11, 10, 0.5), (11, 1, 1)"
    )
    conn.commit()
    ereditati = allergeni_da_ricetta(conn, 4)
    assert ereditati == ["Latte"]
    assert ereditati.count("Latte") == 1


def test_lista_prodotti_mostra_gli_allergeni_ereditati(conn):
    per_nome = {p["nome"]: p for p in lista_prodotti(conn)}
    assert per_nome["Bignè"]["allergeni"] == ["Latte"]
    assert per_nome["Crema pasticcera"]["allergeni"] == ["Latte"]


# ---- creazione ingrediente ----

def test_crea_ingrediente_da_anagrafica_richiede_denominazione(conn):
    dati = {"nome": "Farina 00", "conservazione": "Magazzino",
            "unita_misura": "kg", "denominazione_legale": ""}
    with pytest.raises(ErroreAnagrafica, match="denominazione legale"):
        crea_ingrediente(conn, dati, da_anagrafica=True)
    dati["denominazione_legale"] = "Farina di grano tenero tipo 00"
    p = crea_ingrediente(conn, dati, da_anagrafica=True)
    assert p["tipo"] == "ingrediente"
    assert p["denominazione_legale"] == "Farina di grano tenero tipo 00"


def test_crea_ingrediente_validazioni(conn):
    with pytest.raises(ErroreAnagrafica, match="Conservazione"):
        crea_ingrediente(conn, {"nome": "X", "conservazione": "Cantina",
                                "unita_misura": "kg"}, da_anagrafica=False)
    with pytest.raises(ErroreAnagrafica, match="Unità di misura"):
        crea_ingrediente(conn, {"nome": "X", "conservazione": "Frigo",
                                "unita_misura": " "}, da_anagrafica=False)
    with pytest.raises(ErroreAnagrafica, match="sconosciuto"):
        crea_ingrediente(conn, {"nome": "X", "conservazione": "Frigo",
                                "unita_misura": "kg", "allergeni": [99]},
                         da_anagrafica=False)


def test_crea_ingrediente_rapido_salva_gli_allergeni(conn):
    # il "➕ Nuovo ingrediente" del form arrivi: gli allergeni si
    # dichiarano già lì, non si aspetta la scheda anagrafica
    p = crea_ingrediente(conn, {"nome": "Pasta sfoglia pronta",
                                "conservazione": "Freezer",
                                "unita_misura": "kg",
                                "allergeni": [1, 2]}, da_anagrafica=False)
    assert p["tipo"] == "ingrediente"
    assert [a["nome"] for a in p["allergeni"]] == ["Latte", "Uova"]


# ---- allergeni di legge: i 14 del Reg. UE 1169/2011 ----

def test_garantisci_allergeni_di_legge_senza_duplicati(conn):
    # anche su un DB nato col vecchio seed demo a 4 allergeni:
    # chi manca si aggiunge, chi c'è resta con il suo id
    garantisci_allergeni_di_legge(conn)
    n = conn.execute("SELECT COUNT(*) AS n FROM allergeni").fetchone()["n"]
    assert n == 14
    assert conn.execute(
        "SELECT id FROM allergeni WHERE nome = 'Latte'"
    ).fetchone()["id"] == 1
    garantisci_allergeni_di_legge(conn)      # idempotente
    assert conn.execute("SELECT COUNT(*) AS n FROM allergeni").fetchone()["n"] == 14


# ---- modifica ingrediente ----

def test_salva_ingrediente_sostituisce_gli_allergeni(conn):
    p = salva_prodotto(conn, {**INGREDIENTE, "allergeni": [1, 3]})
    assert [a["nome"] for a in p["allergeni"]] == ["Latte", "Frutta a guscio"]
    p = salva_prodotto(conn, {**INGREDIENTE, "allergeni": [2]})
    assert [a["nome"] for a in p["allergeni"]] == ["Uova"]


def test_salva_ingrediente_validazioni(conn):
    with pytest.raises(ErroreAnagrafica, match="denominazione"):
        salva_prodotto(conn, {**INGREDIENTE, "denominazione_legale": " "})
    with pytest.raises(ErroreAnagrafica, match="Conservazione"):
        salva_prodotto(conn, {**INGREDIENTE, "conservazione": "Cantina"})
    with pytest.raises(ErroreAnagrafica, match="nome"):
        salva_prodotto(conn, {**INGREDIENTE, "nome": " "})


def test_salva_prodotto_lab_rifiuta_allergeni_dichiarati(conn):
    with pytest.raises(ErroreAnagrafica, match="ereditano"):
        salva_prodotto(conn, {"id": 3, "nome": "Crema pasticcera",
                              "unita_misura": "kg", "allergeni": [1]})


def test_salva_prodotto_lab_modifica_nome_e_sigla(conn):
    p = salva_prodotto(conn, {"id": 3, "nome": "Crema pasticcera",
                               "unita_misura": "kg", "sigla": "crm"})
    assert p["nome"] == "Crema pasticcera"
    assert p["sigla"] == "CRM"          # le sigle dei lotti sono MAIUSCOLE
    assert p["famiglia"] == "Creme"     # resta quella della ricetta (master)


def test_salva_prodotto_lab_um_opzionale(conn):
    # l'u.m. del prodotto NON serve più: se il salvataggio non la manda,
    # resta quella storica (i vecchi dati non si buttano via)
    p = salva_prodotto(conn, {"id": 3, "nome": "Crema pasticcera", "sigla": "CRM"})
    assert p["unita_misura"] == "kg"


# ---- dettagli ----

def test_dettaglio_ingrediente_con_arrivi_e_totali_calcolati(conn):
    p = dettaglio_prodotto(conn, 1)
    assert p["tipo"] == "ingrediente"
    assert p["n_arrivi"] == 1
    a = p["arrivi"][0]
    assert a["codice_lotto"] == "LAT-A"
    assert a["totale"] == 20.0          # 10 x €2, CALCOLATO
    assert a["totale_iva"] == 22.0      # +10%


def test_dettaglio_prodotto_con_produzioni_recenti(conn):
    conn.execute(
        "INSERT INTO lotti_interni (id, prodotto_id, famiglia_id, qta_prodotta, "
        "codice_lotto, data_produzione, data_scadenza) "
        "VALUES (300, 3, 1, 2, 'CRP-20261116-01', '2026-11-16', '2026-11-20')"
    )
    conn.commit()
    p = dettaglio_prodotto(conn, 3)
    assert p["tipo"] == "prodotto"
    assert p["ha_ricetta"] is True
    assert p["n_produzioni"] == 1
    assert p["produzioni"][0]["codice_lotto"] == "CRP-20261116-01"
    assert p["allergeni"] == ["Latte"]


def test_dettaglio_prodotto_candidato(conn):
    p = dettaglio_prodotto(conn, 5)
    assert p["tipo"] == "prodotto"      # nato da "nuovo prodotto": non è un ingrediente
    assert p["ha_ricetta"] is False
    assert p["famiglia"] is None


def test_dettaglio_fornitore_con_arrivi(conn):
    f = dettaglio_fornitore(conn, 1)
    assert f["nome"] == "Caseificio"
    assert f["n_arrivi"] == 1
    assert f["arrivi"][0]["prodotto"] == "Latte intero"


# ---- famiglie: rinomina che si propaga ----

def test_rinomina_famiglia_si_propaga_ovunque(conn):
    rinomina_famiglia(conn, 1, "Creme al cucchiaio")
    assert dettaglio_prodotto(conn, 3)["famiglia"] == "Creme al cucchiaio"
    per_nome = {p["nome"]: p for p in lista_prodotti(conn)}
    assert per_nome["Crema pasticcera"]["famiglia"] == "Creme al cucchiaio"


def test_rinomina_famiglia_rifiuta_duplicati_case_insensitive(conn):
    with pytest.raises(ErroreAnagrafica, match="Esiste già"):
        rinomina_famiglia(conn, 2, "creme")
    with pytest.raises(ErroreAnagrafica, match="obbligatorio"):
        rinomina_famiglia(conn, 1, "  ")


# ---- eliminazioni PROTETTE ----

def test_elimina_prodotto_protetto_con_arrivi(conn):
    with pytest.raises(ErroreAnagrafica, match="protetta"):
        elimina_prodotto(conn, 1)      # il latte è arrivato


def test_elimina_prodotto_protetto_con_ricetta(conn):
    with pytest.raises(ErroreAnagrafica, match="ricetta"):
        elimina_prodotto(conn, 3)      # la crema è il master di una ricetta


def test_elimina_prodotto_libero(conn):
    elimina_prodotto(conn, 2)          # uova senza arrivi né ricetta
    elimina_prodotto(conn, 5)          # candidato mai usato
    assert conn.execute("SELECT COUNT(*) FROM prodotti").fetchone()[0] == 3


def test_elimina_fornitore_protetto_e_libero(conn):
    with pytest.raises(ErroreAnagrafica, match="protetta"):
        elimina_fornitore(conn, 1)
    elimina_fornitore(conn, 2)         # nessun arrivo: si elimina
    assert conn.execute("SELECT COUNT(*) FROM fornitori").fetchone()[0] == 1


# ---- fornitore: modifica ----

def test_salva_fornitore_aggiorna_i_contatti(conn):
    f = salva_fornitore(conn, {
        "id": 1, "nome": "Caseificio Valle", "piva": "IT999",
        "telefono": "06 123456", "email": "info@valle.it", "note": "consegna il martedì",
    })
    assert f["nome"] == "Caseificio Valle"
    assert f["telefono"] == "06 123456"
    with pytest.raises(ErroreAnagrafica, match="ragione sociale"):
        salva_fornitore(conn, {"id": 1, "nome": " ", "piva": None,
                               "telefono": None, "email": None, "note": None})


# ---- Unità di misura (RIFIN 34) ----

def test_seed_delle_unita_riporta_quelle_usate():
    # il seed di inizializza() ritrova da SOLO le u.m. già usate dai
    # prodotti + le 4 di sistema, senza toccare le modifiche dell'utente
    import os
    import tempfile
    percorso = os.path.join(tempfile.gettempdir(), "test_seed_um.db")
    if os.path.exists(percorso):
        os.remove(percorso)
    c = db.inizializza(percorso)   # DB NUOVO: nessun prodotto ancora
    nomi = [r["nome"] for r in c.execute("SELECT nome FROM unita_misura").fetchall()]
    assert set(nomi) == {"g", "kg", "ml", "lt"}
    c.execute(
        "INSERT INTO prodotti (nome, conservazione, unita_misura) "
        "VALUES ('Pirottini', 'Magazzino', 'pz')"
    )
    c.commit()
    c.close()
    c = db.inizializza(percorso)   # secondo avvio: il seed è idempotente
    nomi = [r["nome"] for r in c.execute("SELECT nome FROM unita_misura").fetchall()]
    assert set(nomi) == {"g", "kg", "ml", "lt", "pz"}
    c.close()
    os.remove(percorso)


def test_crea_unita_e_rifiuta_duplicati(conn):
    u = crea_unita(conn, "vassoi")
    assert u["nome"] == "vassoi"
    with pytest.raises(ErroreAnagrafica, match="già"):
        crea_unita(conn, "VASSOI")   # il confronto non respira mai il maiuscolo
    with pytest.raises(ErroreAnagrafica, match="obbligatorio"):
        crea_unita(conn, "   ")
    with pytest.raises(ErroreAnagrafica, match="sistema"):
        crea_unita(conn, "kg")      # le 4 di sistema esistono già per legge


def test_lista_unita_conta_i_prodotti_e_marchia_le_di_sistema(conn):
    crea_unita(conn, "vassoi")
    righe = {r["nome"]: r for r in lista_unita(conn)}
    assert righe["kg"]["sistema"] is True
    assert righe["vassoi"]["sistema"] is False
    assert righe["pz"]["n_prodotti"] == 3   # uova, bignè e tortina


def test_rinomina_unita_si_propaga_ai_prodotti(conn):
    u = crea_unita(conn, "teglie")
    conn.execute(
        "UPDATE prodotti SET unita_misura = 'teglie' WHERE id = 5"
    )
    r = rinomina_unita(conn, u["id"], "teglia")
    assert r["n_prodotti_aggiornati"] == 1
    assert conn.execute(
        "SELECT unita_misura FROM prodotti WHERE id = 5"
    ).fetchone()["unita_misura"] == "teglia"


def test_le_unita_di_sistema_non_si_toccano(conn):
    righe = [r for r in lista_unita(conn) if r["sistema"]]
    assert {r["nome"] for r in righe} == {"g", "kg", "ml", "lt"}
    kg_id = conn.execute(
        "SELECT id FROM unita_misura WHERE nome = 'kg'").fetchone()["id"]
    with pytest.raises(ErroreAnagrafica, match="sistema"):
        rinomina_unita(conn, kg_id, "kili")
    with pytest.raises(ErroreAnagrafica, match="sistema"):
        elimina_unita(conn, kg_id)


def test_elimina_unita_solo_se_libera(conn):
    u = crea_unita(conn, "vassoi")
    elimina_unita(conn, u["id"])      # mai usata: via
    pz_id = conn.execute(
        "SELECT id FROM unita_misura WHERE nome = 'pz'").fetchone()["id"]
    with pytest.raises(ErroreAnagrafica, match="In uso"):
        elimina_unita(conn, pz_id)     # 3 prodotti la usano: bloccata


# ---- RIFIN 45: il nome non resta mai intrappolato (creazione ingrediente) ----

def test_crea_ingrediente_duplicato_respinto_con_indicazioni(conn):
    # il nome di un ingrediente VERO non si prende due volte (prima il
    # controllo NON esisteva affatto): il messaggio dice dov'è la scheda
    with pytest.raises(ErroreAnagrafica, match="esiste già"):
        crea_ingrediente(conn, {
            "nome": "latte INTERO", "conservazione": "Frigo",
            "unita_misura": "lt", "denominazione_legale": "Latte fresco"})
    with pytest.raises(ErroreAnagrafica, match="card Ingredienti"):
        crea_ingrediente(conn, {
            "nome": "Latte intero", "conservazione": "Frigo",
            "unita_misura": "lt", "denominazione_legale": "Latte fresco"})


def test_crea_ingrediente_riusa_il_candidato_abbandonato(conn):
    # il caso "Torta al cioccolato": una riga nata da un ➕ mai completato
    # (niente famiglia/conservazione/storia) si COMPLETA, stesso id
    conn.execute("INSERT INTO prodotti (nome) VALUES ('Torta al cioccolato')")
    fantasma_id = conn.execute(
        "SELECT id FROM prodotti WHERE nome = 'Torta al cioccolato'").fetchone()["id"]
    p = crea_ingrediente(conn, {
        "nome": "torta al cioccolato", "conservazione": "Frigo",
        "unita_misura": "kg", "denominazione_legale": "Torta al cioccolato",
        "allergeni": [1, 2]})
    assert p["id"] == fantasma_id          # riusata, non duplicata
    assert p["conservazione"] == "Frigo"   # ...e completata per davvero
    # gli allergeni dichiarati alla nascita viaggiano nella scheda
    assert sorted(a["id"] for a in p["allergeni"]) == [1, 2]
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM prodotti "
        "WHERE LOWER(nome) = LOWER('Torta al cioccolato')").fetchone()["n"]
    assert n == 1


# ---- RIFIN 47: i candidati VISIBILI e gestibili dalla card Prodotti ----

def test_lista_candidati_solo_gli_abbandonati(conn):
    # Tortina (id 5): nata dal ➕, mai completata. Crema/Bignè hanno ricetta,
    # Latte/Uova sono ingredienti: UN solo candidato in lista
    cand = lista_candidati(conn)
    assert [c["nome"] for c in cand] == ["Tortina"]
    assert cand[0]["id"] == 5            # il pannello Completa/Elimina
    # lo completa la ricetta: e il candidato SPARISCE
    fam = conn.execute("SELECT id FROM famiglie WHERE nome = 'Creme'").fetchone()["id"]
    conn.execute(
        "INSERT INTO ricette (prodotto_id, famiglia_id, resa) VALUES (5, ?, '8 pz')",
        (fam,))
    conn.commit()
    assert lista_candidati(conn) == []


# ---- RIFIN 51: la densità (g/ml) vive nella scheda dell'ingrediente ----

def test_ingrediente_con_densita_e_modifica(conn):
    # il fixture ha già il suo "Latte intero": qui serve un liquido NUOVO
    p = crea_ingrediente(conn, {"nome": "Olio di semi", "conservazione": "Magazzino",
                                "unita_misura": "lt", "densita": 1.03},
                         da_anagrafica=False)
    assert p["densita"] == 1.03
    # la MODIFICA (PUT anagrafica) la aggiorna: il dato resta dell'utente
    salva_prodotto(conn, {"id": p["id"], "nome": "Olio di semi",
                          "conservazione": "Magazzino", "unita_misura": "lt",
                          "denominazione_legale": "olio di semi", "densita": 1.04})
    assert dettaglio_prodotto(conn, p["id"])["densita"] == 1.04
    # e si può anche togliere del tutto
    salva_prodotto(conn, {"id": p["id"], "nome": "Olio di semi",
                          "conservazione": "Magazzino", "unita_misura": "lt",
                          "denominazione_legale": "olio di semi"})
    assert dettaglio_prodotto(conn, p["id"])["densita"] is None


def test_ingrediente_densita_con_virgola_dei_pasticceri(conn):
    # "1,03" con la virgola si accetta: chi pesa 103 g su 100 ml
    # scrive quel che legge sulla bilancia
    p = crea_ingrediente(conn, {"nome": "Panna da montare", "conservazione": "Frigo",
                                "unita_misura": "lt", "densita": " 1,03 "},
                         da_anagrafica=False)
    assert p["densita"] == 1.03


def test_ingrediente_densita_sporca_respinta(conn):
    for lurida in (0, -1, "tanta"):
        with pytest.raises(ErroreAnagrafica, match="Densità"):
            crea_ingrediente(conn, {"nome": "Sciroppo di prova", "conservazione": "Magazzino",
                                    "unita_misura": "lt", "densita": lurida},
                             da_anagrafica=False)


def test_densita_custom_aggiunta_normalizzata_e_aggiornata(conn):
    # RIFIN 52: "Caffè" diventa "caffe" (minuscolo, senza accenti);
    # ripetere la parola AGGIORNA il valore, non duplica la riga
    v = aggiungi_densita_custom(conn, {"parola": "  Caffè  ", "densita": 0.98})
    assert v == {"parola": "caffe", "densita": 0.98}
    v = aggiungi_densita_custom(conn, {"parola": "CAFFÈ", "densita": 1.02})
    assert v["densita"] == 1.02
    assert lista_densita_custom(conn) == [{"parola": "caffe", "densita": 1.02}]


def test_densita_custom_sporca_respinta(conn):
    # parola vuota o densità lurida: niente, come per l'anagrafica
    with pytest.raises(ErroreAnagrafica, match="obbligatoria"):
        aggiungi_densita_custom(conn, {"parola": "   ", "densita": 1.03})
    with pytest.raises(ErroreAnagrafica, match="maggiore di zero"):
        aggiungi_densita_custom(conn, {"parola": "sciroppo d'acero", "densita": "tanta"})


def test_densita_custom_eliminata(conn):
    aggiungi_densita_custom(conn, {"parola": "sciroppo d'acero", "densita": "1,10"})
    # anche eliminando con accenti/maiuscole: la voce è quella
    elimina_densita_custom(conn, "Sciroppo D'Acero")
    assert lista_densita_custom(conn) == []
    elimina_densita_custom(conn, "mai esistita")  # via tranquilla (idempotente)


def test_densita_custom_sovrascrive_il_suggerimento(conn):
    # la somma dei due mondi: la voce dell'utente entra nel suggerimento
    from app.logic.um import densita_suggerita
    aggiungi_densita_custom(conn, {"parola": "latte crudo", "densita": 1.035})
    assert densita_suggerita(conn, "Latte crudo fresco") == ("latte crudo", 1.035)
    assert densita_suggerita(conn, "Latte fresco") == ("latte", 1.03)


def test_creazione_eredita_densita_dalla_tabella(conn):
    # RIFIN 53: crei "Latte fresco di malga" da QUALSIASI form senza densità
    # → il backend la prende dalla tabella (la stessa del "Latte intero")
    p = crea_ingrediente(conn, {"nome": "Latte fresco di malga", "conservazione": "Frigo",
                                "unita_misura": "lt"}, da_anagrafica=False)
    assert p["densita"] == 1.03


def test_creazione_densita_scritta_vince_sulla_tabella(conn):
    p = crea_ingrediente(conn, {"nome": "Olio di oliva", "conservazione": "Magazzino",
                                "unita_misura": "lt", "densita": 0.916},
                         da_anagrafica=False)
    assert p["densita"] == 0.916   # non lo 0,92 del catalogo


def test_creazione_senza_match_niente_densita_auto(conn):
    p = crea_ingrediente(conn, {"nome": "Farina di riso", "conservazione": "Magazzino",
                                "unita_misura": "kg"}, da_anagrafica=False)
    assert p["densita"] is None


def test_fantasma_reuse_eredita_densita(conn):
    # il candidato abbandonato riprende la stessa strada: nome → tabella
    conn.execute("INSERT INTO prodotti (nome, unita_misura) VALUES ('Latte crudo', 'lt')")
    p = crea_ingrediente(conn, {"nome": "Latte crudo", "conservazione": "Frigo",
                                "unita_misura": "lt"}, da_anagrafica=False)
    assert p["densita"] == 1.03


# ---- RIFIN 58: flag "semilavorato" (solo dichiarativo, badge anagrafica) ----

def test_crea_ingrediente_semilavorato_e_ritornato_dal_dettaglio(conn):
    p = crea_ingrediente(conn, {
        "nome": "Crema al pistacchio", "conservazione": "Frigo",
        "unita_misura": "kg",
        "denominazione_legale": "pistacchio, zucchero, olio di girasole",
        "semilavorato": True,
    }, da_anagrafica=True)
    assert p["semilavorato"] == 1
    # e la lista ingredienti lo porta (badge in tabella)
    riga = [x for x in lista_ingredienti(conn) if x["id"] == p["id"]]
    assert riga and riga[0]["semilavorato"] == 1


def test_salva_prodotto_modifica_il_flag_semilavorato(conn):
    p = crea_ingrediente(conn, {
        "nome": "Crema al pistacchio", "conservazione": "Frigo",
        "unita_misura": "kg",
        "denominazione_legale": "pistacchio, zucchero, olio di girasole",
    }, da_anagrafica=True)
    assert p["semilavorato"] == 0
    q = salva_prodotto(conn, {**INGREDIENTE, "id": p["id"],
                              "nome": "Crema al pistacchio",
                              "denominazione_legale": "pistacchio, zucchero, olio di girasole",
                              "semilavorato": True})
    assert q["semilavorato"] == 1
