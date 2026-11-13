"""P4 · Escaleta con códigos de tiempo. El gancho nunca pasa de 3 s.

El modelo no devuelve los códigos de tiempo de forma fiable, así que se
reconstruyen aquí a partir de las duraciones relativas. Es más robusto y además
garantiza que cumplan el contrato: contiguos, sin huecos y terminando en la
duración objetivo.
"""
from __future__ import annotations

import json

from .. import contracts, llm
from ..normaliza import (normalizar_funcion, segundos_a_tiempo, tiempo_a_segundos,
                         tomar_campo, tomar_lista)

# peso de cada función en el reparto del tiempo
PESOS = {"hook": 0.10, "planteamiento": 0.22, "conflicto": 0.28,
         "giro": 0.12, "desenlace": 0.20, "cta": 0.08, "cierre": 0.06}


def _reconstruir(beats: list[dict], duracion: int, tipo: str,
                 brief: dict | None = None) -> list[dict]:
    """Asigna códigos de tiempo contiguos y espacio a cada unidad."""
    from .. import espacio as esp_mod
    from .. import local

    breve = brief or {}
    esp_declarado = breve.get("espacio") or {"modo": "auto"}
    if esp_declarado.get("modo") == "fijo":
        base = {k: esp_declarado[k] for k in ("tipo", "local", "momento")}
    else:
        rubro = local.clasificar(breve.get("marca", {}).get("producto", ""),
                                 breve.get("marca", {}).get("nombre", ""))
        base = esp_mod.sugerido(rubro, breve.get("ubicacion", {}).get("ciudad", ""))

    limpios = []
    for b in beats:
        funcion = normalizar_funcion(tomar_campo(b, ("funcion", "function", "tipo", "beats")))
        crudo_esp = tomar_campo(b, ("espacio", "space", "escena", "setting", "lugar"), None)
        if isinstance(crudo_esp, dict):
            esp = esp_mod.construir(
                crudo_esp.get("tipo", base["tipo"]),
                crudo_esp.get("local", base["local"]),
                crudo_esp.get("momento", base["momento"]))
        elif isinstance(crudo_esp, str) and crudo_esp.strip():
            esp = esp_mod.extraer_del_texto(crudo_esp) or dict(base)
        else:
            # el modelo no declaró espacio: se busca dentro del texto libre
            textos = " ".join(str(v) for v in b.values() if isinstance(v, str))
            esp = esp_mod.extraer_del_texto(textos) or dict(base)

        limpios.append({
            "funcion": funcion,
            "descripcion": tomar_campo(
                b, ("descripcion", "description", "texto", "text", "accion", "acción"),
                ""),
            "espacio": esp,
            "cuarta_pared": tomar_campo(b, ("cuarta_pared", "fourth_wall"), ""),
        })

    if not limpios:
        return []

    # el primer beat siempre es el gancho, y nunca pasa de 3 segundos
    if limpios[0]["funcion"] != "hook":
        limpios.insert(0, {"funcion": "hook", "descripcion": "",
                           "espacio": dict(base), "cuarta_pared": ""})

    hook = min(3, max(2, duracion // 8))
    resto = max(duracion - hook, 1)

    # se reparte el resto según el peso de cada función
    pesos = [PESOS.get(b["funcion"], 0.15) for b in limpios[1:]] or [1.0]
    total = sum(pesos)

    cortes = [0, hook]
    acumulado = hook
    for peso in pesos[:-1]:
        acumulado += max(1, round(resto * peso / total))
        cortes.append(min(acumulado, duracion - 1))
    cortes.append(duracion)

    # se eliminan duplicados y se garantiza el orden
    cortes = sorted(set(cortes))
    while len(cortes) < len(limpios) + 1:
        cortes.insert(-1, cortes[-1] - 1 if cortes[-1] > 1 else cortes[-1])
    cortes = cortes[:len(limpios) + 1]

    salida = []
    for i, b in enumerate(limpios):
        if i >= len(cortes) - 1:
            break
        cp = b["cuarta_pared"]
        if cp not in ("directa", "indirecta", "indirecta_con_tag"):
            cp = "directa" if tipo == "publicitario" else "indirecta"
        if b["funcion"] == "cierre" and tipo == "sketch" and cp == "indirecta":
            cp = "indirecta_con_tag"
        salida.append({
            "tc_in": segundos_a_tiempo(cortes[i]),
            "tc_out": segundos_a_tiempo(cortes[i + 1]),
            "funcion": b["funcion"],
            "descripcion": b["descripcion"],
            "espacio": b["espacio"],
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
        sistema = llm.cargar_prompt("v1_escaleta.md")
        espacio_txt = _bloque_espacio(brief)
        usuario = (
            persona_txt + "\n"
            f"PREMISA ELEGIDA ({premisa['id']}): {premisa['proposicion']}\n"
            f"CARÁCTER: {premisa['caracter']}\n"
            f"CONFLICTO: {premisa['conflicto']}\n"
            f"DESENLACE: {premisa['desenlace']}\n\n"
            f"DURACIÓN OBJETIVO: {dur} s\n"
            f"TIPO: {tipo}\n\n"
            + espacio_txt + "\n"
            "Cada unidad debe declarar su espacio con los tres componentes "
            "(tipo, local, momento).\n\n"
            "Devuelve: {\"beats\": [{\"tc_in\": \"00:00\", \"tc_out\": \"00:03\", "
            "\"funcion\": \"hook\", \"descripcion\": \"\", "
            "\"espacio\": {\"tipo\": \"INT\", \"local\": \"\", \"momento\": \"DÍA\"}, "
            "\"cuarta_pared\": \"indirecta\"}]}"
        )
        r = llm.pedir_json(sistema, usuario, seco=None, temperatura=0.4)
        crudo = llm.parsear(r, "la escaleta")
        beats = tomar_lista(crudo, ("beats", "escaleta", "unidades", "structure",
                                    "secuencia", "scenes"))
        datos = {
            "beats": _reconstruir(beats, dur, tipo, brief),
            "duracion_estimada_s": float(dur),
            "cierre": "Rótulo de marca",
        }

    if not datos.get("beats"):
        raise contracts.ContratoInvalido(
            "El modelo no devolvió ninguna unidad de escaleta. Vuelve a intentarlo.")

    # todas las unidades comparten el espacio declarado, si el usuario lo fijó
    if brief.get("espacio", {}).get("modo") == "fijo":
        fijo = {k: brief["espacio"][k] for k in ("tipo", "local", "momento")}
        for b in datos["beats"]:
            b["espacio"] = dict(fijo)

    contracts.escaleta(datos)
    return datos


def _bloque_espacio(brief: dict) -> str:
    from .. import espacio as esp_mod
    from .. import local

    esp = brief.get("espacio") or {"modo": "auto"}
    if esp.get("modo") == "fijo":
        return esp_mod.bloque_prompt(
            {k: esp[k] for k in ("tipo", "local", "momento")}, "fijo")

    rubro = local.clasificar(brief["marca"].get("producto", ""),
                             brief["marca"].get("nombre", ""))
    sugerido = esp_mod.sugerido(rubro, brief["ubicacion"].get("ciudad", ""))
    return esp_mod.bloque_prompt(sugerido, "auto") + (
        f"Sugerencia para este rubro: {esp_mod.encabezado(sugerido)} "
        "(puedes cambiarla si otra localización cuenta mejor la historia).\n")






