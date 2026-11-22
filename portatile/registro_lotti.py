"""Registro Lotti - avvio versione portabile (fase 2: exe con finestra nativa).

Stesso identico codice della fase 1 (app/): NESSUNA riscrittura.
Questo wrapper fa solo tre cose:

  1. Decide dove vive il database: ACCANTO all'exe, in data/, cosi' i dati
     viaggiano col programma e sopravvivono agli aggiornamenti dell'exe
     (nel .exe onefile il codice viene estratto in una cartella TEMPORANEA
     che Windows cancella: il DB non deve MAI finire li' dentro).
  2. Avvia il server FastAPI/uvicorn su 127.0.0.1, in un thread in
     background (solo locale, nessuna esposizione verso l'esterno).
  3. Apre la finestra nativa con pywebview (Edge WebView2 su Windows).
     Opzioni: --browser apre invece il browser di sistema (diagnostica nel
     caso WebView2 mancasse); stesso comportamento anche se pywebview non
     fosse importabile.

Chiudendo la finestra l'app si spegne. Il DB resta in <cartella exe>\\data.
"""

import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

PORTA_BASE = 8765  # dedicata all'exe: non collide con avvia.bat (porta 8000)


# --------------------------------------------------------------------------
# 1. Dove vive l'installazione (e il DB)
# --------------------------------------------------------------------------

def radice():
    """Cartella dell'installazione: quella dell'exe se congelato,
    la root del repo se lanciato in sviluppo (py portatile/registro_lotti.py)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def prepara_path():
    """Rende importabile il pacchetto app/ in entrambe le modalità."""
    base = radice()
    if getattr(sys, "frozen", False):
        # PyInstaller onefile: il codice di app/ vive nell'archivio estratto
        sys.path.insert(0, getattr(sys, "_MEIPASS", str(base)))
    else:
        sys.path.insert(0, str(base))
    return base


def percorso_db(base):
    return base / "data" / "registro-lotti.db"


# --------------------------------------------------------------------------
# 2. Server in background
# --------------------------------------------------------------------------

def sceglie_porta():
    """Prima porta libera da PORTA_BASE in su (max 10 tentativi).

    Evita il rifiuto di connessione se un'altra copia e' gia' aperta.
    """
    for porta in range(PORTA_BASE, PORTA_BASE + 11):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", porta))
                return porta
            except OSError:
                continue
    raise RuntimeError("Nessuna porta libera da %d" % PORTA_BASE)


def avvia_con(app, porta):
    """Avvia uvicorn in un thread daemon e torna l'oggetto server."""
    import uvicorn

    # log_config=None: negli exe SENZA console sys.stdout e' None e il
    # formatter di default di uvicorn chiama sys.stdout.isatty() crashando
    # ("Unable to configure formatter 'default'", pyinstaller#7339).
    # Il logging serve in sviluppo, mai nella finestra.
    config = uvicorn.Config(app, host="127.0.0.1", port=porta,
                            log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="server")
    thread.start()
    server._thread = thread  # per il join in modalita' browser
    return server


def attendi_server(porta, timeout=30.0):
    """Attende che /api/health risponda (il DB si crea allo startup)."""
    url = "http://127.0.0.1:%d/api/health" % porta
    scadenza = time.time() + timeout
    ultimo = None
    while time.time() < scadenza:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception as exc:  # server non ancora pronto
            ultimo = exc
            time.sleep(0.1)
    raise RuntimeError("Il server non parte entro %.0f s: %s" % (timeout, ultimo))


# --------------------------------------------------------------------------
# 3. Finestra (o browser), errori visibili
# --------------------------------------------------------------------------

def dialogo_errore(titolo, testo):
    """Finestra di errore anche senza console (exe senza finestra nera)."""
    print(testo)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(testo), str(titolo), 0x10)
    except Exception:
        pass


def apri_finestra(url, usa_browser):
    """Apre pywebview.

    True = la finestra si e' aperta e poi chiusa (l'app puo' spegnersi).
    False = modalita' --browser o finestra nativa non disponibile:
    il chiamante mantiene vivo il server finche' l'utente lo ferma.
    """
    if usa_browser:
        return False
    try:
        import webview

        webview.create_window("Registro Lotti", url,
                              width=1440, height=900,
                              min_size=(1100, 700))
        webview.start()
        return True
    except Exception as exc:
        dialogo_errore("Registro Lotti - finestra",
                       "Impossibile aprire la finestra nativa (%s).\n"
                       "Si apre il browser di sistema." % exc)
        return False


# --------------------------------------------------------------------------
# Avvio
# --------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    usa_browser = "--browser" in argv

    try:
        base = prepara_path()

        # patch del percorso DB PRIMA di qualsiasi connessione:
        # inizializza() usava il default calcolato sul __file__ congelato
        import app.db as db

        db.DB_PATH = percorso_db(base)

        # import DOPO il patch: lo startup di FastAPI inizializza il DB
        from app.main import app

        porta = sceglie_porta()
        server = avvia_con(app, porta)
        attendi_server(porta)
        chiusa = apri_finestra("http://127.0.0.1:%d" % porta, usa_browser)

        if chiusa:
            # la finestra e' stata chiusa: spegnimento pulito
            server.should_exit = True
            try:
                server._thread.join(timeout=5)
            except Exception:
                pass
        else:
            # modalita' browser (o finestra non disponibile): apri il browser
            # e resta vivo finche' il server gira (Ctrl+C per fermare)
            webbrowser.open("http://127.0.0.1:%d" % porta)
            try:
                server._thread.join()
            except KeyboardInterrupt:
                server.should_exit = True
        return 0
    except Exception as exc:
        dialogo_errore("Registro Lotti - errore", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
