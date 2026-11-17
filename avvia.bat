@echo off
REM ============================================================
REM  Registro Lotti - avvio rapido (fase 1: sviluppo locale)
REM  Controlla Python, crea l'ambiente, installa le librerie,
REM  VERIFICA che il server parta, poi apre il browser.
REM  In caso di errore la finestra resta APERTA col messaggio.
REM ============================================================
cd /d "%~dp0"
title Registro Lotti

echo.
echo === Registro Lotti - avvio ===
echo.

REM --- 1. Python presente? (l'alias dello Store risponde con errore 9009)
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERRORE] Python non trovato nel PATH.
  echo.
  echo Installa Python 3.10+ da https://www.python.org/downloads/
  echo e durante l'installazione SPUNTA "Add python.exe to PATH".
  echo Poi rilancia questo file.
  echo.
  pause
  exit /b 1
)
echo Python: OK
python --version

REM --- 2. Ambiente virtuale (creato una volta sola)
if not exist ".venv\Scripts\python.exe" (
  echo Creo l'ambiente virtuale .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERRORE] ambiente virtuale non creato. Vedi messaggio qui sopra.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"

REM --- 3. Librerie installate? (installa solo se mancano)
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo Installo le librerie la prima volta, attendi ...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERRORE] installazione librerie fallita. Controlla la connessione.
    pause
    exit /b 1
  )
)

REM --- 4. Verifica che l'app si avvii PRIMA di aprire il browser
echo Verifico che il server parta ...
python -c "import app.main" >nul 2>&1
if errorlevel 1 (
  echo [ERRORE] l'app non si avvia. Dettagli:
  echo.
  python -c "import app.main"
  echo.
  echo Se l'errore cita la versione di Python: servono 3.10 o superiore.
  pause
  exit /b 1
)
echo Server: OK

REM --- 5. Browser dopo 3 secondi (il tempo di mettere in moto il server)
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"

echo.
echo ================================================================
echo  Registro Lotti in funzione: http://127.0.0.1:8000
echo  Documentazione API: http://127.0.0.1:8000/docs
echo  Per fermare il server: chiudi questa finestra o premi Ctrl+C
echo ================================================================
echo.

REM NOTA: python -m uvicorn, MAI "uvicorn" da solo: pip crea in
REM .venv\Scripts degli eseguibili NON firmati che Smart App Control /
REM Device Guard blocca (esperienza del 15/11). Con python -m
REM lanciamo tutto tramite python.exe (firmato) e il blocco non scatta.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo [Il server si e fermato]
pause
