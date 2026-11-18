# Schema del database (v0.1)

Modello SQL completo per il gestionale lotti, derivato dall'esempio guida (uovo → crema pasticcera → bignè).

## Principi

- DBMS: **SQLite** (singolo file, backup = copia della cartella dati insieme agli allegati).
- Chiavi primarie: INTEGER autoincrement per semplicità, i codici lotto restano univoci via constraint.
- La tracciabilità è gestita da un'unica tabella di **consumo ricorsiva**: un lotto può consumare lotti in ingresso E lotti interni.
- Quantità: REAL per tollerare pesi/volumi; non si fa magazzino contabile nella v0.1, solo tracciabilità.

## Tabelle

```sql
-- Anagrafica fornitori
CREATE TABLE fornitori (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    note TEXT
);

-- Anagrafica prodotti (copre ingredienti acquistati E prodotti interni)
CREATE TABLE famiglie (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Allergeni: i 14 obbligatori da etichetta (Reg. UE 1169/2011) con descrizione/esempi
CREATE TABLE allergeni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    descrizione TEXT
);

-- Dichiarazione allergeni per INGREDIENTE (many-to-many).
-- I PRODOTTI DI LABORATORIO non si dichiarano: ereditano dalla ricetta
-- (unione ricorsiva sugli ingredienti, calcolata dall'app).
CREATE TABLE prodotti_allergeni (
    prodotto_id INTEGER NOT NULL REFERENCES prodotti(id),
    allergene_id INTEGER NOT NULL REFERENCES allergeni(id),
    PRIMARY KEY (prodotto_id, allergene_id)
);

CREATE TABLE prodotti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    -- gli ingredienti acquistati si riconoscono da famiglia NULL;
    -- i prodotti di laboratorio hanno la famiglia (es. 'Creme')
    famiglia_id INTEGER REFERENCES famiglie(id),  -- NULL = ingrediente acquistato
    conservazione TEXT,                -- luogo fisico: 'Frigo' | 'Freezer' | 'Magazzino' (solo ingredienti)
    denominazione_legale TEXT,         -- dicitura etichetta d'acquisto, per l'etichetta dei prodotti finiti
    unita_misura TEXT,            -- 'kg', 'lt', 'pz', 'uova'...
    marca TEXT,                   -- produttore/marca per ingredienti acquistati (tracciabilità; NULL per interni)
    denominazione TEXT,           -- denominazione legale per l'etichetta (es. 'uova fresche intere di gallina');
                                  -- OBBLIGATORIA per ingredienti acquistati (suggerimento: precompilata dal nome);
                                  -- NULL per i prodotti di laboratorio: la loro lista si calcola dai consumi
    sigla TEXT,                   -- per generare il codice lotto interno
    note TEXT
    -- sottofamiglia TEXT         -- rimandata: si aggiungerà come colonna opzionale
);

-- Lotti in ingresso (eventi di arrivo)
CREATE TABLE lotti_ingresso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prodotto_id INTEGER NOT NULL REFERENCES prodotti(id),
    fornitore_id INTEGER NOT NULL REFERENCES fornitori(id),
    marca TEXT,                          -- marca/produttore del LOTTO consegnato (default: da prodotti.marca)
    codice_lotto TEXT NOT NULL,          -- lotto esterno del fornitore
    data_arrivo TEXT NOT NULL,           -- ISO 8601: 'YYYY-MM-DD'
    data_scadenza TEXT NOT NULL,
    quantita REAL,
    quantita_residua REAL,              -- aggiunta magazzino: giacenza del lotto, scaricata dai consumi
    prezzo_unitario REAL,               -- costo d'acquisto per unità di misura
    iva REAL,                           -- aliquota % (4 / 10 / 22): totale e totale con IVA sono calcolati, non memorizzati
    UNIQUE (prodotto_id, codice_lotto, fornitore_id)
);

-- Lotti interni (eventi di produzione)
CREATE TABLE lotti_interni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prodotto_id INTEGER NOT NULL REFERENCES prodotti(id),
    famiglia_id INTEGER REFERENCES famiglie(id),  -- SNAPSHOT della famiglia di questa produzione
                                       -- (può differire dalla ricetta: produzione slave)
    qta_prodotta REAL,                  -- NECESSARIA per l'etichetta calcolata: attribuzione
                                       -- esatta degli ingredienti dei lotti interni consumati
                                       -- (NESSUNA tabella di snapshot etichetta: i consumi sono
                                       -- il verbale, denominazioni e allergeni si calcolano)
    codice_lotto TEXT NOT NULL UNIQUE,   -- auto-generato: es. CRP-20261112-01
    data_produzione TEXT NOT NULL,
    data_scadenza TEXT NOT NULL
);

-- Consumo: quale lotto è stato usato in quale produzione
-- 'origine' distingue un lotto in ingresso da un lotto interno (ricorsività)
CREATE TABLE consumi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lotto_interno_id INTEGER NOT NULL REFERENCES lotti_interni(id),
    origine TEXT NOT NULL CHECK (origine IN ('ingresso', 'interno')),
    lotto_origine_id INTEGER NOT NULL,    -- id in lotti_ingresso oppure lotti_interni
    quantita_usata REAL,
    UNIQUE (lotto_interno_id, origine, lotto_origine_id)
);

-- Allegati (DDT, certificati, foto) collegabili a lotti e produzioni
CREATE TABLE allegati (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_file TEXT NOT NULL,             -- nome visualizzato
    percorso_relativo TEXT NOT NULL,     -- dentro la cartella dati dell'app
    origine TEXT NOT NULL CHECK (origine IN ('ingresso', 'interno')),
    lotto_id INTEGER NOT NULL,           -- id in lotti_ingresso oppure lotti_interni
    caricato_il TEXT NOT NULL,
    riferimento_cartaceo TEXT            -- opzionale: es. "DDT cartaceo in faldone 2026"
);
```

