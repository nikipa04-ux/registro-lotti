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
│   │   ├── arrivi.py      #   lotti in ingresso, allegati
│   │   ├── produzioni.py  #   lotti interni, consumi, etichetta calcolata
│   │   ├── magazzino.py   #   giacenze, scadenze
│   │   └── dashboard.py   #   quadro riassuntivo del giorno
│   ├── logic/             # LOGICA DI BUSINESS (funzioni pure, testabili)
│   │   ├── um.py          #   conversioni: solo g↔kg e ml↔lt, mai implicite
│   │   ├── fefo.py        #   proposta lotti che scadono prima
│   │   ├── lotti.py       #   generazione codice SIGLA-AAAAMMGG-NN
│   │   ├── etichetta.py   #   lista ingredienti calcolata dai consumi
│   │   ├── foodcost.py    #   costi: storico prezzi dagli arrivi
│   │   └── dashboard.py   #   scadenze imminenti e contatori
│   └── ui/                # interfaccia reale (dashboard) servita dal backend
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

## Dati di prova (seed)

Per vedere il gestionale vivo da subito, senza inserire nulla a mano:

```cmd
.venv\Scripts\activate
python -m app.seed
```

Carica lo scenario del pasticciere: 3 fornitori, 6 ingredienti (con allergeni,
conservazione e denominazioni legali), le ricette di crema e bignè, 6 arrivi e
2 produzioni collegate dai consumi. Le date sono calcolate rispetto a oggi,
quindi la dashboard mostra subito scadenze vere (panna critica, latte in
scadenza, ecc.). Per ricaricare la demo da zero: `python -m app.seed --reset`.

## Interfaccia

La dashboard è la prima schermata reale: stesso design del prototipo
(`docs/prototipo.html`), ma i dati arrivano da `/api/dashboard` invece che da
array finti. Le altre sezioni (arrivi, produzioni, magazzino, anagrafiche)
sono segnate "presto" nella navigazione e arrivano nelle prossime iterazioni.

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
