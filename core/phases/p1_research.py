"""P1b · Investigación local (sin modelos).

Motor de reglas que clasifica el producto y compone la investigación con el
material del briefing. Se usa cuando STORIDEX_DRY_RUN está activo.

Regla que respeta igual que la fase real: nunca inventa competidores con nombre.
Si no hay fuente, la lista va vacía y `sin_datos` es verdadero.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json

from .. import contracts, llm, referencias, services
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
        sistema = llm.cargar_prompt("v2_research.md")
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
        usuario += "\n\n" + json.dumps(
            {"fuentes_de_consulta": referencias.catalogo()["fuentes"]}, ensure_ascii=False
        )
        try:
            for attempt in range(2):
                r = llm.investigar(sistema, usuario, seco=_muestra(brief) if llm.DRY else None)
                try:
                    datos = llm.parsear(r, "el análisis de mercado")
                    contracts.research(datos)
                    break
                except (llm.RespuestaInvalida, contracts.ContratoInvalido) as exc:
                    if attempt:
                        raise
                    usuario += "\n" + str(llm.cargar_prompt("v1_corregir_contrato.md")) + "\n" + str(exc)
        except Exception as exc:
            llm.registrar_error("p1_research", RuntimeError(type(exc).__name__))
            llm.error_servicio("gemini")
            r = llm.Respuesta("{}", "sin-busqueda")
            datos = local.research(brief)
            datos["sin_busqueda"] = True
        if r.fuentes:
            datos["_fuentes_grounding"] = r.fuentes[:20]

    comp = datos.get("competencia")
    if not isinstance(comp, dict):
        comp = {}
    comp["modo_solicitado"] = modo
    market = datos.get("mercado")
    if not isinstance(market, dict):
        market = {}
    used = set()
    grounded = {uri for uri in datos.get("_fuentes_grounding", [])
                if isinstance(uri, str) and uri.startswith(("https://", "http://"))}
    for block, modes in (("de_marca", {"marca", "ambas"}), ("de_feed", {"feed", "ambas"})):
        items = comp.get(block)
        comp[block] = []
        if modo not in modes or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            urls = item.get("fuentes")
            sources = [url for url in urls if isinstance(url, str) and url in grounded
                       ] if isinstance(urls, list) else []
            if sources:
                comp[block].append({**item, "fuentes": sources,
                                    "nivel": T2 if item.get("nivel") == T2 else T3})
                used.update(sources)
            elif llm.DRY and block == "de_feed":
                comp[block].append({**item, "fuentes": [], "nivel": T4})
    trends = market.get("tendencias")
    market["tendencias"] = [
        {**item, "nivel": T3} for item in trends
        if isinstance(item, dict) and isinstance(item.get("fuente"), str)
        and item["fuente"] in grounded
    ] if isinstance(trends, list) else []
    used.update(item["fuente"] for item in market["tendencias"])
    comp["sin_datos"] = not comp["de_marca"] if modo in {"marca", "ambas"} else not comp["de_feed"]
    datos["competencia"] = comp
    datos["mercado"] = market
    op = datos.get("oportunidad")
    if not isinstance(op, dict) or not used:
        text = op.get("texto", "") if llm.DRY and isinstance(op, dict) else ""
        op = {"texto": text or "Sin fuentes verificables. Cualquier oportunidad se considera inferida.",
              "nivel": T4}
    datos["oportunidad"] = op
    datos["fuentes_total"] = len(used)

    datos["dossier_referencias"] = (
        brief.get("dossier_referencias") or referencias.congelar(brief)
    )
    dossier = deepcopy(datos["dossier_referencias"])
    contextual = datos.pop("referencias_contextuales", [])
    allowed = referencias.catalogo()["fuentes"]
    now = datetime.now(timezone.utc).isoformat()
    if isinstance(contextual, list):
        for item in contextual[:6]:
            if not isinstance(item, dict):
                continue
            source = item.get("fuente")
            url = item.get("url")
            finding = item.get("hallazgo")
            if (isinstance(source, str) and source in allowed
                    and isinstance(url, str) and url in grounded
                    and isinstance(finding, str) and finding.strip()):
                dossier["referencias"].append({
                    "id": f"S{len(dossier['referencias']) + 1}",
                    "fuente": source, "url": url, "fecha": now,
                    "mercado": brief["ubicacion"],
                    "hallazgo": finding.strip()[:2000], "origen": "busqueda_grounding",
                    "nivel": T3, "veracidad": "sin_verificacion",
                })
    datos["fuentes_total"] = len(used | {
        ref["url"] for ref in dossier["referencias"] if ref["origen"] == "busqueda_grounding"
    })
    dossier, connection_states = services.research(brief, dossier)
    datos["services"] = connection_states
    datos["dossier_referencias"] = dossier
    datos["herramientas"] = {
        key: {
            "nombre": value["nombre"],
            "descripcion": value["descripcion"],
            "aplicacion": value["aplicacion"],
            "estado": (
                "referencias_disponibles" if any(ref["fuente"] == key for ref in dossier["referencias"])
                else "patrones_disponibles" if any(p["fuente"] == key for p in dossier["patrones"])
                else "sin_datos_actuales"
            ),
        } for key, value in allowed.items()
    }
    contracts.research(datos)
    return datos


