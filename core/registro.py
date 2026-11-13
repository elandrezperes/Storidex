"""Registro lingüístico derivado de la ubicación que eligió el usuario.

No se adivina nada: el registro es una CONSECUENCIA de país, provincia y ciudad,
que el usuario declaró. El tono decide cuánto de ese registro se usa.

- neutro    → español neutro, sin localismos
- moderado  → registro local en dosis: léxico y tratamiento sí, caricatura no
- marcado   → registro local pleno, con las voces propias de la variedad
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

_DATOS = None


def _cargar() -> dict:
    global _DATOS
    if _DATOS is None:
        ruta = os.path.join(os.path.dirname(__file__), "data", "registros.json")
        with open(ruta, encoding="utf-8") as f:
            _DATOS = json.load(f)
    return _DATOS


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def obtener(pais: str, provincia: str = "", ciudad: str = "") -> dict:
    """Registro para una ubicación declarada. Nunca falla: cae a neutro."""
    datos = _cargar()
    base = {"registro": "español neutro", "tratamiento": "tuteo",
            "marcadores": [], "evitar": [], "ejemplo": "", "pais": pais,
            "ciudad": ciudad, "especifico": False}

    rama = datos.get(pais.strip()) or datos["Neutro"]
    entrada = None
    for clave, valor in rama.items():
        if clave.startswith("_"):
            continue
        if _sin_tildes(clave) == _sin_tildes(provincia or "").strip():
            entrada = valor
            break
    especifico = entrada is not None
    if entrada is None:
        entrada = rama.get("_default") or datos["Neutro"]["_default"]

    salida = dict(base)
    salida.update({k: v for k, v in entrada.items() if not k.startswith("_")})
    salida["pais"] = pais
    salida["provincia"] = provincia
    salida["ciudad"] = ciudad
    salida["especifico"] = especifico
    return salida


def nombre(reg: dict) -> str:
    """Etiqueta corta para mostrar en la interfaz."""
    return reg.get("registro", "español neutro")


def bloque_prompt(reg: dict, tono: str) -> str:
    """Texto que se inyecta en la instrucción del modelo."""
    if tono == "neutro":
        return (
            "REGISTRO LINGÜÍSTICO: español neutro. El usuario eligió tono neutro, "
            "así que NO uses localismos, ni voseo, ni modismos regionales. "
            "Tratamiento: tú / usted. Vocabulario estándar.\n"
            "PROHIBIDO usar estas voces de variedades regionales: "
            + ", ".join(_cargar()["Neutro"]["_default"]["evitar"]) + "\n"
        )

    intensidad = (
        "usa el registro de forma natural y sostenida: el léxico local debe estar "
        "presente en la mayor parte del diálogo, como habla la gente en la calle"
        if tono == "marcado" else
        "usa el registro con moderación: tratamiento y algunas voces locales, "
        "sin que suene a imitación forzada"
    )

    lineas = [
        f"REGISTRO LINGÜÍSTICO OBLIGATORIO: {reg['registro']}.",
        f"Ubicación declarada por el usuario: {reg.get('ciudad','')}, "
        f"{reg.get('provincia','')}, {reg.get('pais','')}.",
        f"Tratamiento: {reg['tratamiento']}.",
        f"Intensidad pedida por el tono «{tono}»: {intensidad}.",
        "Voces y giros propios de esta variedad (úsalos, no los imites): "
        + ", ".join(reg["marcadores"][:12]) + ".",
        "PROHIBIDO usar estas voces, que son de OTRA variedad y delatan que el "
        "guion no es local: " + ", ".join(reg["evitar"]) + ".",
    ]
    ej = reg.get("ejemplo")
    if ej:
        lineas.append(f"Referencia de registro (no la copies, es solo el tono): «{ej}»")
    return "\n".join(lineas) + "\n"


def _palabras(texto: str) -> set[str]:
    return {_sin_tildes(p) for p in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", texto)}


def verificar(texto: str, reg: dict, tono: str) -> dict:
    """Comprueba que el texto respete la variedad y el tono pedidos."""
    palabras = _palabras(texto)
    ajenismos = sorted({v for v in reg["evitar"]
                        if _sin_tildes(v) in palabras})
    marcadores = sorted({m for m in reg["marcadores"]
                         if _sin_tildes(m) in palabras})

    problemas = []
    if ajenismos:
        problemas.append(
            "Usa voces de otra variedad del español: " + ", ".join(ajenismos)
            + f". El registro pedido es {reg['registro']}.")

    if tono == "neutro" and marcadores:
        problemas.append(
            "El tono es neutro pero aparecen localismos: " + ", ".join(marcadores) + ".")
    elif tono == "marcado" and not marcadores:
        problemas.append(
            f"El tono es marcado y no hay ninguna voz del registro "
            f"({reg['registro']}). El diálogo suena neutro.")

    return {
        "registro": reg["registro"],
        "tono": tono,
        "tratamiento": reg["tratamiento"],
        "marcadores_encontrados": marcadores,
        "ajenismos": ajenismos,
        "ok": not problemas,
        "problemas": problemas,
    }

