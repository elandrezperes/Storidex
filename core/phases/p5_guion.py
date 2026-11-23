"""P5 · Guion en párrafos tipados. No texto libre.

Los modelos devuelven los párrafos con nombres de tipo en inglés, en mayúsculas o
con acentos («Scene Heading», «Diálogo»). Aquí se normalizan contra la lista
cerrada de tipos permitidos. Si un párrafo no encaja en ninguno, se descarta en
lugar de romper la generación.
"""
from __future__ import annotations

import json

from .. import contracts, evidence, llm, referencias
from ..levels import peor
from ..normaliza import normalizar_tipo, tomar_campo, tomar_lista


def _normalizar_parrafos(crudos: list[dict], brief: dict | None = None,
                         escaleta: dict | None = None) -> list[dict]:
    from .. import espacio as esp_mod

    breve = brief or {}
    # espacio de referencia: el del briefing si está fijo, o el de la escaleta
    base = None
    esp_brief = breve.get("espacio") or {}
    if esp_brief.get("modo") == "fijo":
        base = {k: esp_brief[k] for k in ("tipo", "local", "momento")}
    if base is None and escaleta:
        beats = escaleta.get("beats") or []
        if beats and isinstance(beats[0].get("espacio"), dict):
            base = beats[0]["espacio"]

    salida = []
    for p in crudos:
        tipo = normalizar_tipo(tomar_campo(p, ("tipo", "type", "elemento", "elemento_tipo")))
        texto = tomar_campo(p, ("texto", "text", "contenido", "content", "value", "linea"))
        if not tipo or not texto:
            continue
        limpio = {"tipo": tipo, "texto": texto}

        if tipo == "scene_heading":
            crudo_esp = tomar_campo(p, ("espacio", "space", "setting", "escena"), None)
            esp = None
            if isinstance(crudo_esp, dict):
                esp = esp_mod.construir(
                    crudo_esp.get("tipo", "INT"),
                    crudo_esp.get("local", ""),
                    crudo_esp.get("momento", "DÍA"))
            elif isinstance(crudo_esp, str) and crudo_esp.strip():
                esp = esp_mod.extraer_del_texto(crudo_esp)
            if esp is None:
                esp = esp_mod.extraer_del_texto(texto)
            if esp is None:
                esp = dict(base) if base else None
            if esp_brief.get("modo") == "fijo":
                esp = dict(base)
            if esp:
                # el encabezado se reescribe con el formato del oficio
                prefijo = ""
                if "HOOK" in str(texto).upper():
                    prefijo = "HOOK — "
                elif "CIERRE" in str(texto).upper():
                    prefijo = "CIERRE — "
                limpio["espacio"] = esp
                limpio["texto"] = prefijo + esp_mod.encabezado(esp)

        tc = tomar_campo(p, ("tc", "timecode", "t", "time"), "")
        if tc:
            limpio["tc"] = tc
        salida.append(limpio)
    return salida


