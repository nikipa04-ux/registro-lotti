# Registro Lotti

Gestionale per piccole aziende della ristorazione: registro dei lotti in arrivo, scadenze, tracciabilità avanti e indietro (Reg. CE 852/2004), ricette e produzioni, magazzino, allergeni (Reg. UE 1169/2011) ed etichette ingredienti calcolate dal verbale di produzione.

App web locale: backend Python (FastAPI) + SQLite, interfaccia nel browser. Nessun cloud, nessun server: i dati restano nel negozio.

## Struttura del progetto

```
registro-lotti/
├── avvia.bat              # doppio clic: crea l'ambiente, installa, avvia
├── requirements.txt       # librerie Python del progetto
├── app/
│   ├── main.py            # server FastAPI: serve l'UI e le API
│   ├── db.py              # connessione SQLite + inizializzazione schema
│   ├── schema.sql         # schema del database v0.1
│   ├── seed.py            # dati di prova (scenario del pasticciere)
│   ├── api/               # ENDPOINT (ricevono richieste, chiamano la logica)
│   │   ├── anagrafiche.py #   fornitori, prodotti, famiglie, allergeni
│   │   ├── arrivi.py      #   lotti in ingresso: lista, dettaglio, registrazione
│   │   ├── produzioni.py  #   lotti interni, consumi, etichetta calcolata
│   │   ├── ricette.py     #   il master: crea e corregge le ricette
│   │   ├── magazzino.py   #   giacenze, scadenze
│   │   └── dashboard.py   #   quadro riassuntivo del giorno
│   ├── logic/             # LOGICA DI BUSINESS (funzioni pure, testabili)
│   │   ├── um.py          #   conversioni: solo g↔kg e ml↔lt, mai implicite
│   │   ├── fefo.py        #   proposta lotti che scadono prima
│   │   ├── lotti.py       #   generazione codice SIGLA-AAAAMMGG-NN
│   │   ├── arrivi.py      #   regole di registrazione di un arrivo
│   │   ├── produzioni.py  #   proposta FEFO e verbale della produzione
│   │   ├── ricette.py     #   il master: upsert ricetta, famiglia, righe
│   │   ├── etichetta.py   #   lista ingredienti calcolata dai consumi
│   │   ├── etichetta_pdf.py  # il PDF a griglia del foglio A4 (solo stdlib)
│   │   ├── foodcost.py    #   costi: storico prezzi dagli arrivi
│   │   └── dashboard.py   #   scadenze imminenti e contatori
│   └── ui/                # interfaccia reale (dashboard + arrivi + produzioni)
├── data/                  # qui vive il DB (fuori da git)
├── docs/
│   ├── prototipo.html     # prototipo cliccabile della UI (riferimento)
│   ├── schema-db.md       # documentazione dello schema
│   └── mappa-progetto.md  # mappa del progetto: ER, flusso, regole
└── tests/                 # test della logica (pytest)
```

## Requisiti

- Python 3.10 o superiore (`python --version` da cmd per verificare)
- Git + GitHub Desktop

## Avvio (Windows)

Doppio clic su **`avvia.bat`**. Alla prima esecuzione crea l'ambiente virtuale, installa le librerie e avvia il server su http://127.0.0.1:8000 aprendo il browser.

Avvio manuale equivalente:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Nota importante: usare sempre `python -m uvicorn` e `python -m pytest`, mai i
comandi diretti (`uvicorn`, `pytest`). Pip crea in `.venv\Scripts` degli
eseguibili NON firmati digitalmente che Smart App Control / Device Guard può
bloccare ("è stato bloccato dai criteri di Device Guard"). Chiamando i moduli
tramite python.exe (firmato) il problema non si pone mai.

## Test

```cmd
.venv\Scripts\activate
python -m pytest
```

Comprende due guardie statiche: nessun modulo API può oscurare un
import (`test_api_static`) e l'interfaccia non può avere funzioni JS
definite ma mai usate né ID HTML dimenticati (`test_ui_static`).

## Dati di prova (seed)

Per vedere il gestionale vivo da subito, senza inserire nulla a mano:

```cmd
.venv\Scripts\activate
python -m app.seed
```

