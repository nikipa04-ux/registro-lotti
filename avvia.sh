#!/bin/bash
# ============================================================
#  Registro Lotti - avvio rapido (fase 1: sviluppo locale)
#  Controlla Python, crea l'ambiente, installa le librerie,
#  VERIFICA che il server parta, poi apre il browser.
#  In caso di errore il terminale resta APERTO col messaggio.
# ============================================================
cd "$(dirname "$0")" || exit 1

echo
echo "=== Registro Lotti - avvio ==="
echo

# --- 1. Python presente? (su Fedora l'eseguibile è python3)
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERRORE] Python3 non trovato nel PATH."
  echo
  echo "Installa Python 3.10+ con:  sudo dnf install python3 python3-pip"
  echo "Poi rilancia questo script."
  echo
  read -rp "Premi Invio per chiudere ..."
  exit 1
fi
echo "Python: OK"
python3 --version

# --- 2. Ambiente virtuale (creato una volta sola)
if [ ! -x ".venv/bin/python" ]; then
  echo "Creo l'ambiente virtuale .venv ..."
  python3 -m venv .venv || {
    echo "[ERRORE] ambiente virtuale non creato. Vedi messaggio qui sopra."
    read -rp "Premi Invio per chiudere ..."
    exit 1
  }
fi

# --- 3. Librerie installate? (installa solo se mancano)
if ! .venv/bin/python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "Installo le librerie la prima volta, attendi ..."
  .venv/bin/python -m pip install -r requirements.txt || {
    echo "[ERRORE] installazione librerie fallita. Controlla la connessione."
    read -rp "Premi Invio per chiudere ..."
    exit 1
  }
fi

# --- 4. Verifica che l'app si avvii PRIMA di aprire il browser
echo "Verifico che il server parta ..."
if ! .venv/bin/python -c "import app.main" >/dev/null 2>&1; then
  echo "[ERRORE] l'app non si avvia. Dettagli:"
  echo
  .venv/bin/python -c "import app.main"
  echo
  echo "Se l'errore cita la versione di Python: servono 3.10 o superiore."
  read -rp "Premi Invio per chiudere ..."
  exit 1
fi
echo "Server: OK"

# --- 5. Browser dopo 3 secondi (il tempo di mettere in moto il server)
(
  sleep 3
  xdg-open http://127.0.0.1:8000 >/dev/null 2>&1
) &

echo
echo "================================================================"
echo " Registro Lotti in funzione: http://127.0.0.1:8000"
echo " Documentazione API:           http://127.0.0.1:8000/docs"
echo " Per fermare il server: premi Ctrl+C in questo terminale"
echo "================================================================"
echo

# NOTA: python -m uvicorn, come nel bat. Su Linux non serve per
# Smart App Control (question Windows), ma manteniamo lo stesso
# comando su entrambi gli OS: un solo schema mentale.
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo
echo "[Il server si è fermato]"
read -rp "Premi Invio per chiudere ..."