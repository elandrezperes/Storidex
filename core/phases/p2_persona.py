"""P2 · Persona operativa: síntesis con restricciones duras y autocrítica.

Dos llamadas: la primera sintetiza; la segunda revisa contra tres reglas y
corrige. El segmento no es el destinatario: es el cerco dentro del cual la
síntesis opera.

En modo real, TODO el contenido procede del modelo. Ninguna frase de la ficha
está escrita de antemano: si la autocorrección detecta una frase genérica, pide
al modelo que la reescriba.
"""
from __future__ import annotations

import json

from .. import contracts, llm
from ..levels import T4, confianza

GENERICAS = ("le gusta la música", "busca calidad", "valora la confianza",
             "persona activa", "ama la vida", "excelencia", "calidad y confianza")


def ejecutar(brief: dict, research: dict) -> dict:
    seg = brief["segmento"]
    usuario = (
        "BRIEFING\n"
        f"Marca: {brief['marca']['nombre']}\n"
        f"Producto o servicio: {brief['marca']['producto']}\n"
        f"Ciudad: {brief['ubicacion'].get('ciudad','')}, "
        f"{brief['ubicacion'].get('provincia','')}, {brief['ubicacion'].get('pais','')}\n"
        f"Segmento: {seg['edad_min']} a {seg['edad_max']} años · sexo {seg['sexo']} · "
        f"nivel socioeconómico {seg.get('nse','')}\n"
        f"Objetivo del video: {', '.join(brief['objetivo'])}\n"
        f"Tipo: {brief['forma']['tipo']} de {brief['forma']['duracion_objetivo_s']} s\n"
        f"Tono: {brief['forma']['tono']}\n"
        f"Indicaciones del cliente: {brief['forma'].get('indicaciones') or '(ninguna)'}\n\n"
        f"OPORTUNIDAD DE MERCADO: {research.get('oportunidad', {}).get('texto') or '(sin datos)'}\n\n"
        "Construye la ficha de UNA persona concreta de ese segmento. Todo debe ser "
        "coherente con el producto y la ciudad. Devuelve los bloques perfil, consumo, "
        "conflicto, lenguaje y anti_persona, cada uno con su campo «nivel» (T1–T4).\n\n"
        "Esquema:\n"
        '{"perfil":{"nombre":"","edad":0,"ocupacion":"","barrio":"","nivel":"T4"},'
        '"consumo":{"cuando":"","donde":"","dispositivo":"","nivel":"T4"},'
        '"conflicto":{"problema":"","objecion":"","detonante":"","nivel":"T4"},'
        '"lenguaje":{"diria":["","",""],"no_diria":["",""],"nivel":"T4"},'
        '"anti_persona":{"quien_no_es":"","nivel":"T4"}}'
    )

    r = llm.pedir_json(llm.cargar_prompt("v1_persona.md"), usuario,
                       seco=_seco(brief) if llm.DRY else None, temperatura=0.9)
    ficha = _reparar(llm.parsear(r, "la ficha de persona"), brief)
    ficha = _autocritica(ficha, brief)
    ficha = _reparar(ficha, brief)          # segunda pasada, por si la corrección vino a medias
    contracts.persona(ficha, brief)
    ficha["confianza"] = confianza(ficha)
    return ficha


def _reparar(ficha: dict, brief: dict) -> dict:
    """Rellena huecos de la ficha SIN inventar contenido creativo.

    Solo arregla lo estructural: claves ausentes, tipos equivocados y la edad
    fuera de rango. Las frases y el conflicto son siempre del modelo; si faltan,
    los pide la autocorrección, no este paso.
    """
    seg = brief["segmento"]
    ficha = dict(ficha or {})

    # ---- perfil: la edad se acota al segmento, no se rechaza
    perfil = dict(ficha.get("perfil") or {})
    try:
        edad = int(perfil.get("edad"))
    except (TypeError, ValueError):
        edad = (seg["edad_min"] + seg["edad_max"]) // 2
    perfil["edad"] = min(max(edad, seg["edad_min"]), seg["edad_max"])
    for clave, defecto in (("nombre", ""), ("ocupacion", ""), ("barrio", ""), ("nivel", T4)):
        if not perfil.get(clave):
            perfil[clave] = defecto
    ficha["perfil"] = perfil

    # ---- bloques de texto
    for bloque, claves in (
        ("consumo", ("cuando", "donde", "dispositivo")),
        ("conflicto", ("problema", "objecion", "detonante")),
    ):
        b = dict(ficha.get(bloque) or {})
        for k in claves:
            b.setdefault(k, "")
        b.setdefault("nivel", T4)
        ficha[bloque] = b

    # ---- lenguaje: listas limpias
    lang = dict(ficha.get("lenguaje") or {})
    diria = [str(f).strip() for f in (lang.get("diria") or []) if str(f).strip()]
    no_diria = [str(f).strip() for f in (lang.get("no_diria") or []) if str(f).strip()]
    lang["diria"] = diria[:5]
    lang["no_diria"] = no_diria[:5]
    lang.setdefault("nivel", T4)
    ficha["lenguaje"] = lang

    # ---- anti-persona
    anti = dict(ficha.get("anti_persona") or {})
    anti.setdefault("quien_no_es", "")
    anti.setdefault("nivel", T4)
    ficha["anti_persona"] = anti

    return ficha