## Ricette (aggiunta successiva, novembre 2026)

La ricetta è il ponte tra anagrafica prodotti e tracciabilità: selezionato il prodotto in produzione, l'app usa la ricetta per proporre automaticamente i lotti da consumare.

```sql
-- Testata ricetta: una per prodotto interno
CREATE TABLE ricette (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prodotto_id INTEGER NOT NULL UNIQUE REFERENCES prodotti(id),
    resa TEXT,                        -- es. '5 kg', '60 pz'
    note TEXT
);

-- Righe di ricetta: ingredienti con quantità per dose completa
-- 'ingrediente_id' può puntare a un ingrediente O a un semilavorato
-- (ricorsività: la crema pasticcera è ingrediente dei bignè)
CREATE TABLE ricette_righe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ricetta_id INTEGER NOT NULL REFERENCES ricette(id) ON DELETE CASCADE,
    ingrediente_id INTEGER NOT NULL REFERENCES prodotti(id),
    quantita REAL NOT NULL,
    UNIQUE (ricetta_id, ingrediente_id)
);
```

Nota v0.2 potenziale: aggiungere `shelf_life_giorni` alla ricetta/prodotto per calcolare la scadenza del lotto interno in automatico.

## Regola di prodotto: allegati opzionali

- Gli allegati digitali sono **opzionali**: non tutti i documenti (fatture, DDT) esistono in forma digitale.
- Un lotto senza allegati è perfettamente valido; l'allegato arricchisce il lotto, mai prerequisito.
- Per i documenti solo cartacei, il campo `riferimento_cartaceo` (testo libero) permette di lasciare traccia della collocazione fisica senza digitalizzazione.

## Impostazioni (aggiunta successiva, novembre 2026)

I dati dell'**attività che produce**: ragione sociale e indirizzo finiscono
sull'etichetta PDF (Reg. UE 1169/2011). Il produttore è UNO, ma la tabella
chiave/valore resta generica per le impostazioni future (logo, copie di
default del PDF...). Se una chiave non esiste, il suo valore è stringa vuota
e l'etichetta semplicemente non porta la riga.

