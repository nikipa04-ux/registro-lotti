-- ============================================================
--  Registro Lotti - schema del database v0.1
--  Derivato dal prototipo e da docs/schema-db.md.
--  SQLite: un solo file, backup = copia della cartella dati.
-- ============================================================

-- Anagrafica fornitori
CREATE TABLE IF NOT EXISTS fornitori (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    piva TEXT,
    telefono TEXT,
    email TEXT,
    note TEXT
);

-- Famiglie dei prodotti di laboratorio (es. 'Creme', 'Dolci finiti')
CREATE TABLE IF NOT EXISTS famiglie (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- I 14 allergeni obbligatori (Reg. UE 1169/2011)
CREATE TABLE IF NOT EXISTS allergeni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    descrizione TEXT
);

-- Anagrafica prodotti: copre ingredienti acquistati E prodotti di laboratorio.
-- Una sola tabella, due identità:
--   ingrediente acquistato  -> famiglia_id NULL (marca, conservazione, denominazione_legale)
--   prodotto di laboratorio -> famiglia_id NOT NULL (eredita allergeni e lista
--                              ingredienti dalla ricetta: niente campi scritti a mano)
CREATE TABLE IF NOT EXISTS prodotti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    famiglia_id INTEGER REFERENCES famiglie(id),
    conservazione TEXT,              -- 'Frigo' | 'Freezer' | 'Magazzino' (solo ingredienti)
    unita_misura TEXT,              -- 'kg', 'lt', 'pz', 'uova'...
    sigla TEXT,                     -- per il codice lotto interno (es. CRP)
    marca TEXT,                     -- marca abituale (default per gli arrivi)
    denominazione_legale TEXT,      -- dicitura dell'etichetta d'acquisto, per l'etichetta
                                    -- dei prodotti finiti; obbligatoria per gli ingredienti
    note TEXT
);

-- Dichiarazione allergeni per INGREDIENTE (many-to-many).
-- I prodotti di laboratorio NON dichiarano: ereditano dalla ricetta.
CREATE TABLE IF NOT EXISTS prodotti_allergeni (
    prodotto_id INTEGER NOT NULL REFERENCES prodotti(id),
    allergene_id INTEGER NOT NULL REFERENCES allergeni(id),
    PRIMARY KEY (prodotto_id, allergene_id)
);

-- Lotti in ingresso (eventi di arrivo)
CREATE TABLE IF NOT EXISTS lotti_ingresso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prodotto_id INTEGER NOT NULL REFERENCES prodotti(id),
    fornitore_id INTEGER NOT NULL REFERENCES fornitori(id),
    marca TEXT,                     -- marca del LOTTO consegnato (default da prodotti.marca)
    codice_lotto TEXT NOT NULL,     -- lotto esterno del fornitore
    data_arrivo TEXT NOT NULL,      -- ISO 8601: 'YYYY-MM-DD'
    data_scadenza TEXT NOT NULL,
    quantita REAL,
    quantita_residua REAL,          -- giacenza del lotto, scaricata dai consumi
    prezzo_unitario REAL,           -- costo d'acquisto per u.m. (lo storico prezzi nasce qui)
    iva REAL,                       -- aliquota %: i totali sono CALCOLATI, non memorizzati
    UNIQUE (prodotto_id, codice_lotto, fornitore_id)
);

-- Lotti interni (eventi di produzione)
CREATE TABLE IF NOT EXISTS lotti_interni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prodotto_id INTEGER NOT NULL REFERENCES prodotti(id),
    famiglia_id INTEGER REFERENCES famiglie(id),  -- SNAPSHOT della famiglia di questa
                                                   -- produzione (può differire dalla ricetta)
    qta_prodotta REAL,              -- fondamentale per l'etichetta calcolata: attribuzione
                                     -- esatta degli ingredienti dei lotti interni consumati
    codice_lotto TEXT NOT NULL UNIQUE,  -- auto-generato: SIGLA-AAAAMMGG-NN
    data_produzione TEXT NOT NULL,
    data_scadenza TEXT NOT NULL
);

-- Consumo: quale lotto è stato usato in quale produzione.
-- 'origine' distingue un lotto in ingresso da un lotto interno (ricorsività:
-- la crema pasticcera consuma lotti in ingresso, il bignè consuma la crema).
-- I consumi sono IL VERBALE: giacenze, food cost, allergeni ed etichetta
-- si calcolano da qui, non si scrivono a mano.
CREATE TABLE IF NOT EXISTS consumi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lotto_interno_id INTEGER NOT NULL REFERENCES lotti_interni(id),
    origine TEXT NOT NULL CHECK (origine IN ('ingresso', 'interno')),
    lotto_origine_id INTEGER NOT NULL,
    quantita_usata REAL,
    UNIQUE (lotto_interno_id, origine, lotto_origine_id)
);

-- Ricetta master: una per prodotto di laboratorio
CREATE TABLE IF NOT EXISTS ricette (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prodotto_id INTEGER NOT NULL UNIQUE REFERENCES prodotti(id),
    famiglia_id INTEGER REFERENCES famiglie(id),  -- la famiglia nasce QUI (master)
    resa TEXT,                      -- es. '5 kg', '60 pz' (testo: lo capisce la logica)
    procedimento TEXT,              -- i passi della ricetta
    note TEXT
);

-- Righe di ricetta: ingredienti con quantità per dose completa.
-- ingrediente_id può puntare a un ingrediente acquistato O a un semilavorato
-- (ricorsività: la crema è "ingrediente" dei bignè).
CREATE TABLE IF NOT EXISTS ricette_righe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ricetta_id INTEGER NOT NULL REFERENCES ricette(id) ON DELETE CASCADE,
    ingrediente_id INTEGER NOT NULL REFERENCES prodotti(id),
    quantita REAL NOT NULL,
    UNIQUE (ricetta_id, ingrediente_id)
);

-- Allegati (DDT, certificati, foto): opzionali, il DB salva solo il percorso.
-- Per i documenti solo cartacei: riferimento_cartaceo (collocazione fisica).
CREATE TABLE IF NOT EXISTS allegati (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_file TEXT NOT NULL,
    percorso_relativo TEXT NOT NULL,   -- dentro la cartella dati dell'app
    origine TEXT NOT NULL CHECK (origine IN ('ingresso', 'interno')),
    lotto_id INTEGER NOT NULL,
    caricato_il TEXT NOT NULL,
    riferimento_cartaceo TEXT
);

-- ============================================================
--  Indici per le query di tracciabilità
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_lotti_ingresso_scadenza ON lotti_ingresso(data_scadenza);
CREATE INDEX IF NOT EXISTS idx_lotti_interni_scadenza ON lotti_interni(data_scadenza);
CREATE INDEX IF NOT EXISTS idx_consumi_interno ON consumi(lotto_interno_id);
CREATE INDEX IF NOT EXISTS idx_consumi_origine ON consumi(origine, lotto_origine_id);

-- ============================================================
--  Impostazioni: i dati dell'ATTIVITÀ che produce (chi firma le etichette)
-- ============================================================
-- Chiavi note: 'produttore_ragione_sociale', 'produttore_indirizzo'. Il
-- produttore è UNO (la pasticceria), ma la tabella generica resta aperta
-- per ciò che verrà (copie di default, formato etichetta...).
CREATE TABLE IF NOT EXISTS impostazioni (
    chiave TEXT PRIMARY KEY,
    valore TEXT
);
