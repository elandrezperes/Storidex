"""Procedencia de afirmaciones y vínculos propuestos por el modelo."""
from __future__ import annotations

import json

from .levels import peor

FIELDS = {
    "perfil": ("edad", "ocupacion", "barrio"),
    "consumo": ("cuando", "donde", "dispositivo"),
    "conflicto": ("problema", "objecion", "detonante"),
    "lenguaje": ("diria", "no_diria"),
    "anti_persona": ("quien_no_es",),
}


def annotate(persona, sources):
    references = persona.pop("referencias", {})
    if not isinstance(references, dict):
        references = {}
    by_id = {f"E{i}": source for i, source in enumerate(sources, 1)}
    claims = {}
    for block, fields in FIELDS.items():
        for field in fields:
            key = f"{block}.{field}"
            link = references.get(key)
            source_id = link.get("id") if isinstance(link, dict) else None
            source = by_id.get(source_id) if isinstance(source_id, str) else None
            quote = link.get("fragmento") if isinstance(link, dict) else None
            supported = (
                source is not None and isinstance(quote, str) and quote.strip()
                and quote.strip() in source["fragmento"]
                and persona[block][field] not in ("", [], None)
            )
            claims[key] = {
                "afirmacion": persona[block][field],
                "origen": source["origen"] if supported else "inferencia_ia",
                "nivel": ("T1" if source["origen"] == "declaracion_dueno" else "T2")
                if supported else "T4",
                "respaldo": {**source, "id": source_id, "fragmento": quote.strip()}
                if supported else None,
                "veracidad": "sin_verificacion",
            }
        persona[block]["nivel"] = peor(
            claims[f"{block}.{field}"]["nivel"] for field in fields
        )
    persona["afirmaciones"] = claims


def context(persona):
    claims = persona.get("afirmaciones", {})
    return json.dumps(claims, ensure_ascii=False)


def valid_refs(value, allowed):
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(key for key in value if isinstance(key, str) and key in allowed))


def script_links(raw, paragraphs, outline):
    """Conserva enlaces propuestos con un beat y un fragmento existentes."""
    beats = {beat["tc_in"]: beat.get("afirmaciones", []) for beat in outline["beats"]}
    links = []
    if not isinstance(raw, list):
        return links
    for link in raw:
        if not isinstance(link, dict):
            continue
        beat = link.get("beat")
        fragment = link.get("fragmento")
        if not isinstance(beat, str) or not isinstance(fragment, str) or not fragment.strip():
            continue
        refs = valid_refs(link.get("afirmaciones"), beats.get(beat, []))
        matches = [i for i, paragraph in enumerate(paragraphs)
                   if paragraph["tipo"] in {"action", "dialogue", "title"}
                   and fragment.strip() in paragraph["texto"]]
        if refs and len(matches) == 1:
            links.append({"beat": beat, "parrafo": matches[0], "afirmaciones": refs,
                          "fragmento": fragment.strip(), "estado": "propuesto"})
    return links
