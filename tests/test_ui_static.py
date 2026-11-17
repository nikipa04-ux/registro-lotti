"""Guardia statica all'interfaccia: nessuna funzione JS morta, nessun controllo HTML senza JS.

Regola nata da un bug reale (17/11/2026): il bottone "Salva ricetta"
(nr-salva) aveva perso il listener, così salvaRicetta era definita ma
mai richiamata e dalla modale non si salvava niente. I test pytest non
vedono il JavaScript: qui si legge il sorgente con regex, niente browser.
"""
import re
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "app" / "ui"
JS = (UI / "app.js").read_text(encoding="utf-8")
HTML = (UI / "index.html").read_text(encoding="utf-8")


def test_nessuna_funzione_js_definita_ma_mai_usata():
    funzioni = re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", JS)
    morte = [
        nome for nome in funzioni
        if len(re.findall(r"\b" + re.escape(nome) + r"\b", JS)) < 2
    ]
    assert funzioni, "nessuna funzione trovata in app.js: lettura fallita?"
    assert not morte, "Funzioni JS mai richiamate: " + ", ".join(sorted(morte))


def test_nessun_id_html_dimenticato_dal_js():
    ids_html = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', HTML))
    # le sezioni si attivano per nome: mostraSezione costruisce "sez-" + nome
    ignorati = {i for i in ids_html if i.startswith("sez-")}
    orfani = sorted(i for i in ids_html - ignorati if i not in JS)
    assert not orfani, "ID presenti nell'HTML ma mai toccati dal JS: " + ", ".join(orfani)
