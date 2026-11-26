import pytest

from app import db
from app.logic.arrivi import (
    ErroreArrivo, azzera_lotto, elimina_arrivo, registra_arrivo,
    ripristina_lotto,
)


@pytest.fixture()
def conn():
    c = db.connessione(":memory:")
    with open(db.SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.execute("INSERT INTO fornitori (id, nome) VALUES (1, 'Caseificio Valle')")
    c.execute("INSERT INTO fornitori (id, nome) VALUES (2, 'Grossista')")
    c.execute("INSERT INTO famiglie (id, nome) VALUES (1, 'Creme')")
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, marca, unita_misura) "
        "VALUES (1, 'Latte intero', NULL, 'Mucca Felice', 'lt')"
    )
    c.execute(
        "INSERT INTO prodotti (id, nome, famiglia_id, sigla) "
        "VALUES (2, 'Crema pasticcera', 1, 'CRP')"
    )
    c.commit()
    yield c
    c.close()


def arrivo(**extra):
    base = {
        "prodotto_id": 1,
        "fornitore_id": 1,
        "codice_lotto": "L2607A",
        "data_arrivo": "2026-11-16",
        "data_scadenza": "2026-11-23",
        "quantita": 10,
    }
    base.update(extra)
    return base


def test_arrivo_valido_immette_in_magazzino(conn):
    lotto = registra_arrivo(conn, arrivo())
    assert lotto["prodotto"] == "Latte intero"
    assert lotto["fornitore"] == "Caseificio Valle"
    assert lotto["um"] == "lt"
    assert lotto["quantita_residua"] == 10    # residua = quantita: il magazzino parte da qui
    assert lotto["marca"] == "Mucca Felice"   # default dall'anagrafica


def test_marca_del_lotto_vince_sul_default(conn):
    lotto = registra_arrivo(conn, arrivo(marca="Altri Marchi"))
    assert lotto["marca"] == "Altri Marchi"


def test_nota_della_consegna_ritornata_una_volta_salvata(conn):
    lotto = registra_arrivo(conn, arrivo(nota="  confezione da 5 kg, granulometria fine  "))
    assert lotto["nota"] == "confezione da 5 kg, granulometria fine"


def test_senza_nota_il_campo_resta_vuoto(conn):
    lotto = registra_arrivo(conn, arrivo())
    assert lotto["nota"] is None
    lotto_spoglia = registra_arrivo(conn, arrivo(codice_lotto="L2607B", nota="   "))
    assert lotto_spoglia["nota"] is None


def test_duplicato_respinto(conn):
    registra_arrivo(conn, arrivo())
    with pytest.raises(ErroreArrivo):
        registra_arrivo(conn, arrivo())               # stesso prodotto+lotto+fornitore
    # stesso lotto ma altro fornitore: valido
    lotto2 = registra_arrivo(conn, arrivo(fornitore_id=2))
    assert lotto2["fornitore"] == "Grossista"


def test_prodotto_di_laboratorio_non_arriva(conn):
    # "famiglia -> ricetta": un semilavorato nasce da una produzione, non da un arrivo
    with pytest.raises(ErroreArrivo, match="laboratorio"):
        registra_arrivo(conn, arrivo(prodotto_id=2))


def test_scadenza_prima_dell_arrivo_respinta(conn):
    with pytest.raises(ErroreArrivo, match="scadenza"):
        registra_arrivo(conn, arrivo(data_arrivo="2026-11-16", data_scadenza="2026-11-15"))


def test_quantita_nulla_o_negativa_respinta(conn):
    for q in (0, -3, None, "abc"):
        with pytest.raises(ErroreArrivo, match="quantità"):
            registra_arrivo(conn, arrivo(quantita=q))


def test_riferimenti_inesistenti_respinti(conn):
    with pytest.raises(ErroreArrivo, match="inesistente"):
        registra_arrivo(conn, arrivo(prodotto_id=99))
    with pytest.raises(ErroreArrivo, match="inesistente"):
        registra_arrivo(conn, arrivo(fornitore_id=99))


def test_codice_lotto_obbligatorio(conn):
    with pytest.raises(ErroreArrivo, match="obbligatorio"):
        registra_arrivo(conn, arrivo(codice_lotto="   "))


def test_nessuna_scrittura_parziale_su_errore(conn):
    # un arrivo respinto NON lascia righe nel database
    with pytest.raises(ErroreArrivo):
        registra_arrivo(conn, arrivo(quantita=0))
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 0


# ---- elimina_arrivo (eliminazione protetta) ----

def test_elimina_arrivo_senza_consumi_rimuove_il_lotto(conn):
    lotto = registra_arrivo(conn, arrivo())
    elimina_arrivo(conn, lotto["id"])
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 0


