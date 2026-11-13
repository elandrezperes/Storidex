"""P3 · Tres premisas con estructura de Egri.

El modelo a veces devuelve el JSON con otra forma (una lista suelta, una clave
distinta, o texto alrededor). Esta fase normaliza lo que llegue, y si no hay
manera de rescatar tres premisas, vuelve a pedirlas una vez. Nunca revienta con
un KeyError sin decir qué pasó.
"""
from __future__ import annotations

import json

from .. import contracts, llm
from ..levels import T4, peor

CLAVES_LISTA = ("premisas", "premises", "opciones", "options", "alternativas",
                "ideas", "resultados", "results", "items", "propuestas")


class PremisasInvalidas(RuntimeError):
    """El modelo no devolvió tres premisas utilizables."""


def _extraer(datos) -> list[dict]:
    """Acepta dict con lista dentro, lista suelta, o dict indexado por A/B/C."""
    if isinstance(datos, list):
        return [d for d in datos if isinstance(d, dict)]

    if not isinstance(datos, dict):
        return []

    for clave in CLAVES_LISTA:
        valor = datos.get(clave)
        if isinstance(valor, list):
            return [d for d in valor if isinstance(d, dict)]

    # dict indexado: {"A": {...}, "B": {...}, "C": {...}}
    if all(k in datos for k in ("A", "B", "C")):
        return [datos[k] for k in ("A", "B", "C") if isinstance(datos[k], dict)]

    # un único objeto de premisa suelto
    if any(k in datos for k in ("caracter", "proposicion", "conflicto")):
        return [datos]

    return []


def _normalizar(lista: list[dict]) -> list[dict]:
    """Completa campos que el modelo haya nombrado distinto y asigna id."""
    salida = []
    equivalencias = {
        "caracter": ("caracter", "character", "personaje", "quien", "protagonista"),
        "conflicto": ("conflicto", "conflict", "tension", "obstaculo"),
        "desenlace": ("desenlace", "resolution", "outcome", "final", "resolucion"),
        "proposicion": ("proposicion", "premise", "proposition", "idea", "resumen"),
    }
    for i, p in enumerate(lista[:3]):
        limpio = {"id": p.get("id") or "ABC"[i]}
        for campo, alias in equivalencias.items():
            valor = p.get(campo)
            if not valor:
                for a in alias:
                    if p.get(a):
                        valor = p[a]
                        break
            limpio[campo] = str(valor or "").strip()
        limpio["usa_oportunidad"] = bool(p.get("usa_oportunidad", False))
        limpio["nivel"] = p.get("nivel", T4)
        salida.append(limpio)
    return salida


def _completas(lista: list[dict]) -> bool:
    return len(lista) == 3 and all(
        all(p.get(c) for c in ("caracter", "conflicto", "desenlace", "proposicion"))
        for p in lista)


def ejecutar(brief: dict, ficha: dict, research: dict, persona_txt: str) -> dict:
    from .. import local

    if llm.DRY:
        datos = local.premisas(brief, ficha)
    else:
        sistema = llm.cargar_prompt("v1_premisas.md")
        usuario = (
            persona_txt + "\n"
            f"OBJETIVO DEL VIDEO: {', '.join(brief['objetivo'])}\n"
            f"FORMATO: {brief['forma']['tipo']} de {brief['forma']['duracion_objetivo_s']} s\n"
            f"TONO: {brief['forma']['tono']}\n"
            f"FRASE OBLIGATORIA: {brief['forma'].get('especificaciones') or '(ninguna)'}\n"
            f"PRODUCTO: {brief['marca']['nombre']} — {brief['marca']['producto']}\n\n"
            f"OPORTUNIDAD DETECTADA: {research.get('oportunidad', {}).get('texto') or '(sin datos)'}\n\n"
            "Devuelve EXACTAMENTE este objeto, con la clave «premisas» y tres elementos:\n"
            '{"premisas":[{"id":"A","caracter":"","conflicto":"","desenlace":"",'
            '"proposicion":"","usa_oportunidad":false},'
            '{"id":"B","caracter":"","conflicto":"","desenlace":"","proposicion":"",'
            '"usa_oportunidad":true},'
            '{"id":"C","caracter":"","conflicto":"","desenlace":"","proposicion":"",'
            '"usa_oportunidad":false}]}'
        )

        r = llm.pedir_json(sistema, usuario, seco=local.premisas(brief, ficha) if llm.DRY else None,
                           temperatura=0.95)
        crudo = r.texto
        try:
            lista = _extraer(json.loads(crudo))
        except Exception:  # noqa: BLE001
            lista = []
        lista = _normalizar(lista)

        # segunda oportunidad: se le muestra su propia salida y se le pide corregir
        if not _completas(lista):
            usuario2 = (
                usuario
                + "\n\nTU RESPUESTA ANTERIOR NO SIRVIÓ. Devuelve solo el objeto JSON "
                  "con la clave «premisas» y exactamente tres elementos, cada uno con "
                  "caracter, conflicto, desenlace y proposicion no vacíos.\n"
                  "Respuesta anterior:\n" + crudo[:1500]
            )
            r2 = llm.pedir_json(sistema, usuario2, seco=None, temperatura=0.9)
            try:
                lista = _normalizar(_extraer(json.loads(r2.texto)))
            except Exception:  # noqa: BLE001
                lista = []

        if not _completas(lista):
            raise PremisasInvalidas(
                "El modelo no devolvió tres premisas utilizables después de dos intentos. "
                "Puede ser un límite momentáneo del servicio: vuelve a pulsar el botón. "
                "Si persiste, prueba con el tono «neutro» o una duración distinta."
            )

        datos = {"premisas": lista}

    for p in datos["premisas"]:
        p["nivel"] = peor([p.get("nivel", T4), ficha["confianza"]["nivel_global"]])

    contracts.premisas(datos)
    return datos

