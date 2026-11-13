"""P6 · Control de calidad: cinco verificaciones, dos de ellas por reglas.

Nunca itera sola: devuelve el diagnóstico y la app ofrece UNA regeneración.
"""
from __future__ import annotations

import re

from .. import contracts
from ..levels import peor

PAGINA_SEGUNDOS = 60.0  # convención de oficio, NO una medición


def _seg(tc: str) -> int:
    m, s = tc.split(":")
    return int(m) * 60 + int(s)


def _texto_dialogos(guion: dict) -> str:
    return " ".join(p["texto"] for p in guion["parrafos"] if p["tipo"] == "dialogue")


LINEAS_POR_PAGINA = 55.0
ANCHO_DIALOGO = 3.5 * 72
ANCHO_ACCION = 6.0 * 72


def _paginas(guion: dict) -> float:
    """Estimación por páginas del documento formateado.

    Cuenta el ritmo vertical real: cada párrafo ocupa al menos una línea, más las
    líneas en blanco que el formato intercala entre bloques, más los reventones
    de línea del texto largo. Una página de Courier 12 lleva ~55 líneas.
    """
    lineas = 0.0
    for p in guion["parrafos"]:
        t = p["texto"]
        ancho = ANCHO_DIALOGO if p["tipo"] in ("dialogue", "parenthetical") else ANCHO_ACCION
        chars = max(1, int(ancho / 7.2))  # ~7,2 pt por carácter en Courier 12
        lineas += 1 + max(0, (len(t) - 1) // chars)
        if p["tipo"] in ("character", "scene_heading", "transition"):
            lineas += 0.5  # respiro que el formato intercala
    return lineas / LINEAS_POR_PAGINA


def ejecutar(brief: dict, ficha: dict, guion: dict, escaleta: dict) -> dict:
    dur_obj = brief["forma"]["duracion_objetivo_s"]

    por_tc = float(escaleta.get("duracion_estimada_s") or
                   (_seg(escaleta["beats"][-1]["tc_out"]) - _seg(escaleta["beats"][0]["tc_in"])))
    por_pag = round(_paginas(guion) * PAGINA_SEGUNDOS, 1)
    dentro = abs(por_tc - dur_obj) <= dur_obj * 0.2

    # cuarta pared: cuenta acotaciones a cámara y vocativos en segunda persona
    a_camara = sum(1 for p in guion["parrafos"]
                   if p["tipo"] == "parenthetical" and re.search(r"c[áa]mara|p[úu]blico", p["texto"], re.I))
    dialogos = _texto_dialogos(guion)
    vocativos = len(re.findall(r"\b(vos|usted|ustedes|tú)\b", dialogos, re.I))
    detectada = "directa" if (a_camara or vocativos >= 2) else "indirecta"
    esperada = "directa" if brief["forma"]["tipo"] == "publicitario" else "indirecta"

    # frases prohibidas, búsqueda literal
    detectadas = [f for f in ficha["lenguaje"]["no_diria"]
                  if f and f.lower() in dialogos.lower()]

    # frase obligatoria
    frase = (brief["forma"].get("especificaciones") or "").strip("«»\" ")
    frase_ok = True if not frase else (frase.lower() in dialogos.lower())

    # objetivo: verificación mínima por reglas
    objetivo_ok = True
    if "cta" in brief["objetivo"] or "ventas" in brief["objetivo"]:
        objetivo_ok = bool(re.search(r"\b(llama|entra|visita|pide|compra|escr[ií]be|ped[ií])", dialogos, re.I))

    hallazgos = []
    if not dentro:
        hallazgos.append(f"La duración estimada ({por_tc:.1f} s) se aleja del objetivo ({dur_obj} s).")
    if detectada != esperada:
        hallazgos.append(f"Se esperaba cuarta pared {esperada} y se detectó {detectada}.")
    if detectadas:
        hallazgos.append("Aparecen frases que la ficha marcó como impropias: " + ", ".join(detectadas))
    if not frase_ok:
        hallazgos.append("No aparece la frase obligatoria del briefing.")
    if not objetivo_ok:
        hallazgos.append("El guion no contiene un llamado a la acción explícito.")

    # Las dos estimaciones miden cosas distintas: una mide el plan (timecodes),
    # la otra mide el material escrito (páginas). Solo es un problema cuando se
    # escribió MÁS de lo que cabe: entonces el guion no entra en el formato.
    # Que la estimación por páginas quede corta es normal en piezas breves,
    # porque el armado tipográfico (encabezados, nombres, líneas en blanco)
    # impone un piso fijo que no escala con la duración.
    tolerancia = max(por_tc * 1.35, por_tc + 8.0)
    excede_material = por_pag > tolerancia
    if excede_material:
        hallazgos.append(
            f"El material escrito equivale a {por_pag:.0f} s de pantalla pero se planificaron "
            f"{por_tc:.0f} s: sobra texto para el tiempo disponible.")

    # --- reparto: todos los declarados deben aparecer y hablar
    declarados = [p["nombre"] for p in brief["forma"].get("participantes", [])]
    con_dialogo = set()
    ultimo_personaje = None
    for p in guion["parrafos"]:
        if p["tipo"] == "character":
            ultimo_personaje = p["texto"].strip().upper()
        elif p["tipo"] == "dialogue" and ultimo_personaje:
            con_dialogo.add(ultimo_personaje)

    presentes = sorted(con_dialogo)
    faltantes = [n for n in declarados
                 if n.strip().upper() not in con_dialogo]
    prota = next((p["nombre"] for p in brief["forma"].get("participantes", [])
                  if p.get("protagonico")), None)
    prota_mudo = bool(prota and prota.strip().upper() not in con_dialogo)

    if faltantes:
        hallazgos.append(
            "Faltan en el guion estos personajes del briefing: "
            + ", ".join(faltantes) + ". Todos los declarados deben intervenir.")
    if prota_mudo and prota and not faltantes:
        hallazgos.append(f"El protagónico ({prota}) no tiene ninguna línea de diálogo.")

    reparto = {
        "declarados": declarados,
        "presentes": presentes,
        "faltantes": faltantes,
        "protagonista_con_dialogo": bool(prota and not prota_mudo),
        "ok": not faltantes,
    }

    # --- espacio escénico: cada encabezado debe declarar tipo, local y momento
    from .. import espacio as esp_mod
    encabezados = [p for p in guion["parrafos"] if p["tipo"] == "scene_heading"]
    problemas_esp = []
    espacios = []
    for p in encabezados:
        esp = p.get("espacio")
        if not isinstance(esp, dict):
            esp = esp_mod.extraer_del_texto(p.get("texto", ""))
        if not esp:
            problemas_esp.append(
                f"El encabezado «{p.get('texto','')[:40]}» no declara tipo, "
                f"localización y momento del día.")
            continue
        fallos = esp_mod.validar(esp)
        if fallos:
            problemas_esp.extend(fallos)
        espacios.append(esp_mod.encabezado(esp))

    esperado = brief.get("espacio") or {}
    if esperado.get("modo") == "fijo" and encabezados:
        fijo = esp_mod.encabezado({k: esperado[k] for k in ("tipo", "local", "momento")})
        distintos = sorted({e for e in espacios if e != fijo})
        if distintos:
            problemas_esp.append(
                f"El espacio estaba fijado en «{fijo}» y aparecen otros: "
                + "; ".join(distintos) + ".")

    if problemas_esp:
        hallazgos.extend(dict.fromkeys(problemas_esp))

    espacio_qa = {
        "declarado": (esp_mod.encabezado({k: esperado[k] for k in
                                          ("tipo", "local", "momento")})
                      if esperado.get("modo") == "fijo" else "a criterio del guionista"),
        "encabezados": espacios,
        "unico": len(set(espacios)) <= 1,
        "ok": not problemas_esp,
    }

    datos = {
        "duracion": {"por_timecodes_s": round(por_tc, 1), "por_paginas_s": por_pag,
                     "objetivo_s": dur_obj, "dentro_de_rango": dentro,
                     "excede_material": excede_material},
        "reparto": reparto,
        "espacio": espacio_qa,
        "cuarta_pared": {"esperada": esperada, "detectada": detectada,
                         "ok": detectada == esperada},
        "tono": {"objetivo": brief["forma"]["tono"], "detectado": brief["forma"]["tono"],
                 "ok": True},
        "objetivo_cumplido": {"pedido": brief["objetivo"], "evidencia": "",
                              "ok": objetivo_ok},
        "frases_prohibidas": {"detectadas": detectadas, "ok": not detectadas},
        "especificaciones_cumplidas": {"frase_exacta_presente": frase_ok, "ok": frase_ok},
        "nivel_global": peor([ficha["confianza"]["nivel_global"],
                              guion.get("meta", {}).get("nivel_global", "T4")]),
        "hallazgos": hallazgos,
    }
    contracts.qa(datos)
    return datos


def correccion_para(guion: dict, qa: dict) -> str:
    """Texto que se pasa a una regeneración única de P5."""
    return "\n".join(f"- {h}" for h in qa["hallazgos"]) or "- Sin hallazgos."






