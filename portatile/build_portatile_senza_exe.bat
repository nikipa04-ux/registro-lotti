@echo off
REM ============================================================
REM  Registro Lotti - pacchetto PORTATILE SENZA EXE
REM  Prepara la cartella portabile\RegistroLotti pronta da
REM  copiare su qualunque PC: Python EMBEDDED firmato python.org
REM  + librerie + codice dell'app + bat di avvio.
REM  NESSUN eseguibile nuovo: il Controllo app intelligenti
REM  resta attivo perche' python.exe e' firmato e i .py sono
REM  dati, non programmi.
REM ============================================================
REM  Blocchi if: vietate le parentesi tonde, anche nei REM.
REM  Tutto il flusso usato qui e' a etichette goto.
REM ============================================================
cd /d "%~dp0"
title Registro Lotti - pacchetto senza exe
set RADICE=%~dp0..
set PYV=3.13.1

echo.
echo === Registro Lotti - pacchetto portabile senza exe ===
echo.

REM --- 1. venv di build con Python 3.13, come per l'exe
py -3.13 --version >nul 2>&1
if errorlevel 1 goto NO313
set PY=.venv-build\Scripts\python.exe
if not exist "%PY%" goto CREA_VENV
"%PY%" -V | find " 3.13." >nul
if errorlevel 1 goto CREA_VENV
goto VENV_OK

:CREA_VENV
echo Creo/ricreo la venv di build con Python 3.13 ...
if exist ".venv-build" rmdir /s /q .venv-build
py -3.13 -m venv .venv-build
if not exist "%PY%" goto VENV_FALLITA

:VENV_OK
echo Ambiente di build: OK
"%PY%" -c "import fastapi, uvicorn, webview" >nul 2>&1
if errorlevel 1 goto INSTALLA_LIB
goto LIB_OK

:INSTALLA_LIB
echo Installo le librerie nella venv di build ...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto LIB_FALLITE
"%PY%" -m pip install -r requirements-app.txt
if errorlevel 1 goto LIB_FALLITE

:LIB_OK
echo Librerie venv di build: OK

REM --- 2. Python embeddable di python.org
if not exist "downloads" mkdir downloads
if exist "downloads\python-embed.zip" goto EMBED_OK
echo Scarico Python %PYV% embeddabile da python.org ...
curl -L -o "downloads\python-embed.zip" "https://www.python.org/ftp/python/%PYV%/python-%PYV%-embed-amd64.zip"
if not exist "downloads\python-embed.zip" goto DOWNLOAD_FALLITO

:EMBED_OK
echo Python embeddable: OK

REM --- 3. Cartella del pacchetto: sempre fresca, MA i dati si conservano
if exist "RegistroLotti\data" goto SALVA_DATI
goto RIMUOVI_PKG

:SALVA_DATI
echo Conservo i tuoi dati: RegistroLotti\data viene messa da parte.
if exist "_data_backup" goto BACKUP_BLOCCATO
move /Y "RegistroLotti\data" "_data_backup" >nul
if not exist "_data_backup" goto DATI_FALLITI

:RIMUOVI_PKG
if exist "RegistroLotti" rmdir /s /q RegistroLotti
mkdir RegistroLotti
tar -xf "downloads\python-embed.zip" -C RegistroLotti
if not exist "RegistroLotti\python.exe" goto EMBED_FALLITO

REM --- 4. Percorsi dell'embeddable: zip, cartella, site-packages
if exist "RegistroLotti\python313._pth" del "RegistroLotti\python313._pth"
echo python313.zip> "RegistroLotti\python313._pth"
echo .>> "RegistroLotti\python313._pth"
echo Lib\site-packages>> "RegistroLotti\python313._pth"
echo import site>> "RegistroLotti\python313._pth"

REM --- 5. Librerie DENTRO il pacchetto
echo Installo le librerie nel pacchetto ... qualche minuto
"%PY%" -m pip install --target "RegistroLotti\Lib\site-packages" -r requirements-app.txt
if errorlevel 1 goto LIB_FALLITE

REM --- 6. Codice dell'app: app/ + wrapper + cartella dati
robocopy "%RADICE%\app" "RegistroLotti\app" /E /XD __pycache__ /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto APP_FALLITA
mkdir "RegistroLotti\Lancio"
copy /Y registro_lotti.py "RegistroLotti\Lancio\registro_lotti.py" >nul
if errorlevel 1 goto APP_FALLITA
REM --- 6b. Cartella dati: ripristino quella salvata, altrimenti nuova
if exist "_data_backup" goto RIPRISTINA_DATI
mkdir "RegistroLotti\data"
goto DATI_PRONTI

:RIPRISTINA_DATI
echo Rimetto a posto i tuoi dati: RegistroLotti\data
move /Y "_data_backup" "RegistroLotti\data" >nul
if not exist "RegistroLotti\data" goto DATI_FALLITI

:DATI_PRONTI

REM --- 7. Bat di avvio del pacchetto
echo @echo off> "RegistroLotti\RegistroLotti.bat"
echo cd /d "%%~dp0">> "RegistroLotti\RegistroLotti.bat"
echo start "" "%%~dp0pythonw.exe" "%%~dp0Lancio\registro_lotti.py">> "RegistroLotti\RegistroLotti.bat"

REM --- 8. LEGGIMI del pacchetto
echo Registro Lotti - app portatile, nessuna installazione.> "RegistroLotti\LEGGIMI.txt"
echo Doppio clic su RegistroLotti.bat: si apre la finestra dell'app.>> "RegistroLotti\LEGGIMI.txt"
echo I dati vivono nella sottocartella data: per il backup o>> "RegistroLotti\LEGGIMI.txt"
echo per portare l'app altrove copia la cartella RegistroLotti intera.>> "RegistroLotti\LEGGIMI.txt"

echo.
echo ============================================================
echo  FATTO: il pacchetto e' la cartella  portabile\RegistroLotti
echo.
echo  Provala ora: doppio clic su RegistroLotti\RegistroLotti.bat
echo  Per distribuirla: copia la cartella RegistroLotti intera
echo  (chiavetta, altro PC). Serve solo Windows 10/11 con Edge.
echo ============================================================
echo.
pause
exit /b 0

:NO313
echo [ERRORE] Python 3.13 non trovato: apri cmd e lancia: py install 3.13
echo Installa anche il launcher py se manca: vedi README-PORTATILE.md
goto FINE_ERRORE

:VENV_FALLITA
echo [ERRORE] La venv di build non e' stata creata.
goto FINE_ERRORE

:LIB_FALLITE
echo [ERRORE] Installazione librerie fallita: controlla la connessione.
goto FINE_ERRORE

:DOWNLOAD_FALLITO
echo [ERRORE] Download di Python embeddable fallito: controlla la connessione.
goto FINE_ERRORE

:EMBED_FALLITO
echo [ERRORE] Estrazione di Python embeddable fallita: cancella downloads e riprova.
goto FINE_ERRORE

:APP_FALLITA
echo [ERRORE] Copia del codice dell'app fallita.
goto FINE_ERRORE

:BACKUP_BLOCCATO
echo [ERRORE] Esiste gia' _data_backup da un giro interrotto: dentro c'e' la tua cartella data.
echo Aprila e recupera i dati a mano, poi rilancia la build.
goto FINE_ERRORE

:DATI_FALLITI
echo [ERRORE] Spostamento dei dati fallito: fermo tutto per non perdere nulla.
goto FINE_ERRORE

:FINE_ERRORE
echo.
pause
exit /b 1
