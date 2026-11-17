"""Guardia statica ai moduli API: nessun endpoint può oscurare un import.

Regola nata da un bug reale (17/11/2026): in app/api/anagrafiche.py
l'endpoint ``def lista_prodotti(...)`` ribattezzava il nome importato
dalla logica, così /prodotti-lab chiamava l'endpoint sbagliato
(TypeError -> 500: "Il server non risponde" nella card Prodotti).
Questo test legge i sorgenti con ast: non serve importare fastapi.
"""
import ast
from pathlib import Path

API = Path(__file__).resolve().parent.parent / "app" / "api"


def _ridefiniti(sorgente):
    """I nomi di def/class di primo livello che oscurano un import."""
    albero = ast.parse(sorgente)
    importati = set()
    for nodo in albero.body:
        if isinstance(nodo, ast.ImportFrom):
            for a in nodo.names:
                importati.add(a.asname or a.name)
        elif isinstance(nodo, ast.Import):
            for a in nodo.names:
                importati.add((a.asname or a.name).split(".")[0])
    return [
        nodo.name for nodo in albero.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and nodo.name in importati
    ]


def test_nessun_endpoint_oscura_un_import():
    moduli = sorted(API.glob("*.py"))
    assert moduli, "cartella app/api non trovata"
    violazioni = []
    for f in moduli:
        for nome in _ridefiniti(f.read_text(encoding="utf-8")):
            violazioni.append(f"{f.name}: def {nome} oscura l'import omonimo")
    assert not violazioni, "Endpoint che oscurano un import: " + "; ".join(violazioni)
