# Versione portabile senza exe (fase 2)

Pacchetto cartella pronto da copiare su qualunque PC: nessuna
installazione, nessun eseguibile nuovo, **nessun conflitto col Controllo
app intelligenti** (che resta attivo).

**Stesso codice della fase 1** (`app/`, zero riscritture): la cartella
`portatile/` aggiunge solo il wrapper `registro_lotti.py` (avvia il server
in locale e apre la finestra) e il bat che prepara il pacchetto.

## Come si costruisce (una volta, sul PC di sviluppo)

1. Serve **Python 3.13** (`py install 3.13` dal cmd, launcher `py` attivo).
   Il 3.14 dello sviluppo non viene toccato: `avvia.bat` continua a usare il suo.
   Perché proprio 3.13: pythonnet, il motore finestre di pywebview, era senza
   pacchetti pronti per il 3.14 alla data del packaging.
2. Doppio clic su `build_portatile_senza_exe.bat`:
   - riusa/crea la venv di build `.venv-build` con Python 3.13,
   - scarica UNA volta Python embeddabile da python.org (cache `downloads\`),
   - crea la cartella `RegistroLotti\` completa: Python incorporato,
     librerie (fastapi, uvicorn, pywebview, pythonnet), codice `app\`,
     wrapper, bat di avvio, `data\` e LEGGIMI.
3. Fine: il pacchetto è `portabile\RegistroLotti`.

## Come si usa (su qualunque PC Windows 10/11)

- Copia la cartella `RegistroLotti\` intera (chiavetta o zip) e aprila.
- Doppio clic su `RegistroLotti.bat`: si apre la finestra dell'app,
  senza finestra nera di console. Gli eventuali errori appaiono in un
  messaggio a finestra.
- Il database nasce da solo in `RegistroLotti\data\registro-lotti.db`:
  i dati viaggiano con la cartella, il backup è copiare `data\`.
- Per portare i dati della fase 1: copia il `registro-lotti.db` del
  progetto dentro `RegistroLotti\data\`.
- Aggiornare l'app su un PC: ricopia la cartella `app\` nel pacchetto
  (la riesegui del bat rifà tutto il pacchetto, ma conserva i dati:
  `RegistroLotti\data\` viene messa da parte e rimessa a posto).
  Se la build si interrompe, riprendi la cartella `_data_backup\` a mano.

Requisito sul PC di destinazione: Windows 10/11 con Edge (per WebView2,
già presente di norma). Serve solo quello: né Python, né internet.

## Perché il Controllo app intelligenti non disturba

Il SAC blocca gli **eseguibili** non firmati da radici attendibili; non ha
esclusioni configurabili. In questo pacchetto l'unico eseguibile è
`python.exe`/`pythonw.exe` **firmato da python.org**: firma valida e
reputazione consolidata. Tutto il resto (`.py`, `.sql`, html/css/js e i
file delle librerie) è dati, non programmi. Sul PC di destinazione non
gira mai pip né viene eseguito niente di non firmato.

## Diagnostica

- Server sempre e solo su `127.0.0.1` (porta 8765 o la prima libera dopo):
  nessuna esposizione verso la rete. Non interferisce con `avvia.bat`
  dello sviluppo (porta 8000).
- In sviluppo, dal repo: `py portatile\registro_lotti.py` apre la finestra
  sulla copia del progetto; con `--browser` apre invece il browser di
  sistema (utile se WebView2 manca).