```sql
CREATE TABLE IF NOT EXISTS impostazioni (
    chiave TEXT PRIMARY KEY,
    valore TEXT
);
-- chiavi note: 'produttore_ragione_sociale', 'produttore_indirizzo',
-- 'produttore_piva'
```

## Indici per le query di tracciabilità

```sql
CREATE INDEX idx_lotti_ingresso_scadenza ON lotti_ingresso(data_scadenza);
CREATE INDEX idx_lotti_interni_scadenza ON lotti_interni(data_scadenza);
CREATE INDEX idx_consumi_interno ON consumi(lotto_interno_id);
CREATE INDEX idx_consumi_origine ON consumi(origine, lotto_origine_id);
```

## Le due query chiave

**Avanti (richiamo prodotto)**: dato il lotto in ingresso `:id`, quali lotti interni lo hanno consumato, ricorsivamente?

```sql
WITH RECURSIVE coinvolti(lotto_interno_id) AS (
    SELECT lotto_interno_id FROM consumi
    WHERE origine = 'ingresso' AND lotto_origine_id = :id
    UNION
    SELECT c.lotto_interno_id FROM consumi c
    JOIN coinvolti ON c.origine = 'interno' AND c.lotto_origine_id = coinvolti.lotto_interno_id
)
SELECT li.codice_lotto, p.nome, li.data_produzione, li.data_scadenza
FROM coinvolti
JOIN lotti_interni li ON li.id = coinvolti.lotto_interno_id
JOIN prodotti p ON p.id = li.prodotto_id;
```

**Indietro (ispezione)**: dato il lotto interno `:id`, da quali lotti (ingresso e interni) deriva, ricorsivamente?

```sql
WITH RECURSIVE origini(origine, lotto_origine_id) AS (
    SELECT origine, lotto_origine_id FROM consumi
    WHERE lotto_interno_id = :id
    UNION
    SELECT c.origine, c.lotto_origine_id FROM consumi c
    JOIN origini ON c.lotto_interno_id = origini.lotto_origine_id
    WHERE origini.origine = 'interno'
)
SELECT o.origine, o.lotto_origine_id;
```

## Codice lotto interno (regola di generazione)

- Formato: `<SIGLA>-<AAAAMMGG>-<NN>` dove SIGLA deriva dal prodotto (es. CRP per crema pasticcera), NN è un progressivo giornaliero.
- Generato dal backend, l'utente non lo digita mai.

## Denominazioni ed etichetta ingredienti (decisione, 13 novembre 2026)

Per comporre l'elenco ingredienti delle etichette (Reg. UE 1169/2011):

- Ogni **ingrediente acquistato** ha una `denominazione` legale, **assegnata manualmente all'inserimento in anagrafica** e obbligatoria (la UI la suggerisce precompilando dal nome).
- I **prodotti di laboratorio** non dichiarano denominazioni proprie: la loro lista ingredienti si **somma per ricorsione lungo i consumi** (stesso meccanismo degli allergeni).
- Nessuno snapshot dedicato: la lista è **sempre calcolata** dai consumi del lotto (opzione A scelta da Nicolas il 13/11/2026). Le quantità dei consumi sono già lo snapshot sufficiente; il resto è calcolato, il più automatico possibile.
- Ordine di elencazione: decrescente per quantità, rispettando la regola delle u.m. (nessuna conversione implicita fra tipi diversi).
- Denominazioni e allergeni viaggiano insieme: la composizione etichetta è un'unica funzione che restituisce la stringa con gli allergeni in evidenza.
- Collegata alla voce di backlog "stampa etichette QR".

## Note v0.1

- No gestione utente multiutente né login (uso locale monoutente).
- No magazzino contabile: le quantità servono solo come informazione, non c'è giacenza calcolata.
- Le scadenze dei lotti interni sono inserite/calcolate a mano dall'utente in v0.1; un futuro "schede prodotto" con shelf-life standard automática è un miglioramento possibile.