Carica lo scenario del pasticciere: 3 fornitori, 6 ingredienti (con allergeni,
e **tutti i 14 allergeni di legge** in tabella: il server li assicura a ogni
avvio anche sui database esistenti, `app/logic/anagrafiche.py` →
`ALLERGENI_DI_LEGGE` / `garantisci_allergeni_di_legge`, Reg. UE 1169/2011),
conservazione e denominazioni legali), le ricette di crema e bignè, 6 arrivi e
2 produzioni collegate dai consumi. Le date sono calcolate rispetto a oggi,
quindi la dashboard mostra subito scadenze vere (panna critica, latte in
scadenza, ecc.). Per ricaricare la demo da zero: `python -m app.seed --reset`.

## Interfaccia

Comportamenti comuni a tutte le sezioni:

- le finestre modali si chiudono con **Escape**, col bottone Annulla o
  clicando fuori (sullo sfondo scuro);
- le schede di dettaglio (anagrafiche, arrivi, produzioni) non si
  allungano all'infinito: il contenuto scrolla DENTRO la card
  (intestazione fissa, bottoni sempre visibili in fondo);
- le liste lunghe scrollano dentro la propria card.

### Dashboard

La prima schermata reale: stesso design del prototipo
(`docs/prototipo.html`), ma i dati arrivano da `/api/dashboard` invece che da
array finti. Stat cards, scadenze entro 7 giorni con badge colore, pulsante
rapido per il nuovo arrivo.

### Arrivi

La sezione con cui si registra tutto ciò che entra:

- **Filtri a cascata** come nel prototipo: una casella di ricerca (prodotto,
  marca, lotto o fornitore) + select fornitore + select ingrediente +
  finestra di scadenza (≤3 giorni / ≤7 giorni / scaduti) + contatore
  "N di M arrivi"
