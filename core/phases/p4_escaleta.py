"""P4 · Escaleta con códigos de tiempo. El gancho nunca pasa de 3 s.

El modelo no devuelve los códigos de tiempo de forma fiable, así que se
reconstruyen aquí a partir de las duraciones relativas. Es más robusto y además
garantiza que cumplan el contrato: contiguos, sin huecos y terminando en la
duración objetivo.
"""
from __future__ import annotations

import json

from .. import contracts, evidence, llm, referencias
from ..normaliza import (normalizar_funcion, segundos_a_tiempo, tiempo_a_segundos,
                         tomar_campo, tomar_lista)

# peso de cada función en el reparto del tiempo
PESOS = {"hook": 0.10, "planteamiento": 0.22, "conflicto": 0.28,
         "giro": 0.12, "desenlace": 0.20, "cta": 0.08, "cierre": 0.06}


def _reconstruir(beats: list[dict], duracion: int, tipo: str, refs=()) -> list[dict]:
    """Asigna códigos de tiempo contiguos, respetando el gancho de 3 s."""
    limpios = []
    for b in beats:
        funcion = normalizar_funcion(tomar_campo(b, ("funcion", "function", "tipo", "beats")))
        limpios.append({
            "funcion": funcion,
            "afirmaciones": evidence.valid_refs(b.get("afirmaciones"), refs),
            "descripcion": tomar_campo(
                b, ("descripcion", "description", "texto", "text", "accion", "acción"),
                ""),
            "cuarta_pared": tomar_campo(b, ("cuarta_pared", "fourth_wall"), ""),
            "espacio": b.get("espacio"),
        })

    if not limpios:
        return []

    # el primer beat siempre es el gancho, y nunca pasa de 3 segundos
    if limpios[0]["funcion"] != "hook":
        limpios.insert(0, {"funcion": "hook", "descripcion": "", "cuarta_pared": ""})

    hook = min(3, max(2, duracion // 8))
    resto = max(duracion - hook, 1)

    # Reserva un segundo para cada beat posterior antes de repartir el sobrante.
    if len(limpios) == 1:
        limpios.append({"funcion": "cierre", "descripcion": "", "cuarta_pared": ""})
    limpios = limpios[:resto + 1]
    pesos = [PESOS.get(b["funcion"], 0.15) for b in limpios[1:]]
    sobrante = resto - len(pesos)
    total = sum(pesos)
    cortes = [0, hook]
    acumulado = 0.0
    for i, peso in enumerate(pesos, start=1):
        acumulado += peso
        cortes.append(hook + i + round(sobrante * acumulado / total))

    salida = []
    for i, b in enumerate(limpios):
        cp = "directa" if tipo == "publicitario" else "indirecta"
        if tipo == "sketch" and i == len(limpios) - 1 and (
            b["funcion"] == "cierre" or b["cuarta_pared"] == "indirecta_con_tag"
        ):
            cp = "indirecta_con_tag"
        salida.append({
            "tc_in": segundos_a_tiempo(cortes[i]),
            "tc_out": segundos_a_tiempo(cortes[i + 1]),
            "funcion": b["funcion"],
            "descripcion": b["descripcion"],
            "afirmaciones": b.get("afirmaciones", []),
            "espacio": b.get("espacio"),
            "cuarta_pared": cp,
        })
    return salida


def ejecutar(brief: dict, premisa: dict, persona_txt: str) -> dict:
    from .. import local

    dur = brief["forma"]["duracion_objetivo_s"]
    tipo = brief["forma"]["tipo"]

    if llm.DRY:
        datos = local.escaleta(brief, premisa)
    else:
        sistema = llm.cargar_prompt("v4_escaleta.md")
        usuario = (
            "BRIEFING OBLIGATORIO\n" + json.dumps(referencias.brief_para_modelo(brief), ensure_ascii=False) + "\n\n"
            + persona_txt + "\n"
            f"PREMISA ELEGIDA ({premisa['id']}): {premisa['proposicion']}\n"
            f"CARÁCTER: {premisa['caracter']}\n"
            f"CONFLICTO: {premisa['conflicto']}\n"
            + json.dumps(premisa, ensure_ascii=False) + "\n\n"
            + f"DURACIÓN OBJETIVO: {dur} s\n"
            f"TIPO: {tipo}\n\n"
            "Devuelve: {\"beats\": [{\"tc_in\": \"00:00\", \"tc_out\": \"00:03\", "
            "\"funcion\": \"hook\", \"descripcion\": \"\", "
            "\"cuarta_pared\": \"indirecta\", \"afirmaciones\": []}]}"
        )
        def validate(data):
            contracts.escaleta(data)
            from ..normaliza import tiempo_a_segundos
            contracts._exigir(tiempo_a_segundos(data["beats"][-1]["tc_out"]) == dur,
                              "La escaleta debe terminar en la duración objetivo.")
            for i, beat in enumerate(data["beats"]):
                allowed = {"directa"} if tipo == "publicitario" else {"indirecta"}
                if tipo == "sketch" and i == len(data["beats"]) - 1:
                    allowed.add("indirecta_con_tag")
                contracts._exigir(beat["cuarta_pared"] in allowed,
                    f"Beat {i+1}: cuarta_pared={beat['cuarta_pared']}; para {tipo} debe ser {sorted(allowed)}.")
        from copy import deepcopy
        schema = deepcopy(contracts._schema("p4_escaleta"))
        schema["properties"]["beats"]["items"]["properties"]["cuarta_pared"]["enum"] = (
            ["directa"] if tipo == "publicitario" else ["indirecta", "indirecta_con_tag"])
        crudo = llm.pedir_validado(sistema, usuario, validate, esquema=schema, seco=None, temperatura=0.4)
        datos = {"beats": crudo["beats"], "duracion_estimada_s": float(dur),
                 "cierre": crudo.get("cierre", "")}

    if not datos.get("beats"):
        raise contracts.ContratoInvalido(
            "El modelo no devolvió ninguna unidad de escaleta. Vuelve a intentarlo.")

    if llm.DRY:
        relevant = next((beat for beat in datos["beats"] if beat["funcion"] == "conflicto"),
                        datos["beats"][0])
        relevant["afirmaciones"] = premisa.get("afirmaciones", [])
    from .. import espacio
    declared = brief.get("espacio", {})
    base = espacio.construir("INT", "ESPACIO", "DÍA")
    for beat in datos["beats"]:
        if declared.get("modo") == "fijo":
            selected = declared
        else:
            selected = beat.get("espacio") or espacio.extraer_del_texto(beat["descripcion"]) or base
        if isinstance(selected, str):
            selected = espacio.extraer_del_texto(selected) or base
        if not isinstance(selected, dict):
            selected = base
        beat["espacio"] = espacio.construir(selected.get("tipo", base["tipo"]),
            selected.get("local", base["local"]), selected.get("momento", base["momento"]))
    contracts.escaleta(datos)
    return datos

