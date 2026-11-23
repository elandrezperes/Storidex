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

from .. import contracts, evidence, llm
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

    sources = brief.get("evidencia_publico", [])
    catalog = {f"E{i}": source for i, source in enumerate(sources, 1)}
    usuario += "\n\n" + json.dumps({"evidencia_publico": catalog}, ensure_ascii=False)
    ficha = llm.pedir_validado(llm.cargar_prompt("v2_persona.md"), usuario,
        lambda data: contracts.persona(data, brief),
        esquema="p2_persona", seco=_seco(brief) if llm.DRY else None, temperatura=0.9)
    ficha = _autocritica(ficha, brief)
    contracts.persona(ficha, brief)
    evidence.annotate(ficha, sources)
    ficha["cobertura"] = confianza(ficha)
    ficha["confianza"] = ficha["cobertura"].copy()
    return ficha


def _autocritica(ficha: dict, brief: dict) -> dict:
    """Segunda llamada obligatoria, validada; un fallo se registra y se comunica."""
    usuario = json.dumps({"brief": brief, "ficha": ficha}, ensure_ascii=False)
    corregida = llm.pedir_validado(llm.cargar_prompt("v1_autocritica_persona.md"), usuario,
        lambda data: contracts.persona(data, brief), esquema="p2_persona", seco=ficha if llm.DRY else None,
        temperatura=0.3)
    original_refs = ficha.get("referencias", {})
    corregida["referencias"] = {
        f"{block}.{field}": original_refs[f"{block}.{field}"]
        for block, fields in evidence.FIELDS.items() for field in fields
        if f"{block}.{field}" in original_refs
        and corregida[block][field] == ficha[block][field]
    }
    return corregida


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
        f"{evidence.context(f)}\n"
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


