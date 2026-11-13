"""P1b · Investigación local (sin modelos).

Motor de reglas que clasifica el producto y compone la investigación con el
material del briefing. Se usa cuando STORIDEX_DRY_RUN está activo.

Regla que respeta igual que la fase real: nunca inventa competidores con nombre.
Si no hay fuente, la lista va vacía y `sin_datos` es verdadero.
"""
from __future__ import annotations

import json
import os

from .. import contracts, llm
from ..levels import T2, T3, T4


def _muestra(brief: dict) -> dict:
    """Respuesta local para modo seco, derivada del briefing real."""
    from .. import local
    return local.research(brief)


def ejecutar(brief: dict) -> dict:
    from .. import local

    modo = brief.get("competencia", {}).get("modo", "ambas")
    if modo == "ninguna":
        datos = local.research(brief)
    elif llm.DRY:
        datos = local.research(brief)
    else:
        sistema = llm.cargar_prompt("v1_research.md")
        usuario = (
            "BRIEFING\n" + json.dumps({k: brief[k] for k in
                                       ("marca", "ubicacion", "segmento", "objetivo")},
                                      ensure_ascii=False, indent=2)
            + f"\n\nMODO DE COMPETENCIA SOLICITADO: {modo}\n\n"
            "Esquema de salida:\n"
            '{"competencia": {"modo_solicitado": "", "de_marca": [{"nombre": "", '
            '"descripcion": "", "fuentes": [], "nivel": "T2", "hallazgos": []}], '
            '"de_feed": [{"patron": "", "ejemplo": "", "fuentes": [], "nivel": "T3"}], '
            '"sin_datos": false}, "mercado": {"tendencias": [{"termino": "", '
            '"fuente": "", "nivel": "T3"}]}, "oportunidad": {"texto": "", "nivel": "T3"}, '
            '"fuentes_total": 0}'
        )
        r = llm.investigar(sistema, usuario, seco=_muestra(brief) if llm.DRY else None)
        datos = llm.parsear(r, "el análisis de mercado")
        if r.fuentes:
            datos["_fuentes_grounding"] = r.fuentes[:20]

    # refuerzo de la regla: sin URL, el nivel baja a inferido
    comp = datos.get("competencia")
    if not isinstance(comp, dict):
        comp = {}
    comp.setdefault("modo_solicitado", brief.get("competencia", {}).get("modo", "ambas"))
    for bloque in ("de_marca", "de_feed"):
        if not isinstance(comp.get(bloque), list):
            comp[bloque] = []
        for c in comp[bloque]:
            if not isinstance(c, dict):
                continue
            if not c.get("fuentes"):
                c["nivel"] = T4
            elif c.get("nivel") not in (T2, T3):
                c["nivel"] = T3
    comp["sin_datos"] = not (comp["de_marca"] or comp["de_feed"])
    datos["competencia"] = comp

    # el resto del bloque se normaliza para que las fases siguientes no fallen
    if not isinstance(datos.get("mercado"), dict):
        datos["mercado"] = {"tendencias": []}
    if not isinstance(datos.get("mercado", {}).get("tendencias"), list):
        datos["mercado"]["tendencias"] = []

    op = datos.get("oportunidad")
    if not isinstance(op, dict):
        op = {"texto": "", "nivel": T4}
    op.setdefault("texto", "")
    op.setdefault("nivel", T3)
    datos["oportunidad"] = op

    datos.setdefault("fuentes_total", 0)

    contracts.research(datos)
    return datos


