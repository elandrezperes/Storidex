"""Dossier de referencias aportadas y patrones creativos reproducibles."""
from __future__ import annotations

import csv
from datetime import date
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

CATALOGO = Path(__file__).with_name("data") / "referencias_creativas.json"
CAMPOS = ("fuente", "url", "fecha", "mercado", "hallazgo")


def catalogo():
    return json.loads(CATALOGO.read_text(encoding="utf-8"))


def _url_publica(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None
    except ValueError:
        return False


def validar(brief):
    refs = brief.get("referencias", [])
    if not isinstance(refs, list) or len(refs) > 12:
        raise ValueError("Se admiten hasta 12 referencias por proyecto.")
    sources = catalogo()["fuentes"]
    for ref in refs:
        if (not isinstance(ref, dict)
                or any(not isinstance(ref.get(key), str) or not ref[key].strip() for key in CAMPOS)
                or ref["fuente"] not in sources or not _url_publica(ref["url"])
                or len(ref["hallazgo"]) > 2000 or len(ref["mercado"]) > 160
                or len(ref["url"]) > 1000):
            raise ValueError("Completa la fuente, el enlace HTTPS, la fecha, el mercado y el hallazgo.")
        try:
            date.fromisoformat(ref["fecha"])
        except ValueError as exc:
            raise ValueError("Usa una fecha válida para cada referencia.") from exc
    raw = brief.get("trends_csv", "")
    if not isinstance(raw, str) or len(raw) > 12000:
        raise ValueError("Usa un CSV de Google Trends de hasta 12 000 caracteres.")


def _serie(raw):
    """Retiene las filas exportadas y su cabecera, incluidas series múltiples."""
    if not raw.strip():
        return None
    lines = list(csv.reader(io.StringIO(raw.lstrip("\ufeff"))))
    start = next((i for i, row in enumerate(lines) if len(row) >= 2
                  and row[0].strip().casefold() in {
                      "day", "week", "month", "date", "year", "hora", "hour",
                      "día", "semana", "mes", "fecha", "año",
                  }), None)
    if start is None:
        return {"estado": "sin_serie_interpretable", "nivel": "T4"}
    header = lines[start]
    rows = [row for row in lines[start + 1:] if len(row) == len(header) and row[0].strip()]
    if not rows:
        return {"estado": "sin_serie_interpretable", "nivel": "T4"}
    return {"estado": "importada", "columnas": header, "filas": rows, "nivel": "T3",
            "fuente": "https://trends.google.com/trends/explore",
            "contexto_exportado": lines[:start],
            "metodo": "Interés relativo tal como se exportó de Google Trends."}


def congelar(brief):
    library = catalogo()
    objectives = set(brief["objetivo"])
    kind = brief["forma"]["tipo"]
    ranked = sorted(library["patrones"], key=lambda p: (
        -len(objectives.intersection(p["objetivos"])), p["tipo"] != kind, p.get("titulo") is None, p["id"],
    ))
    items = []
    for index, ref in enumerate(brief.get("referencias", []), 1):
        items.append({**{key: ref[key].strip() for key in CAMPOS}, "id": f"R{index}",
                      "origen": "aportada", "nivel": "T3", "veracidad": "sin_verificacion"})
    return {
        "version_catalogo": library["version"],
        "referencias": items,
        "trends": _serie(brief.get("trends_csv", "")),
        "patrones": [{**p, "url": p.get("url") or library["fuentes"][p["fuente"]]["url"]}
                     for p in ranked[:3]],
    }


def contexto(dossier):
    """Contexto breve; el CSV completo queda en el artefacto de auditoría."""
    trend = dossier.get("trends")
    sample = trend
    if trend and trend["estado"] == "importada":
        rows = trend["filas"]
        sample = {**trend, "total_filas": len(rows), "filas": rows if len(rows) <= 6 else rows[:1] + rows[-5:]}
    return {"referencias": dossier.get("referencias", []),
            "patrones": dossier.get("patrones", []), "trends": sample}


def brief_para_modelo(brief):
    """Evita repetir el dossier y el CSV en las llamadas de redacción."""
    return {key: value for key, value in brief.items()
            if key not in {"dossier_referencias", "referencias", "trends_csv"}}