def test_elimina_arrivo_protetta_se_consumato(conn):
    from app.logic.produzioni import registra_produzione
    # una ricetta minima per consumare il latte del lotto
    conn.execute(
        "INSERT INTO ricette (id, prodotto_id, famiglia_id) VALUES (10, 1, 1)"
    )
    conn.execute(
        "INSERT INTO ricette_righe (ricetta_id, ingrediente_id, quantita) "
        "VALUES (10, 2, 1)"
    )
    conn.commit()
    lotto = registra_arrivo(conn, arrivo())
    registra_produzione(conn, {
        "prodotto_id": 1,
        "data_produzione": "2026-11-16",
        "data_scadenza": "2026-11-23",
        "qta_prodotta": 1,
        "consumi": [
            {"origine": "ingresso", "lotto_origine_id": lotto["id"], "quantita_usata": 2},
        ],
    })
    with pytest.raises(ErroreArrivo, match="protetta"):
        elimina_arrivo(conn, lotto["id"])
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 1  # il lotto resta: la tracciabilità non si riscrive


# --------- azzeramento manuale della residua (RIFIN 38, es. il bar) ---------

def test_azzeramento_porta_residua_a_zero_e_scrive_la_data(conn):
    lotto = registra_arrivo(conn, arrivo())
    azzera_lotto(conn, lotto["id"], oggi="2026-11-18")
    riga = conn.execute(
        "SELECT quantita_residua, data_esaurimento FROM lotti_ingresso WHERE id = ?",
        (lotto["id"],),
    ).fetchone()
    assert riga["quantita_residua"] == 0
    assert riga["data_esaurimento"] == "2026-11-18"
    # il lotto NON si cancella: la tracciabilità resta
    n = conn.execute("SELECT COUNT(*) FROM lotti_ingresso").fetchone()[0]
    assert n == 1


def test_azzeramento_doppio_respinge(conn):
    lotto = registra_arrivo(conn, arrivo())
    azzera_lotto(conn, lotto["id"], oggi="2026-11-18")
    with pytest.raises(ErroreArrivo, match="già"):
        azzera_lotto(conn, lotto["id"], oggi="2026-11-18")


def test_azzeramento_lotto_inesistente_respinge(conn):
    with pytest.raises(ErroreArrivo):
        azzera_lotto(conn, 999, oggi="2026-11-18")


# ---- ripristino di un lotto azzerato a mano (RIFIN 39: era uno sbaglio) ----

def test_ripristino_riporta_la_residua_fotografata_prima_dell_azzeramento(conn):
    lotto = registra_arrivo(conn, arrivo())
    # azzera la foto non parte da 10 ma dalla residua REALE (qui 4)
    conn.execute("UPDATE lotti_ingresso SET quantita_residua = 4 WHERE id = ?",
                 (lotto["id"],))
    conn.commit()
    azzera_lotto(conn, lotto["id"], oggi="2026-11-18")
    ripristina_lotto(conn, lotto["id"])
    riga = conn.execute(
        "SELECT quantita_residua, data_esaurimento, residua_pre_azzeramento "
        "FROM lotti_ingresso WHERE id = ?", (lotto["id"],),
    ).fetchone()
    assert riga["quantita_residua"] == 4        #NON 10: la foto era 4
    assert riga["data_esaurimento"] is None    # fuori da "Esauriti"
    assert riga["residua_pre_azzeramento"] is None  # la foto si consuma
    # e si può azzerare DI NUOVO: nasce una foto fresca
    azzera_lotto(conn, lotto["id"], oggi="2026-11-19")
    riga2 = conn.execute(
        "SELECT quantita_residua, residua_pre_azzeramento FROM lotti_ingresso WHERE id = ?",
        (lotto["id"],),
    ).fetchone()
    assert riga2["quantita_residua"] == 0
    assert riga2["residua_pre_azzeramento"] == 4


def test_ripristino_senza_foto_torna_alla_quantita_originale(conn):
    # lotti azzerati PRIMA della RIFIN 39: niente foto, si torna a quantita
    lotto = registra_arrivo(conn, arrivo())
    conn.execute(
        "UPDATE lotti_ingresso SET quantita_residua = 0, data_esaurimento = '2026-11-18' "
        "WHERE id = ?", (lotto["id"],),
    )
    conn.commit()
    ripristina_lotto(conn, lotto["id"])
    riga = conn.execute(
        "SELECT quantita_residua, data_esaurimento FROM lotti_ingresso WHERE id = ?",
        (lotto["id"],),
    ).fetchone()
    assert riga["quantita_residua"] == 10
    assert riga["data_esaurimento"] is None


def test_ripristino_lotto_mai_azzerato_respinge(conn):
    lotto = registra_arrivo(conn, arrivo())
    with pytest.raises(ErroreArrivo, match="non è stato azzerato"):
        ripristina_lotto(conn, lotto["id"])
    # anche il doppio ripristino è respinto: la foto si consuma al primo
    azzera_lotto(conn, lotto["id"], oggi="2026-11-18")
    ripristina_lotto(conn, lotto["id"])
    with pytest.raises(ErroreArrivo, match="non è stato azzerato"):
        ripristina_lotto(conn, lotto["id"])


def test_ripristino_lotto_inesistente_respinge(conn):
    with pytest.raises(ErroreArrivo):
        ripristina_lotto(conn, 999)
