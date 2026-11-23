"""Validación de los contratos de cada fase (AGENTS.md §5).

Se valida a mano, sin dependencias, para que el proyecto arranque en cualquier
entorno. Cada función lanza ContratoInvalido con un mensaje en español que se
muestra en la interfaz tal cual.
"""
from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache
from jsonschema import Draft202012Validator

@lru_cache(maxsize=None)
def _schema(name):
    return json.loads((Path(__file__).parent / "schemas" / f"{name}.json").read_text())

def validar(name, data):
    errors = sorted(Draft202012Validator(_schema(name)).iter_errors(data), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        field = ".".join(map(str, error.path)) or "raíz"
        raise ContratoInvalido(f"Contrato {name}, campo {field}: {error.message}")
    return data



class ContratoInvalido(ValueError):
    pass


def _exigir(cond: bool, mensaje: str) -> None:
    if not cond:
        raise ContratoInvalido(mensaje)


# --------------------------------------------------------------------- P0
def brief(d: dict) -> dict:
    validar("p0_brief", d)
    _exigir(isinstance(d, dict), "El briefing debe ser un objeto.")
    for k in ("marca", "ubicacion", "segmento", "forma"):
        _exigir(k in d, f"Falta el bloque «{k}» en el briefing.")

    _exigir(bool(d["marca"].get("nombre", "").strip()), "La marca no puede quedar vacía.")
    _exigir(bool(d["marca"].get("producto", "").strip()), "El producto no puede quedar vacío.")

    seg = d["segmento"]
    _exigir(isinstance(seg.get("edad_min"), int) and isinstance(seg.get("edad_max"), int),
            "El rango de edad debe tener dos extremos numéricos.")
    _exigir(18 <= seg["edad_min"] < seg["edad_max"] <= 70,
            "El rango de edad debe ir de 18 a 70 años y ser creciente.")
    _exigir(seg.get("sexo") in ("ambos", "f", "m"), "El sexo debe ser «ambos», «f» o «m».")

    forma = d["forma"]
    _exigir(forma.get("tipo") in ("sketch", "publicitario"),
            "El tipo de video debe ser «sketch» o «publicitario».")
    _exigir(forma.get("tono") in ("neutro", "moderado", "marcado"),
            "El tono debe ser «neutro», «moderado» o «marcado».")
    _exigir(forma.get("duracion_objetivo_s") in (15, 30, 45, 60),
            "La duración debe ser 15, 30, 45 o 60 segundos.")
    _exigir(len(forma.get("participantes", [])) >= 1,
            "Debe declararse al menos un participante.")
    nombres = [p.get("nombre", "").strip().casefold() for p in forma["participantes"]]
    _exigir(all(nombres) and len(set(nombres)) == len(nombres),
            "Cada participante debe tener un nombre distinto.")
    _exigir(any(p.get("protagonico") for p in forma["participantes"]),
            "Debe haber un participante protagónico.")

    _exigir(isinstance(forma.get("recursos", ""), str),
            "Describe los recursos disponibles con texto.")
    sources = d.get("evidencia_publico", [])
    _exigir(isinstance(sources, list) and len(sources) <= 20,
            "Se admiten hasta 20 registros de evidencia del público.")
    for source in sources:
        _exigir(isinstance(source, dict)
                and source.get("origen") in ("observacion", "declaracion_dueno")
                and all(isinstance(source.get(key), str) and source[key].strip()
                        for key in ("informante", "fecha", "fragmento")),
                "Cada evidencia requiere origen, informante, fecha y fragmento.")

    from . import referencias
    try:
        referencias.validar(d)
    except ValueError as exc:
        raise ContratoInvalido(str(exc)) from exc

    if "espacio" in d:
        space = d["espacio"]
        _exigir(isinstance(space, dict) and space.get("modo") in {"auto", "fijo"},
                "El modo de espacio debe ser auto o fijo.")
        if space.get("modo") == "fijo":
            from . import espacio
            _exigir(not espacio.validar(space), "Completa el tipo, la localización y el momento del espacio.")

    objetivo = d.get("objetivo") or []
    _exigir(len(objetivo) >= 1, "Debe elegirse al menos un objetivo del video.")
    _exigir(set(objetivo) <= {"views", "cta", "ventas", "seguidores"},
            "Objetivo no reconocido. Usa views, cta, ventas o seguidores.")

    modo = d.get("competencia", {}).get("modo", "ambas")
    _exigir(modo in ("marca", "feed", "ambas", "ninguna"), "Modo de competencia no válido.")
    return d


# --------------------------------------------------------------------- P1
def research(d: dict) -> dict:
    validar("p1_research", d)
    _exigir(isinstance(d.get("competencia"), dict), "Falta el bloque «competencia».")
    _exigir("de_marca" in d["competencia"], "Falta la lista «de_marca» (puede estar vacía).")
    _exigir("de_feed" in d["competencia"], "Falta la lista «de_feed» (puede estar vacía).")
    # regla dura: ningún competidor sin fuente puede ser T2/T3
    for c in d["competencia"]["de_marca"]:
        if not c.get("fuentes"):
            c["nivel"] = "T4"
    return d


# --------------------------------------------------------------------- P2
def persona(d: dict, brief_: dict) -> dict:
    validar("p2_persona", d)
    for k in ("perfil", "consumo", "conflicto", "lenguaje", "anti_persona"):
        _exigir(k in d, f"Falta el bloque «{k}» en la ficha de persona.")

    seg = brief_["segmento"]
    edad = d["perfil"].get("edad")
    _exigir(isinstance(edad, int), "La edad de la persona debe ser un número entero.")
    _exigir(seg["edad_min"] <= edad <= seg["edad_max"],
            f"La persona tiene {edad} años, fuera del rango {seg['edad_min']}–{seg['edad_max']}.")

    return d


# --------------------------------------------------------------------- P3
def premisas(d: dict) -> dict:
    validar("p3_premisas", d)
    items = d.get("premisas", [])
    _exigir(len(items) == 3, "Deben generarse exactamente tres premisas.")
    for p in items:
        for k in ("caracter", "conflicto", "desenlace", "proposicion"):
            _exigir(bool(str(p.get(k, "")).strip()), f"La premisa {p.get('id','?')} no tiene «{k}».")
    return d


# --------------------------------------------------------------------- P4
def escaleta(d: dict) -> dict:
    validar("p4_escaleta", d)
    beats = d.get("beats", [])
    _exigir(len(beats) >= 2, "La escaleta necesita al menos dos unidades.")
    _exigir(beats[0].get("funcion") == "hook", "La primera unidad debe ser el gancho.")

    def seg(tc: str) -> int:
        m, s = tc.split(":")
        return int(m) * 60 + int(s)

    _exigir(seg(beats[0]["tc_out"]) - seg(beats[0]["tc_in"]) <= 3,
            "El gancho no puede durar más de tres segundos.")
    previous = 0
    for beat in beats:
        start, end = seg(beat["tc_in"]), seg(beat["tc_out"])
        _exigir(start == previous and end > start, "Los tiempos deben ser contiguos y crecientes.")
        previous = end
    return d


# --------------------------------------------------------------------- P5
TIPOS_VALIDOS = {"scene_heading", "action", "character", "parenthetical",
                 "dialogue", "transition", "title"}


def guion(d: dict, brief_: dict) -> dict:
    validar("p5_guion", d)
    parrafos = d.get("parrafos", [])
    _exigir(len(parrafos) >= 4, "El guion está vacío o incompleto.")
    for p in parrafos:
        _exigir(p.get("tipo") in TIPOS_VALIDOS,
                f"Tipo de párrafo no permitido: «{p.get('tipo')}».")
        _exigir(bool(str(p.get("texto", "")).strip()), "Hay un párrafo sin texto.")
        if p["tipo"] == "character":
            allowed = {item["nombre"].strip().casefold() for item in brief_["forma"]["participantes"]}
            _exigir(p["texto"].strip().casefold() in allowed,
                    f"Personaje fuera del elenco: {p['texto']}. Usa solamente {sorted(allowed)}.")
    return d


# --------------------------------------------------------------------- P6
def qa(d: dict) -> dict:
    validar("p6_qa", d)
    for k in ("duracion", "cuarta_pared", "tono", "nivel_global"):
        _exigir(k in d, f"Falta «{k}» en el control de calidad.")
    return d


