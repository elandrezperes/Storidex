"""P0 · Briefing: validación y construcción de restricciones duras.

No usa ningún modelo. Es la fase que más controla: si el briefing está mal,
ninguna fase posterior puede compensarlo.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from .. import contracts, referencias
from ..levels import T1


def _slug(texto: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "_", texto.lower().strip())
    return t.strip("_")[:28] or "sin_marca"


def nuevo_run_id(marca: str) -> str:
    return f"{datetime.now():%Y-%m-%d_%H%M}_{_slug(marca)}"


def restricciones(brief: dict) -> dict:
    """Bloque que las fases posteriores no pueden violar."""
    seg = brief["segmento"]
    ubi = brief["ubicacion"]
    return {
        "edad_min": seg["edad_min"],
        "edad_max": seg["edad_max"],
        "sexo": seg["sexo"],
        "nse": seg.get("nse", ""),
        "pais": ubi.get("pais", ""),
        "provincia": ubi.get("provincia", ""),
        "ciudad": ubi.get("ciudad", ""),
        "duracion_objetivo_s": brief["forma"]["duracion_objetivo_s"],
        "tipo": brief["forma"]["tipo"],
        "tono": brief["forma"]["tono"],
        "frases_prohibidas": [],
    }


def ejecutar(brief: dict, raiz_runs: str = "runs", *,
             identificador: str | None = None) -> tuple[dict, str]:
    """Valida, normaliza, asigna niveles T1 y persiste la ejecución."""
    contracts.brief(brief)

    b = json.loads(json.dumps(brief))  # copia profunda
    b.setdefault("idioma", {"locale": "es-EC", "variante": "cuencano"})
    b.setdefault("competencia", {"modo": "ambas"})

    b.setdefault("espacio", {"modo": "auto"})
    if b["espacio"].get("modo") == "fijo":
        from .. import espacio
        b["espacio"] = {"modo": "fijo", **espacio.construir(
            b["espacio"]["tipo"], b["espacio"]["local"], b["espacio"]["momento"])}

    b["run_id"] = identificador or nuevo_run_id(b["marca"]["nombre"])
    b["niveles"] = {
        "marca": T1, "producto": T1, "ubicacion": T1,
        "segmento": T1, "objetivo": T1, "forma": T1,
    }
    b["restricciones"] = restricciones(b)
    b["dossier_referencias"] = referencias.congelar(b)

    ruta = os.path.join(raiz_runs, b["run_id"])
    os.makedirs(ruta, exist_ok=True)
    with open(os.path.join(ruta, "brief.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=2)
    return b, ruta

