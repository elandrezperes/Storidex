"""Normalización de lo que devuelven los modelos.

Los modelos no respetan los nombres de campo ni el formato de los códigos de
tiempo. En lugar de confiar en que lo harán, se normaliza todo antes de validar.
Estas funciones son el punto donde el sistema se vuelve tolerante sin perder
control: nada pasa a la fase siguiente sin estar en la forma esperada.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- tiempos
def tiempo_a_segundos(valor) -> int | None:
    """Acepta '00:03', '0:03', '00:00:03', 3, '3', '3s', '00:03.5'."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    t = str(valor).strip().lower().replace("seg", "").replace("s", "").strip()
    if not t:
        return None
    if ":" in t:
        partes = [p for p in re.split(r"[:.]", t) if p != ""]
        try:
            nums = [int(float(p)) for p in partes]
        except ValueError:
            return None
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) >= 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def segundos_a_tiempo(seg: int) -> str:
    seg = max(0, int(seg))
    return f"{seg // 60:02d}:{seg % 60:02d}"


# ---------------------------------------------------------------- funciones
FUNCIONES = {
    "hook": "hook", "gancho": "hook", "apertura": "hook", "inicio": "hook",
    "opening": "hook", "attention": "hook",
    "planteamiento": "planteamiento", "setup": "planteamiento", "presentacion": "planteamiento",
    "presentación": "planteamiento", "contexto": "planteamiento", "introduccion": "planteamiento",
    "introducción": "planteamiento", "desarrollo": "planteamiento",
    "conflicto": "conflicto", "conflict": "conflicto", "tension": "conflicto",
    "tensión": "conflicto", "problema": "conflicto", "complicacion": "conflicto",
    "complicación": "conflicto",
    "giro": "giro", "twist": "giro", "turn": "giro", "punto de giro": "giro",
    "desenlace": "desenlace", "resolution": "desenlace", "resolucion": "desenlace",
    "resolución": "desenlace", "solucion": "desenlace", "solución": "desenlace",
    "climax": "desenlace", "clímax": "desenlace", "solución del conflicto": "desenlace",
    "cta": "cta", "llamado": "cta", "call to action": "cta", "call-to-action": "cta",
    "llamado a la accion": "cta", "llamado a la acción": "cta",
    "cierre": "cierre", "closing": "cierre", "ending": "cierre", "close": "cierre",
    "final": "cierre", "outro": "cierre", "tag": "cierre",
}


def normalizar_funcion(valor) -> str:
    t = str(valor or "").strip().lower()
    t = re.sub(r"[_\-]", " ", t)
    if t in FUNCIONES:
        return FUNCIONES[t]
    for clave, canon in FUNCIONES.items():
        if clave in t:
            return canon
    return "planteamiento"


# ------------------------------------------------------------------ tipos
TIPOS = {
    "scene_heading": "scene_heading", "scene heading": "scene_heading",
    "encabezado": "scene_heading", "encabezado de escena": "scene_heading",
    "slug": "scene_heading", "slugline": "scene_heading", "heading": "scene_heading",
    "localizacion": "scene_heading", "localización": "scene_heading",
    "action": "action", "accion": "action", "acción": "action",
    "descripcion": "action", "descripción": "action", "stage direction": "action",
    "acotacion de escena": "action", "acotación de escena": "action",
    "character": "character", "personaje": "character", "character name": "character",
    "parenthetical": "parenthetical", "parentetico": "parenthetical",
    "parentético": "parenthetical", "acotacion": "parenthetical",
    "acotación": "parenthetical", "paréntesis": "parenthetical", "parentesis": "parenthetical",
    "dialogue": "dialogue", "dialogo": "dialogue", "diálogo": "dialogue",
    "line": "dialogue", "linea": "dialogue", "línea": "dialogue", "speech": "dialogue",
    "transition": "transition", "transicion": "transition", "transición": "transition",
    "title": "title", "titulo": "title", "título": "title", "rotulo": "title",
    "rótulo": "title", "card": "title", "cartela": "title",
}

ORDEN_TIPOS = ["scene_heading", "action", "character", "parenthetical",
               "dialogue", "transition", "title"]


def normalizar_tipo(valor) -> str | None:
    t = str(valor or "").strip().lower()
    t = re.sub(r"[_\-]", " ", t)
    t = re.sub(r"\s+", " ", t)
    if t in TIPOS:
        return TIPOS[t]
    for clave, canon in TIPOS.items():
        if clave in t:
            return canon
    return None


# ------------------------------------------------------------- estructuras
def tomar_lista(datos, claves: tuple[str, ...]) -> list:
    """Devuelve la primera lista que aparezca bajo alguna de las claves."""
    if datos is None:
        return []
    if isinstance(datos, list):
        return [x for x in datos if isinstance(x, dict)]
    if not isinstance(datos, dict):
        return []
    for clave in claves:
        valor = datos.get(clave)
        if isinstance(valor, list):
            return [x for x in valor if isinstance(x, dict)]
        if isinstance(valor, dict):
            # un dict de elementos indexados: {"A": {...}, "B": {...}}
            hijos = [v for v in valor.values() if isinstance(v, dict)]
            if hijos:
                return hijos
    # último recurso: la primera lista de diccionarios que haya
    for valor in datos.values():
        if isinstance(valor, list) and valor and all(isinstance(x, dict) for x in valor):
            return valor
    return []


def tomar_campo(d: dict, claves: tuple[str, ...], por_defecto: str = "") -> str:
    for clave in claves:
        valor = d.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return por_defecto