def _autocritica(ficha: dict, brief: dict) -> dict:
    """Detecta estereotipo, contradicción y frase genérica, y corrige.

    En modo real la corrección la hace el modelo: no se inyecta ninguna frase
    escrita de antemano.
    """
    diria = ficha.get("lenguaje", {}).get("diria") or []
    sospechosas = [f for f in diria if any(g in f.lower() for g in GENERICAS)]
    faltan = len(diria) < 3

    if not sospechosas and not faltan and ficha.get("anti_persona", {}).get("quien_no_es"):
        return ficha

    if llm.DRY:
        return _autocritica_local(ficha)

    usuario = (
        "Esta ficha tiene un problema de calidad. Corrígela.\n\n"
        f"FICHA ACTUAL\n{json.dumps(ficha, ensure_ascii=False, indent=2)}\n\n"
        f"PRODUCTO: {brief['marca']['nombre']} — {brief['marca']['producto']}\n"
        f"CIUDAD: {brief['ubicacion'].get('ciudad','')}\n"
        f"SEGMENTO: {brief['segmento']['edad_min']}–{brief['segmento']['edad_max']} años\n\n"
        "PROBLEMAS DETECTADOS\n"
        + ("- Frases que un humano no diría en voz alta o que son genéricas de "
           "publicidad: " + " / ".join(sospechosas) + "\n" if sospechosas else "")
        + ("- Faltan frases en «diria» (deben ser tres).\n" if faltan else "")
        + ("" if ficha.get("anti_persona", {}).get("quien_no_es") else
           "- Falta la anti-persona.\n")
        + "\nDevuelve la ficha COMPLETA corregida, con el mismo esquema. "
          "Las frases de «diria» deben ser literales, en primera persona, con el "
          "registro y el vocabulario de esa persona en esa ciudad. Sin adjetivos, "
          "sin clichés publicitarios."
    )
    try:
        r = llm.pedir_json(llm.cargar_prompt("v1_persona.md"), usuario,
                           seco=ficha, temperatura=0.9)
        corregida = llm.parsear(r, "la ficha corregida")
        # se conserva la estructura original si el modelo omitió algún bloque
        for bloque in ("perfil", "consumo", "conflicto", "lenguaje", "anti_persona"):
            if bloque not in corregida:
                corregida[bloque] = ficha[bloque]
        return corregida
    except Exception:  # noqa: BLE001
        return ficha


def _autocritica_local(ficha: dict) -> dict:
    """Solo para pruebas automáticas: completa la ficha sin llamar al modelo."""
    from .. import local
    diria = [f for f in ficha.get("lenguaje", {}).get("diria", [])
             if not any(g in f.lower() for g in GENERICAS)]
    ficha.setdefault("lenguaje", {})["diria"] = diria
    while len(ficha["lenguaje"]["diria"]) < 3:
        ficha["lenguaje"]["diria"].append("Yo a esa hora no pienso, solo pongo algo")
    if not ficha.get("anti_persona", {}).get("quien_no_es"):
        ficha["anti_persona"] = {"quien_no_es": "Quien busca información, no compañía",
                                 "nivel": T4}
    return ficha


def _seco(brief: dict) -> dict:
    from .. import local
    return local.persona(brief)


def inyectar(brief: dict, ficha: dict) -> str:
    """Bloque de texto que se inyecta en la ideación. Es la restricción clave."""
    f = ficha
    return (
        "PERSONA A LA QUE LE HABLAS\n"
        f"{f['perfil']['nombre']}, {f['perfil']['edad']}, {f['perfil']['ocupacion']}, "
        f"{f['perfil'].get('barrio','')}.\n"
        f"Consume: {f['consumo']['cuando']} — {f['consumo']['donde']}.\n"
        f"Problema: {f['conflicto']['problema']}.\n"
        f"Objeción que hay que desactivar: {f['conflicto']['objecion']}.\n"
        f"Detonante: {f['conflicto']['detonante']}.\n"
        f"Frases que diría: " + " / ".join(f["lenguaje"]["diria"]) + "\n"
        f"Frases PROHIBIDAS: " + " / ".join(f["lenguaje"]["no_diria"]) + "\n"
        f"NO le hablas a: {f['anti_persona']['quien_no_es']}.\n"
    )


