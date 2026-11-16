@echo off
REM ============================================================
REM  Registro Lotti - avvio rapido (fase 1: sviluppo locale)
REM  Doppio clic: prima esecuzione installa le librerie,
REM  poi avvia il server e apre il browser.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv" (
  echo Prima esecuzione: creo l'ambiente virtuale e installo le librerie...
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  pip install -r requirements.txt
) else (
  call ".venv\Scripts\activate.bat"
)

echo.
echo Server su http://127.0.0.1:8000  (Ctrl+C nella finestra per fermare)
start "" http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