- **Tabella** come la demo: prodotto, marca in badge (del lotto, con default
  dall'anagrafica), lotto, fornitore, arrivo, scadenza colorata, quantità,
  prezzo unitario, totale e totale+IVA (CALCOLATI dal server)
- **Dettaglio lotto**: clic su una riga → dati del lotto, costi e
  tracciabilità avanti ("usato in": quali produzioni l'hanno consumato),
  più bottone "🗑 Elimina" con conferma; il contenuto scrolla DENTRO la
  card (intestazione fissa, azioni sempre visibili)
- **Nuovo arrivo** (modale): ingrediente e fornitore sono combobox con
  typeahead (tendina raggruppata per conservazione 🧊); se il nome cercato
  non esiste compare "➕ Crea..." che apre la creazione rapida: l'ingrediente
  nasce lì (conservazione, u.m., sigla, marca, denominazione legale e
  allergeni a chip, già selezionabili) e resta
  selezionato. Date, quantità, prezzo e IVA facoltativi.

Le regole di registrazione vivono nel server (`app/logic/arrivi.py`):
residua = quantità in partenza, un prodotto di laboratorio non può "arrivare"
(nasce da una produzione), la scadenza non può precedere l'arrivo, lotto
duplicato per lo stesso fornitore respinto. Il form mostra i messaggi
d'errore del server così come sono.

**Eliminazione PROTETTA** (`DELETE /api/arrivi/{arrivo_id}`): un lotto già
consumato in un verbale di produzione non si elimina (la tracciabilità non
si riscrive: il messaggio dice di annullare invece quella produzione);
senza consumi l'arrivo si elimina dal bottone 🗑 nel dettaglio.

**Regola dei menu a cascata**: in OGNI combobox il bottone "➕ Crea..." è
sempre l'ULTIMA riga della tendina; la creazione rapida non fa mai cambiare
schermata e il nome cercato arriva già precompilato (modificabile).

Le altre sezioni (scadenze, magazzino) sono segnate "presto" nella
navigazione e arrivano nei prossimi capitoli.

### Produzioni

La sezione in cui nascono i lotti interni (semilavorati e dolci finiti).
La produzione è SLAVE della ricetta MASTER: la proposta parte dalle righe
della ricetta, l'operatore al massimo corregge.

- **Ricerca** per prodotto o lotto interno + contatore; tabella demo:
  prodotto + famiglia in badge, lotto mono, data produzione, scadenza
  colorata, "N lotti usati"
- **Dettaglio**: clic su una riga → dati del lotto, tracciabilità INDIETRO
  ("deriva da": i lotti consumati con le quantità) e AVANTI ("usato in"),
  etichetta ingredienti CALCOLATA dal verbale (denominazioni in ordine di
  peso, senza quantità) + "Contiene (allergeni):" dichiarazione degli allergeni
  + bottone "🏷 Etichetta PDF": il foglio A4 con la GRIGLIA di etichette
  pronte da stampare e tagliare (2 colonne x 4 righe = 8 per foglio, oltre
  si aggiunge la pagina; parametro `?copie=N`, default 8). Il PDF nasce
  dalla SOLA libreria standard Python: nessuna dipendenza nuova, font
  Helvetica/Courier di base con accenti italiani (à è ì ò ù é). Ogni
  etichetta accompagna il prodotto: nome, lotto interno, prodotto il /
  scade il, ingredienti calcolati, allergeni in rosso se presenti.
  + bottone "🗑 Elimina" (annulla il verbale e ripristina le giacenze);
  il contenuto scrolla DENTRO la card (intestazione fissa, azioni sempre
  visibili)
- **Nuova produzione** (modale a passi 1-2-3):
  1. prodotto da produrre (solo prodotti di laboratorio CON ricetta) →
     carica la proposta. Il combobox segue la regola del ➕: si può CREARE
     il prodotto al volo (u.m. + sigla) senza chiudere il form; se poi manca
     la ricetta, il warning offre "➕ Crea la ricetta di X ora": la modale
     ricetta si apre SOPRA il form produzione e al salvataggio si torna
     alla proposta FEFO, già pronta da salvare
  2. la proposta FEFO: una riga per ingrediente di ricetta con i chip dei
     lotti proposti (stesso ordine FEFO del server, quantità modificabile,
     riga escludibile ✕/↩), righe aggiungibili fuori ricetta (ingredienti
     acquistati e prodotti di laboratorio), alert rosso se manca merce;
     il bottone **⚖ Assegna lotti** per riga apre un pannello dove l'operatore
     decide a mano quanto prendere da ogni lotto (somma = quantità della
     riga, giacenze rispettate): la realtà del laboratorio non è mai FEFO
     perfetta. I chip scelti a mano sono marcati "a mano", e "↩ Riallinea
     a FEFO" torna alla proposta automatica. Se il lotto realmente usato
     non è ancora registrato, il ➕ in fondo al pannello lo crea al volo:
     nasce un VERO arrivo (fornitore, quantità, scadenza; arrivo di oggi,
     marca e prezzi si completano in Arrivi), entra nella riga e la FEFO
     copre il resto: la tracciabilità resta intatta, il verbale scarica
     un lotto che esiste davvero
  3. date e quantità prodotta (default = resa della ricetta) → salva

Al salvataggio il server RIVALIDA tutto (`app/logic/produzioni.py`):
giacenze sufficienti, consumi non vuoti (il verbale), niente lotto ripetuto,
scadenza non prima della produzione, scarico della `quantita_residua` dei
lotti in ingresso (le giacenze non si scrivono mai a mano), famiglia
SNAPSHOT dalla ricetta, codice `SIGLA-AAAAMMGG-NN`.

**Nessun tag "semilavorato"**: è una famiglia a etichettare la riga. Ogni
ingrediente di ricetta mostra il badge della sua FAMIGLIA (quella della
sua ricetta, dove la famiglia nasce per regola di design); le famiglie
sono libere: l'utente ne crea quante vuole (`POST /api/anagrafiche/famiglie`)
e il badge cambia di conseguenza.

**Eliminazione PROTETTA** (`DELETE /api/produzioni/{lotto_id}`): un lotto
interno già consumato da altre produzioni non si elimina; se nessuno lo
usa, il bottone 🗑 nel dettaglio annulla il verbale e RIPRISTINA le
giacenze dei lotti in ingresso consumati (le giacenze si scrivono solo in
registrazione, quindi si ripristinano solo qui).

v0.1: i lotti interni consumati (prodotti di laboratorio) non tracciano
la residua: la loro disponibilità è la quantità prodotta. La scelta
manuale dei lotti ("⚖ Assegna lotti", ex backlog) c'è: il server
rivalida comunque giacenze e quantità al salvataggio.

### Ricette

Il MASTER delle produzioni, anticipato rispetto alla tabella di marcia per
colmare il buco "prodotto senza ricetta": senza ricetta non si produce, e
la ricetta ora si crea e si corregge dall'interfaccia.

- **Lista**: ricerca per prodotto + contatore (prodotto + famiglia in
  badge, resa, numero ingredienti, presenza del procedimento), riga
  cliccabile → dettaglio con righe complete (con badge famiglia
  dell'ingrediente), resa, sigla del lotto e procedimento
- **Nuova ricetta** (modale): prodotto = combobox typeahead su tutta
  l'anagrafica esistente in quel momento (nessun suggerimento automatico
  e nessuna lista speciale: se non c'è, lo si crea con "➕ Crea", nome +
  sigla; se quello scelto ha già una ricetta la modale si apre in
  modifica); famiglia = combobox con tendina
  delle esistenti e creazione rapida "➕ Crea" (la famiglia nasce qui:
  l'utente ne crea quante ne vuole e la ritrova subito nella card
  Anagrafiche → Famiglie); resa divisa in due campi, quantità (numero) + unità
  di misura (es. "60" + "pz"; in banca dati resta il testo combinato
  "60 pz", pronto per il futuro calcolatore dinamico), procedimento
  facoltativo, righe ingrediente+quantità (ingredienti acquistati e
  prodotti di laboratorio, come le aggiunte delle produzioni)
- **Modifica**: stessa modale prefilled; le righe RIMPIAZZANO le vecchie
  (la ricetta è il master), le produzioni passate restano con il loro
  snapshot
- **Eliminazione PROTETTA**: rifiutata se il prodotto ha produzioni
  registrate (`DELETE /api/ricette/{prodotto_id}`); senza produzioni la
  ricetta si elimina e il prodotto perde la famiglia

Regole nel server (`app/logic/ricette.py`): righe non vuote con quantità
maggiori di zero, niente ingrediente ripetuto, ingrediente inesistente
respinto, prodotto con lotti in arrivo respinto ("è un ingrediente
acquistato"), famiglia obbligatoria (id esistente o nome nuovo, riusata
se esiste già senza badare a maiuscole), e SYNC: `prodotti.famiglia_id`
rispecchia la famiglia della ricetta così combo e filtri la vedono subito.
Se un prodotto resta senza ricetta, il messaggio della produzione dice di
crearla qui.

### Anagrafiche

La casa dei dati che nascono una volta sola (regola di design: i dati si
chiedono dove nascono, non dove si usano): conservazione e denominazione
legale con l'ingrediente, contatti con il fornitore, famiglia con la
ricetta (qui NON si tocca, al massimo la si apre).

- **Quattro card impilate**, ognuna con contatore, ricerca dedicata e
  lista scrollabile internamente:
  - **🛒 Ingredienti**: nome, marca abituale, conservazione, allergeni
    (⚠ max 2 + "+n"), u.m., sigla, n. arrivi; la ricerca copre nome e
    marca
  - **🥣 Prodotti**: SOLO prodotti con ricetta (gerarchia stretta: il
    prodotto esiste attraverso la sua ricetta, che è il master). Bottone
    **➕ Nuovo**: la modale crea l'anagrafica (nome, sigla) e apre
    SUBITO la ricetta; salvando, il prodotto compare in card. Famiglia in
    badge, allergeni EREDITATI dalla ricetta (calcolati, mai scritti a
    mano), sigla, n. produzioni; filtro per famiglia (badge
    cliccabile, rimovibile con ✕)
  - **🚚 Fornitori**: nome + P.IVA, n. arrivi
  - **🏷 Famiglie**: creazione inline, **rinomina inline ✏️ che si
    propaga ovunque** (tutto JOINa per id), conteggio prodotti cliccabile
    (filtra la card Prodotti), eliminazione solo se non usata
- **Scheda di dettaglio** (clic su una riga): sui monitor larghi
  (≥ 1400px) si apre come **pannello laterale ancorato accanto alle
  card**, sul lato destro dello schermo, sempre visibile mentre si
  scorrono le liste; su schermi
  stretti si apre sotto le card. In entrambi i casi il contenuto scrolla
  DENTRO la scheda (max-height, intestazione fissa) e le azioni
  Salva/Elimina restano sempre visibili in fondo:
  - *ingrediente*: nome, denominazione legale* (per l'etichetta dei
    prodotti finiti), marca abituale (default degli arrivi),
    conservazione*, i 14 allergeni come chips on/off (Reg. UE 1169/2011),
    u.m., sigla, note + arrivi recenti cliccabili (saltano al dettaglio
    del lotto, sezione Arrivi)
  - *prodotto di laboratorio*: nome, sigla, note; famiglia e
    allergeni READ-ONLY ereditati dalla ricetta ("se cambia la ricetta,
    cambiano qui") + bottoni **✏️ Modifica la ricetta / ➕ Crea la
    ricetta** (la modale ricetta si apre sopra la scheda e al salvataggio
    si torna qui, aggiornata) + produzioni recenti cliccabili
  - *fornitore*: ragione sociale, P.IVA, telefono, email, note + arrivi
    recenti
- **+ Nuovo** per ingrediente, fornitore e prodotto di laboratorio
  (modale; per le famiglie riga inline). La denominazione legale è
  suggerita già precompilata dal nome. Il prodotto di laboratorio nasce
  con la sua ricetta: la modale crea l'anagrafica e apre subito il form
  ricetta; se si annulla, il prodotto resta un "candidato" visibile
  solo dalla sezione Ricette finché non avrà la ricetta.
- **Eliminazioni PROTETTE** (`app/logic/anagrafiche.py`): ingrediente con
  arrivi rifiutato, prodotto con arrivi/produzioni/ricetta rifiutato,
  fornitore con arrivi rifiutato. La tracciabilità non si riscrive.
- Endpoint: GET `/api/anagrafiche/ingredienti`, `/prodotti-lab`,
  `/prodotti/{id}`, `/fornitori/{id}`, PUT prodotti/fornitori/famiglie
  (rinomina), DELETE prodotti/fornitori, POST `/ingredienti` (dal modulo,
  con denominazione obbligatoria).

## Pubblicazione su GitHub (GitHub Desktop)

1. Estrai questa cartella in `C:\Users\<utente>\Documents\GitHub\registro-lotti`
2. GitHub Desktop → **File → Add local repository** → scegli la cartella
3. Ti dirà che non è un repository Git: conferma con **Create repository**
4. Premi **Publish repository**: nome `registro-lotti`, account GitHub, lascia spuntato **Keep this code private**

## Flusso di lavoro Git

Una branch per feature, commit liberi sulla branch, squash prima del merge su `main`:

1. **New Branch** in GitHub Desktop prima di iniziare una feature (es. `feature/arrivi`)
2. Lavora e fai commit liberamente sulla branch
3. Quando la feature è finita: squash dei commit in uno solo e merge su `main`
4. Push su GitHub dopo il merge

Una branch non è una cartella separata: è un'etichetta che punta a uno stato della storia. Il codice non si duplica.

## Regole di progetto (ereditate dal prototipo)

1. **I dati si chiedono dove nascono**: conservazione → anagrafica ingrediente; marca → arrivo; famiglia → ricetta.
2. **Ricetta master / produzione slave**: la produzione snapshotta ciò che è successo davvero, non riscrive la ricetta.
3. **Eliminazioni protette**: si cancella solo ciò che nessuno referenzia.
4. **Tutto si calcola dalle registrazioni**: giacenze, food cost, allergeni, etichetta ingredienti. I consumi sono il verbale.
5. **Nessuna conversione implicita** fra unità di misura di tipi diversi: g↔kg e ml↔lt sì, teglie ≠ kg.

## Roadmap

- v0.1: anagrafiche, arrivi, produzioni con tracciabilità ricorsiva, magazzino, scadenze, etichetta calcolata
- v0.2: shelf-life automatiche, dosi riscalate, "può contenere tracce", stampa etichette QR, export CSV
