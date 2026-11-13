"""P5 · Guion en párrafos tipados. No texto libre.

Los modelos devuelven los párrafos con nombres de tipo en inglés, en mayúsculas o
con acentos («Scene Heading», «Diálogo»). Aquí se normalizan contra la lista
cerrada de tipos permitidos. Si un párrafo no encaja en ninguno, se descarta en
lugar de romper la generación.
"""
from __future__ import annotations

import json

from .. import contracts, llm
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


def _faltantes(parrafos: list[dict], declarados: list[str]) -> list[str]:
    """Personajes del briefing que no tienen ninguna línea en el guion."""
    presentes = {p["texto"].strip().upper()
                 for p in parrafos if p.get("tipo") == "character"}
    return [n for n in declarados if n.strip().upper() not in presentes]


def _prompt(brief: dict, ficha: dict, premisa: dict, escaleta: dict,
            persona_txt: str, declarados: list[str], prota: str,
            correccion: str | None = None, refuerzo: str | None = None) -> str:
    """Instrucción de P5. Reparto, registro y no-invención son reglas duras."""
    from .. import registro as reg_mod

    elenco_lineas = "\n".join(
        f"- {p['nombre']}" + ("  ← PROTAGÓNICO" if p["protagonico"] else "")
        for p in brief["forma"]["participantes"])

    ubi = brief["ubicacion"]
    reg = reg_mod.obtener(ubi.get("pais", ""), ubi.get("provincia", ""),
                          ubi.get("ciudad", ""))
    bloque_registro = reg_mod.bloque_prompt(reg, brief["forma"]["tono"])

    datos_utiles = {
        "marca": brief["marca"]["nombre"],
        "producto": brief["marca"]["producto"],
        "ciudad": ubi.get("ciudad", ""),
        "frase obligatoria": brief["forma"].get("especificaciones") or "(ninguna)",
        "indicaciones": brief["forma"].get("indicaciones") or "(ninguna)",
    }

    texto = (
        persona_txt + "\n"
        f"MARCA: {brief['marca']['nombre']} — {brief['marca']['producto']}\n"
        f"UBICACIÓN: {ubi.get('ciudad','')}, {ubi.get('provincia','')}, {ubi.get('pais','')}\n"
        f"PREMISA: {premisa['proposicion']}\n\n"
        "ESCALETA\n" + json.dumps(escaleta["beats"], ensure_ascii=False, indent=2) + "\n\n"
        f"ELENCO OBLIGATORIO ({len(declarados)} personajes)\n{elenco_lineas}\n"
        f"Protagónico: {prota}\n\n"
        "REGLA DURA DEL REPARTO: cada personaje de la lista debe aparecer con su "
        "encabezado `character` y al menos UNA línea de `dialogue`. No omitas a "
        "ninguno, aunque tenga una sola frase. No inventes personajes que no estén "
        "en la lista.\n\n"
        + bloque_registro + "\n"
        f"FRASE OBLIGATORIA TEXTUAL: {brief['forma'].get('especificaciones') or '(ninguna)'}\n"
        f"DURACIÓN: {brief['forma']['duracion_objetivo_s']} s\n"
        f"OBJETIVO: {', '.join(brief['objetivo'])}\n"
        f"TIPO: {brief['forma']['tipo']} · TONO: {brief['forma']['tono']}\n"
        f"FRASES PROHIBIDAS: {' / '.join(ficha['lenguaje']['no_diria'])}\n\n"
        "REGLA DE NO INVENCIÓN: no agregues ningún dato que no esté en el briefing. "
        "Prohibido inventar precios, descuentos, horarios, direcciones, teléfonos, "
        "años de trayectoria, cifras de clientes o promesas comerciales "
        "(«gratis», «2x1», «envío sin costo», porcentajes). Si el briefing no lo dice, "
        "el guion no lo dice.\n"
        "Datos disponibles, y nada más que estos:\n"
        + "\n".join(f"- {k}: {v}" for k, v in datos_utiles.items()) + "\n\n"
        "Devuelve SOLO este JSON, con los tipos en minúscula y con guion bajo:\n"
        '{"parrafos": [{"tipo": "scene_heading", "tc": "00:00", "texto": ""}, '
        '{"tipo": "action", "texto": ""}, {"tipo": "character", "texto": ""}, '
        '{"tipo": "parenthetical", "texto": ""}, {"tipo": "dialogue", "texto": ""}, '
        '{"tipo": "transition", "texto": ""}, {"tipo": "title", "texto": ""}]}\n'
        "Tipos permitidos: scene_heading, action, character, parenthetical, "
        "dialogue, transition, title. No inventes otros."
    )
    if refuerzo:
        texto += f"\n\nATENCIÓN: {refuerzo}\n"
    if correccion:
        texto += f"\nCORRECCIÓN OBLIGATORIA DE ESTA VERSIÓN:\n{correccion}\n"
    return texto


