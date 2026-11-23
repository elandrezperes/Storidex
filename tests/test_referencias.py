"""Importación y trazabilidad del dossier creativo."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from core import contracts, llm, referencias
from core.phases import p0_brief, p1_research


def brief():
    return json.loads(Path("examples/caso_02_producto.json").read_text())


def test_dossier_congelado_conserva_fuentes_y_series(tmp_path):
    data = brief()
    data["referencias"] = [{
        "fuente": "meta", "url": "https://www.facebook.com/ads/library/?id=123",
        "fecha": "2026-11-18", "mercado": "Ecuador", "hallazgo": "Producto visible en apertura",
    }]
    data["trends_csv"] = "Categoría: Todas\n\nSemana,café: (Ecuador)\n2026-11-01,45\n2026-11-08,<1\n"
    frozen, _ = p0_brief.ejecutar(data, str(tmp_path))
    dossier = frozen["dossier_referencias"]
    assert dossier["referencias"][0]["origen"] == "aportada"
    assert dossier["trends"]["filas"][-1][1] == "<1"
    assert len(dossier["patrones"]) == 3
    before = deepcopy(dossier)
    data["referencias"][0]["hallazgo"] = "Cambio"
    assert frozen["dossier_referencias"] == before


def test_dossier_invalido_se_rechaza_y_csv_ininterpretable_se_declara():
    data = brief()
    data["referencias"] = [{"fuente": "meta", "url": "javascript:alert(1)"}]
    with pytest.raises(contracts.ContratoInvalido):
        contracts.brief(data)
    data["referencias"] = []
    data["trends_csv"] = "esto no contiene una serie"
    assert referencias.congelar(data)["trends"]["estado"] == "sin_serie_interpretable"


def test_fuentes_aportadas_no_se_convierten_en_grounding(monkeypatch):
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.setattr(llm, "investigar", lambda *a, **kw: llm.Respuesta(json.dumps({
        "competencia": {"de_marca": [{"nombre": "Inventado", "fuentes": ["https://fake.test"]}]},
        "mercado": {"tendencias": [{"termino": "algo", "fuente": "https://fake.test"}]},
    }), "prueba", fuentes=[]))
    result = p1_research.ejecutar(brief())
    assert not result["competencia"]["de_marca"]
    assert not result["mercado"]["tendencias"]
    assert result["oportunidad"]["nivel"] == "T4"
    assert result["dossier_referencias"]["patrones"]


def test_trace_registra_version_y_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "DRY", True)
    with llm.auditar(tmp_path):
        llm.pedir_json(llm.cargar_prompt("v3_premisas.md"), "datos", seco={})
    trace = json.loads((tmp_path / "trace.json").read_text())
    assert trace["llamadas"][0]["prompt"] == "v3_premisas.md"
    assert trace["tokens"] == {"entrada": 0, "salida": 0}
    assert trace["costo_estimado"] == 0


def test_busqueda_contextual_solo_admite_referencias_del_grounding(monkeypatch):
    monkeypatch.setattr(llm, "DRY", False)
    url = "https://ads.tiktok.com/business/creativecenter/example"
    result = {
        "competencia": {"de_marca": [], "de_feed": []},
        "mercado": {"tendencias": []},
        "referencias_contextuales": [
            {"fuente": "tiktok", "url": url, "hallazgo": "Apertura con demostración"},
            {"fuente": "meta", "url": "https://fake.test", "hallazgo": "Sin respaldo"},
        ],
    }
    monkeypatch.setattr(llm, "investigar", lambda *a, **kw:
                        llm.Respuesta(json.dumps(result), "prueba", fuentes=[url]))
    researched = p1_research.ejecutar(brief())
    refs = researched["dossier_referencias"]["referencias"]
    assert len(refs) == 1
    assert refs[0]["url"] == url
    assert researched["herramientas"]["tiktok"]["estado"] == "referencias_disponibles"
    assert researched["herramientas"]["meta"]["estado"] == "sin_datos_actuales"
    assert not researched["competencia"]["de_marca"]
