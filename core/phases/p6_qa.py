"""P6 · Control de calidad: cinco verificaciones, dos de ellas por reglas.

Nunca itera sola: devuelve el diagnóstico y la app ofrece UNA regeneración.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from .. import contracts, referencias
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

    por_tc = sum(_seg(beat["tc_out"]) - _seg(beat["tc_in"]) for beat in escaleta["beats"])
    por_pag = round(_paginas(guion) * PAGINA_SEGUNDOS, 1)
    dentro = abs(por_tc - dur_obj) <= dur_obj * 0.2

    # Los pronombres de segunda persona también aparecen en diálogos entre personajes.
    wall = comprobar_cuarta_pared(brief, guion, escaleta)
    esperada = "directa" if brief["forma"]["tipo"] == "publicitario" else "indirecta"
    detectada = (
        "indirecta_con_tag" if wall["ok"] and wall["indicacion_a_camara"] and esperada == "indirecta"
        else "directa" if wall["indicacion_a_camara"] else "indirecta"
    )
    dialogos = _texto_dialogos(guion)

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
    if not wall["ok"]:
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

    avisos_estimacion = []
    if abs(por_pag - por_tc) > 0.15 * por_tc:
        avisos_estimacion.append(
            "Las dos estimaciones difieren en más del 15 %. Revisa el ritmo con una lectura o animatic."
        )

    espacio_qa = None
    if "espacio" in brief:
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
        "realizabilidad": {
            "recursos_declarados": brief["forma"].get("recursos", ""),
        },
        "avisos_estimacion": avisos_estimacion,
        "revision_con_evidencia": None,
        "revision_creativa": {
            "guias": ["TikTok Creative Codes", "Google ABCD"],
            "criterios": ["gancho", "mensaje_unico", "beneficio_visible", "cierre"],
            "estado": "pendiente",
        },
        "duracion": {"por_timecodes_s": round(por_tc, 1), "por_paginas_s": por_pag,
                     "objetivo_s": dur_obj, "dentro_de_rango": dentro,
                     "excede_material": excede_material},
        "cuarta_pared": {"esperada": esperada, "detectada": detectada,
                         "ok": wall["ok"]},
        "tono": {"objetivo": brief["forma"]["tono"], "detectado": None, "ok": None},
        "objetivo_cumplido": {"pedido": brief["objetivo"], "evidencia": "",
                              "ok": objetivo_ok},
        "frases_prohibidas": {"detectadas": detectadas, "ok": not detectadas},
        "especificaciones_cumplidas": {"frase_exacta_presente": frase_ok, "ok": frase_ok},
        "nivel_global": peor([ficha["confianza"]["nivel_global"],
                              guion.get("meta", {}).get("nivel_global", "T4")]),
        "hallazgos": hallazgos,
    }
    if espacio_qa is not None:
        datos["espacio"] = espacio_qa
    contracts.qa(datos)
    return datos


def correccion_para(guion: dict, qa: dict) -> str:
    """Texto que se pasa a una regeneración única de P5."""
    return "\n".join(f"- {h}" for h in qa["hallazgos"]) or "- Sin hallazgos."





CRITERIOS = (
    "marca_producto", "mensaje", "publico", "tono", "formato",
    "elenco_protagonismo", "objetivos", "indicaciones", "ritmo",
)


def comprobar_cuarta_pared(brief, guion, escaleta):
    beats = escaleta["beats"]
    direct = brief["forma"].get("tipo") == "publicitario"
    walls = [b.get("cuarta_pared") for b in beats]
    expected_walls = {"directa"} if direct else {"indirecta"}
    format_ok = all(w in expected_walls for w in walls[:-1]) and (
        walls[-1] in (expected_walls if direct else expected_walls | {"indirecta_con_tag"})
    )
    camera_pattern = re.compile(
        r"\b(?:a (?:la )?c[áa]mara|al p[úu]blico|"
        r"(?:mira|habla|se dirige) (?:directamente )?al lente)\b", re.I
    )
    negated_cue = re.compile(
        r"\b(?:no|sin|nunca|jamás|jamas|evita(?:n|r)?)\s+(?:se\s+)?"
        r"(?:(?:mir\w*|habl\w*|dirig\w*)\s+)?(?:directamente\s+)?$", re.I
    )
    camera_cues = []
    scene = None
    for p in guion["parrafos"]:
        if p["tipo"] == "scene_heading":
            scene = p.get("tc")
        if p["tipo"] in {"parenthetical", "action"} and any(
            not negated_cue.search(p["texto"][:match.start()])
            for match in camera_pattern.finditer(p["texto"])
        ):
            camera_cues.append(p.get("tc") or scene)
    cue_ok = bool(camera_cues) if direct else not camera_cues or (
        len(camera_cues) == 1
        and walls[-1] == "indirecta_con_tag"
        and camera_cues[0] == beats[-1]["tc_in"]
    )
    return {
        "ok": format_ok and cue_ok,
        "escaleta_coherente": format_ok,
        "indicacion_a_camara": bool(camera_cues),
        "requisito": ("Indica explícitamente que el personaje habla a cámara."
                      if direct else "Limita el aparte al último beat autorizado."),
    }


def lista_brief(brief: dict, guion: dict, escaleta: dict) -> dict:
    """Comprobaciones reproducibles independientes de los metadatos del modelo."""
    forma = brief["forma"]
    paragraphs = guion["parrafos"]
    cast = {p["nombre"].strip().casefold() for p in forma["participantes"]}
    speakers = {p["texto"].strip().casefold() for p in paragraphs if p["tipo"] == "character"}
    actions = " ".join(p["texto"] for p in paragraphs if p["tipo"] == "action").casefold()
    missing = sorted(name for name in cast - speakers
                     if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", actions))
    beats = escaleta["beats"]
    windows = [(_seg(b["tc_in"]), _seg(b["tc_out"])) for b in beats]
    target = forma["duracion_objetivo_s"]
    starts = {b["tc_in"] for b in beats}
    headings = [p.get("tc") for p in paragraphs if p["tipo"] == "scene_heading"]
    visible = " ".join(p["texto"] for p in paragraphs if p["tipo"] in {"dialogue", "title", "action"})
    phrase = (forma.get("especificaciones") or "").strip("«»\" ")
    return {
        "elenco": {"ok": not missing and speakers <= cast,
                   "faltantes": missing, "fuera_del_elenco": sorted(speakers - cast)},
        "tiempos": {"ok": windows[0][0] == 0 and windows[-1][1] == target
                    and all(a < b for a, b in windows)
                    and all(a[1] == b[0] for a, b in zip(windows, windows[1:]))
                    and beats[0]["funcion"] == "hook" and windows[0][1] <= 3
                    and bool(headings) and headings[0] == beats[0]["tc_in"]
                    and all(tc in starts for tc in headings)
                    and headings == sorted(headings)},
        "formato": comprobar_cuarta_pared(brief, guion, escaleta),
        "marca": {"ok": brief["marca"]["nombre"].casefold() in visible.casefold()},
        "frase_exacta": {"ok": not phrase or any(
            phrase in p["texto"] for p in paragraphs if p["tipo"] == "dialogue")},
    }


def revisar_brief(brief, persona, guion, escaleta):
    from .. import llm
    import json

    result = ejecutar(brief, persona, guion, escaleta)
    checks = lista_brief(brief, guion, escaleta)
    result["lista_brief"] = checks
    # Estas heurísticas se conservan como diagnóstico. P6 verifica el formato
    # con la lista y evalúa la intención del CTA y el ritmo con evidencia.
    heuristics = ("Se esperaba cuarta pared", "El material escrito equivale",
                  "El guion no contiene un llamado a la acción explícito")
    result["avisos"] = [item for item in result["hallazgos"] if item.startswith(heuristics)]
    result["hallazgos"] = [item for item in result["hallazgos"] if not item.startswith(heuristics)]
    result["cuarta_pared"]["ok"] = checks["formato"]["ok"]
    result["hallazgos"].extend(
        f"Incumplimiento de {key}. {json.dumps(value, ensure_ascii=False)}"
        for key, value in checks.items() if not value["ok"]
    )
    if llm.DRY or result["hallazgos"]:
        result["revision_con_evidencia"] = None
        return result
    response = llm.pedir_json(
        llm.cargar_prompt("v4_revision_brief.md"),
        json.dumps({"brief": referencias.brief_para_modelo(brief), "escaleta": escaleta, "parrafos": guion["parrafos"],
                    "referencias_creativas": guion.get("trazabilidad", {}).get("referencias_creativas", [])},
                   ensure_ascii=False),
        temperatura=0,
    )
    audit = llm.parsear(response, "la revisión del briefing")
    result["revision_con_evidencia"] = audit
    for criterion, summary in (("objetivos", "objetivo_cumplido"), ("tono", "tono")):
        entry = audit.get(criterion)
        if isinstance(entry, dict):
            result[summary].update(
                ok=entry.get("ok") if isinstance(entry.get("ok"), bool) else None,
                evidencia=entry.get("evidencia", ""), metodo="revision_modelo",
            )
    advice = audit.get("revision_creativa")
    if isinstance(advice, dict):
        creative = result["revision_creativa"]
        findings = {k: advice[k].strip() for k in creative["criterios"]
                    if isinstance(advice.get(k), str) and advice[k].strip()}
        if findings:
            creative.update(estado="orientativa", alertas=findings)
    resources = audit.get("recursos")
    if isinstance(resources, dict) and isinstance(resources.get("evidencia"), str):
        result["realizabilidad"]["alerta_modelo"] = resources["evidencia"]
    for key in CRITERIOS:
        entry = audit.get(key)
        if (not isinstance(entry, dict) or entry.get("ok") is not True
                or not isinstance(entry.get("evidencia"), str) or not entry["evidencia"].strip()):
            evidence = entry.get("evidencia", "") if isinstance(entry, dict) else ""
            result["hallazgos"].append(f"Verificar {key}. {evidence}")
    return result


def revision_humana(data, persona):
    """Valida un dictamen sobre una afirmación o un ensayo de duración."""
    reviewer = data.get("revisor")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise contracts.ContratoInvalido("Identifica a quien realizó la revisión.")
    review = {"revisor": reviewer.strip(), "fecha": datetime.now(timezone.utc).isoformat()}
    field = data.get("afirmacion")
    if field:
        if not isinstance(field, str) or field not in persona.get("afirmaciones", {}):
            raise contracts.ContratoInvalido("Elige una afirmación de la ficha.")
        decision = data.get("decision")
        note = data.get("nota", "")
        if (decision not in ("aceptada", "corregida", "retirada")
                or not isinstance(note, str)
                or decision == "corregida" and not note.strip()):
            raise contracts.ContratoInvalido("Elige un dictamen y escribe la corrección si corresponde.")
        review.update(afirmacion=field, decision=decision, nota=note.strip())
    else:
        method = data.get("metodo")
        seconds = data.get("segundos")
        if (method not in ("lectura", "animatic") or type(seconds) not in (int, float)
                or not 0 < seconds <= 3600):
            raise contracts.ContratoInvalido("Registra el método y una duración válida del ensayo.")
        review.update(metodo=method, segundos=seconds)
    return review
