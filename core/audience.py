"""Edición de hipótesis de audiencia sin transformar declaraciones en mediciones."""
from copy import deepcopy

from . import contracts, evidence, levels


def editar(persona, changes, brief):
    contracts._exigir(isinstance(changes, dict), "La corrección debe contener campos de la ficha.")
    allowed = {f"{block}.{field}" for block, fields in evidence.FIELDS.items() for field in fields}
    allowed.add("perfil.nombre")
    contracts._exigir(set(changes) <= allowed, "Hay campos de audiencia no editables.")
    result, diff = deepcopy(persona), {}
    for key, value in changes.items():
        block, field = key.split(".")
        before = result[block][field]
        if before == value:
            continue
        result[block][field] = value
        diff[key] = {"antes": before, "despues": value, "nivel": "T1"}
        if key in result.get("afirmaciones", {}):
            result["afirmaciones"][key] = {
                "afirmacion": value, "origen": "correccion_usuario", "nivel": "T1",
                "respaldo": None, "veracidad": "sin_verificacion",
            }
    contracts.persona(result, brief)
    if diff:
        result.pop("frase_validada", None)
    for block, fields in evidence.FIELDS.items():
        result[block]["nivel"] = levels.peor(
            result.get("afirmaciones", {}).get(f"{block}.{field}", {}).get("nivel", "T4")
            for field in fields)
    result["cobertura"] = levels.confianza(result)
    result["confianza"] = result["cobertura"].copy()
    return result, diff
