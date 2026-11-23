"""P3 · Tres premisas con estructura de Egri.

El modelo a veces devuelve el JSON con otra forma (una lista suelta, una clave
distinta, o texto alrededor). Esta fase normaliza lo que llegue, y si no hay
manera de rescatar tres premisas, vuelve a pedirlas una vez. Nunca revienta con
un KeyError sin decir qué pasó.
"""
from __future__ import annotations

import json

from .. import contracts, evidence, llm, referencias
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
        limpio = {"id": "ABC"[i]}
        for campo, alias in equivalencias.items():
            valor = p.get(campo)
            if not valor:
                for a in alias:
                    if p.get(a):
                        valor = p[a]
                        break
            limpio[campo] = str(valor or "").strip()
        for field in ("recurso_visual", "razon_estrategica"):
            value = p.get(field)
            limpio[field] = value.strip() if isinstance(value, str) else ""
        limpio["afirmaciones"] = p.get("afirmaciones")
        limpio["referencias_creativas"] = p.get("referencias_creativas")
        limpio["usa_oportunidad"] = bool(p.get("usa_oportunidad", False))
        limpio["nivel"] = p.get("nivel", T4)
        salida.append(limpio)
    return salida


def _completas(lista: list[dict]) -> bool:
    return len(lista) == 3 and all(
        all(p.get(c) for c in ("caracter", "conflicto", "desenlace", "proposicion"))
        for p in lista)


def _alternativas_validas(lista):
    return _completas(lista) and all(
        len({p[field].casefold() for p in lista if p[field]}) == 3
        for field in ("conflicto", "recurso_visual", "desenlace")
    ) and all(p["razon_estrategica"] for p in lista)


def ejecutar(brief: dict, ficha: dict, research: dict, persona_txt: str) -> dict:
    from .. import local

    dossier = (
        research.get("dossier_referencias") or brief.get("dossier_referencias")
        or referencias.congelar(brief)
    )
    if llm.DRY:
        datos = local.premisas(brief, ficha)
    else:
        sistema = llm.cargar_prompt("v3_premisas.md")
        usuario = (
            persona_txt + "\n"
            f"OBJETIVO DEL VIDEO: {', '.join(brief['objetivo'])}\n"
            f"FORMATO: {brief['forma']['tipo']} de {brief['forma']['duracion_objetivo_s']} s\n"
            f"TONO: {brief['forma']['tono']}\n"
            f"FRASE OBLIGATORIA: {brief['forma'].get('especificaciones') or '(ninguna)'}\n"
            f"PRODUCTO: {brief['marca']['nombre']} — {brief['marca']['producto']}\n\n"
            f"OPORTUNIDAD DETECTADA: {research.get('oportunidad', {}).get('texto') or '(sin datos)'}\n\n"
            f"RECURSOS DISPONIBLES: {brief['forma'].get('recursos') or '(sin declarar)'}"
        )

        usuario += "\n\n" + json.dumps(referencias.contexto(dossier), ensure_ascii=False)
        def validate(data):
            contracts.premisas(data)
            contracts._exigir({p["id"] for p in data["premisas"]} == {"A", "B", "C"},
                              "Las premisas deben identificarse A, B y C.")
            contracts._exigir(_alternativas_validas(data["premisas"]),
                              "Diferencia conflicto, recurso visual y desenlace de las tres premisas.")
            contracts._exigir(any(p["usa_oportunidad"] for p in data["premisas"]),
                              "Una premisa debe usar la oportunidad, aunque sea inferida.")
        try:
            datos = llm.pedir_validado(sistema, usuario, validate, esquema="p3_premisas", seco=None, temperatura=0.9)
        except (contracts.ContratoInvalido, llm.RespuestaInvalida) as exc:
            raise PremisasInvalidas("No se recibieron tres premisas válidas después de dos intentos.") from exc

    sources = {item["id"]: item for collection in ("patrones", "referencias")
               for item in dossier[collection]}
    for p in datos["premisas"]:
        selected = evidence.valid_refs(p.get("referencias_creativas"), sources)
        p["referencias_creativas"] = [sources[key] for key in selected[:3]]
        p["afirmaciones"] = evidence.valid_refs(
            p.get("afirmaciones"), ficha.get("afirmaciones", {})
        )
        p["nivel"] = peor([p.get("nivel", T4), ficha["confianza"]["nivel_global"]])

    contracts.premisas(datos)
    return datos