def ejecutar(brief: dict, ficha: dict, premisa: dict, escaleta: dict,
             persona_txt: str, correccion: str | None = None) -> dict:
    from .. import local

    if llm.DRY:
        datos = local.guion(brief, ficha, premisa, escaleta)
    else:
        sistema = llm.cargar_prompt("v6_guion.md")
        elenco = ", ".join(p["nombre"] for p in brief["forma"]["participantes"])
        prota = next(p["nombre"] for p in brief["forma"]["participantes"] if p["protagonico"])
        usuario = (
            "BRIEFING OBLIGATORIO\n" + json.dumps(referencias.brief_para_modelo(brief), ensure_ascii=False) + "\n\n"
            + persona_txt + "\n"
            f"MARCA: {brief['marca']['nombre']} — {brief['marca']['producto']}\n"
            f"CIUDAD: {brief['ubicacion'].get('ciudad','')}\n"
            f"PREMISA: {premisa['proposicion']}\n\n"
            "ESCALETA\n" + json.dumps(escaleta["beats"], ensure_ascii=False, indent=2) + "\n\n"
            f"ELENCO (usa estos nombres exactos): {elenco}\n"
            f"PROTAGÓNICO: {prota}\n"
            f"FRASE OBLIGATORIA TEXTUAL: {brief['forma'].get('especificaciones') or '(ninguna)'}\n"
            f"DURACIÓN: {brief['forma']['duracion_objetivo_s']} s\n"
            f"OBJETIVO: {', '.join(brief['objetivo'])}\n"
            f"TIPO: {brief['forma']['tipo']} · TONO: {brief['forma']['tono']}\n"
            f"FRASES PROHIBIDAS: {' / '.join(ficha['lenguaje']['no_diria'])}\n\n"
            "Devuelve un objeto JSON con parrafos y vinculos. Usa tipos en minúscula y con guion bajo:\n"
            '{"parrafos": [{"tipo": "scene_heading", "tc": "00:00", "texto": ""}, '
            '{"tipo": "action", "texto": ""}, {"tipo": "character", "texto": ""}, '
            '{"tipo": "parenthetical", "texto": ""}, {"tipo": "dialogue", "texto": ""}, '
            '{"tipo": "transition", "texto": ""}, {"tipo": "title", "texto": ""}], "vinculos": []}\n'
            "Tipos permitidos: scene_heading, action, character, parenthetical, "
            "dialogue, transition, title. No inventes otros."
        )
        from .. import registro
        location = brief["ubicacion"]
        usuario += "\n\n" + json.dumps({"registro_linguistico": registro.obtener(
            location.get("pais", ""), location.get("provincia", ""), location.get("ciudad", ""))},
            ensure_ascii=False)
        if correccion:
            usuario += f"\nCORRECCIÓN OBLIGATORIA DE ESTA VERSIÓN:\n{correccion}\n"

        from ..llm import MODEL_WRITE
        def validate(data):
            contracts.guion(data, brief)
            phrase = (brief["forma"].get("especificaciones") or "").strip('«»" ')
            contracts._exigir(not phrase or any(
                phrase in p["texto"] for p in data["parrafos"] if p["tipo"] == "dialogue"),
                f"La frase obligatoria debe decirse literalmente en un párrafo dialogue: {phrase}")
            from .p6_qa import comprobar_cuarta_pared
            wall = comprobar_cuarta_pared(brief, data, escaleta)
            contracts._exigir(wall["ok"], wall["requisito"])
        crudo = llm.pedir_validado(sistema, usuario,
            validate, esquema="p5_guion", modelo=MODEL_WRITE,
            seco=None, temperatura=0.35 if correccion else 0.65)
        datos = {"parrafos": crudo["parrafos"], "vinculos": crudo.get("vinculos", [])}

    datos["parrafos"] = _normalizar_parrafos(datos.get("parrafos", []), brief, escaleta)
    if not datos.get("parrafos"):
        raise contracts.ContratoInvalido(
            "El modelo no devolvió ningún párrafo de guion. Vuelve a intentarlo.")

    # normalización del elenco: mayúsculas conservando tildes
    elenco_up = {p["nombre"].upper(): p["nombre"].upper()
                 for p in brief["forma"]["participantes"]}
    for par in datos["parrafos"]:
        if par.get("tipo") == "character":
            t = par["texto"].strip().upper()
            par["texto"] = elenco_up.get(t, t)

    # fusión de bloques consecutivos del mismo personaje
    limpio = []
    for par in datos["parrafos"]:
        if (par["tipo"] == "character" and limpio
                and limpio[-1]["tipo"] == "character"
                and limpio[-1]["texto"].strip().upper() == par["texto"].strip().upper()):
            continue
        if (par["tipo"] == "character" and len(limpio) >= 2
                and limpio[-1]["tipo"] == "dialogue"
                and limpio[-2]["tipo"] == "character"
                and limpio[-2]["texto"].strip().upper() == par["texto"].strip().upper()):
            continue
        limpio.append(par)
    datos["parrafos"] = limpio

    datos.setdefault("meta", {})
    from .. import registro
    location = brief["ubicacion"]
    reg = registro.obtener(location.get("pais", ""), location.get("provincia", ""),
                           location.get("ciudad", ""))
    datos["meta"].update({
        "duracion_objetivo_s": brief["forma"]["duracion_objetivo_s"],
        "tipo": brief["forma"]["tipo"],
        "tono": brief["forma"]["tono"],
        "registro": reg["registro"],
        "tratamiento": reg["tratamiento"],
        "nivel_global": peor([ficha["confianza"]["nivel_global"], premisa.get("nivel", "T4")]),
    })

    datos["trazabilidad"] = {
        "premisa": premisa["id"],
        "razon_estrategica": premisa.get("razon_estrategica", ""),
        "referencias_creativas": premisa.get("referencias_creativas", []),
        "afirmaciones": premisa.get("afirmaciones", []),
        "vinculos": evidence.script_links(datos.pop("vinculos", []), limpio, escaleta),
    }
    contracts.guion(datos, brief)
    return datos