def ejecutar(brief: dict, ficha: dict, premisa: dict, escaleta: dict,
             persona_txt: str, correccion: str | None = None) -> dict:
    from .. import local

    declarados = [p["nombre"] for p in brief["forma"]["participantes"]]
    prota = next(p["nombre"] for p in brief["forma"]["participantes"] if p["protagonico"])

    if llm.DRY:
        datos = local.guion(brief, ficha, premisa, escaleta)
    else:
        sistema = llm.cargar_prompt("v1_guion.md")
        usuario = _prompt(brief, ficha, premisa, escaleta, persona_txt,
                          declarados, prota, correccion)
        from ..llm import MODEL_WRITE
        r = llm.pedir_json(sistema, usuario, modelo=MODEL_WRITE,
                           seco=local.guion(brief, ficha, premisa, escaleta) if llm.DRY else None,
                           temperatura=0.8)
        datos = {"parrafos": _normalizar_parrafos(
            tomar_lista(llm.parsear(r, "el guion"),
                        ("parrafos", "paragraphs", "guion", "script", "elementos", "lines")),
            brief, escaleta)}

        # si el modelo se olvidó de alguien del elenco, se le pide una vez más
        faltan = _faltantes(datos["parrafos"], declarados)
        if faltan:
            usuario2 = _prompt(brief, ficha, premisa, escaleta, persona_txt,
                               declarados, prota, correccion,
                               refuerzo=(f"En tu versión anterior NO aparecen estos "
                                         f"personajes: {', '.join(faltan)}. Todos los "
                                         f"declarados deben intervenir al menos una vez, "
                                         f"con su propia línea de diálogo."))
            try:
                r2 = llm.pedir_json(sistema, usuario2, modelo=MODEL_WRITE,
                                    temperatura=0.7)
                datos2 = {"parrafos": _normalizar_parrafos(
                    tomar_lista(llm.parsear(r2, "el guion"),
                                ("parrafos", "paragraphs", "guion", "script",
                                 "elementos", "lines")),
                    brief, escaleta)}
                if len(_faltantes(datos2["parrafos"], declarados)) < len(faltan):
                    datos = datos2
            except Exception:  # noqa: BLE001
                pass  # se conserva la primera versión; P6 lo reportará

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
    from .. import registro as reg_mod
    ubi = brief["ubicacion"]
    reg = reg_mod.obtener(ubi.get("pais", ""), ubi.get("provincia", ""),
                          ubi.get("ciudad", ""))
    datos["meta"].update({
        "duracion_objetivo_s": brief["forma"]["duracion_objetivo_s"],
        "tipo": brief["forma"]["tipo"],
        "tono": brief["forma"]["tono"],
        "registro": reg["registro"],
        "tratamiento": reg["tratamiento"],
        "nivel_global": peor([ficha["confianza"]["nivel_global"], premisa.get("nivel", "T4")]),
    })

    contracts.guion(datos, brief)
    return datos






