"""Exportación a Final Draft (.fdx).

El formato se hereda, no se inventa: mismas medidas y mismos tipos de párrafo
que el formato profesional, con el código de tiempo en la columna del número
de escena (AGENTS.md §7).
"""
from __future__ import annotations

from xml.sax.saxutils import escape

MAPA = {
    "scene_heading": "Scene Heading",
    "action": "Action",
    "character": "Character",
    "parenthetical": "Parenthetical",
    "dialogue": "Dialogue",
    "transition": "Transition",
    "title": "Action",
}

CABECERA = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'
    '<FinalDraft DocumentType="Script" Template="No Template" Version="1">\n'
    "  <Content>\n"
)
PIE = "  </Content>\n</FinalDraft>\n"


def _parrafo(p: dict) -> str:
    tipo = MAPA.get(p["tipo"], "Action")
    texto = escape(p["texto"])
    tc = p.get("tc")
    if tc and p["tipo"] == "scene_heading":
        # el código de tiempo ocupa el lugar del número de escena
        return (f'    <Paragraph Type="{tipo}" Number="{escape(tc)}">'
                f"<Text>{texto}</Text></Paragraph>\n")
    return f'    <Paragraph Type="{tipo}"><Text>{texto}</Text></Paragraph>\n'


def generar(guion: dict, brief: dict) -> bytes:
    cuerpo = "".join(_parrafo(p) for p in guion["parrafos"])
    titulo = escape(f"{brief['marca']['nombre']} — {brief['marca']['producto']}")
    documento = (
        CABECERA
        + f"    <Paragraph Type=\"Title\"><Text>{titulo}</Text></Paragraph>\n"
        + cuerpo
        + PIE
    )
    return documento.encode("utf-8")


def guardar(guion: dict, brief: dict, ruta: str) -> str:
    with open(ruta, "wb") as f:
        f.write(generar(guion, brief))
    return ruta

