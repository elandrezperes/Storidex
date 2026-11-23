"""Pruebas de extremo a extremo en modo seco (sin red, sin llaves)."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("STORIDEX_DRY_RUN", "true")

from core import contracts, export_fdx, export_pdf, levels  # noqa: E402
from core.phases import (p0_brief, p1_research, p2_persona, p3_premisas,  # noqa: E402
                         p4_escaleta, p5_guion, p6_qa)


def cargar(nombre: str) -> dict:
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "examples", nombre), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def flujo(tmp_path):
    brief = cargar("caso_01_radio.json")
    b, ruta = p0_brief.ejecutar(brief, raiz_runs=str(tmp_path))
    res = p1_research.ejecutar(b)
    per = p2_persona.ejecutar(b, res)
    txt = p2_persona.inyectar(b, per)
    pre = p3_premisas.ejecutar(b, per, res, txt)
    prem = pre["premisas"][1]
    esc = p4_escaleta.ejecutar(b, prem, txt)
    gu = p5_guion.ejecutar(b, per, prem, esc, txt)
    qa = p6_qa.ejecutar(b, per, gu, esc)
    return b, res, per, pre, esc, gu, qa, ruta


def test_p0_crea_carpeta_y_restricciones(tmp_path):
    b, ruta = p0_brief.ejecutar(cargar("caso_01_radio.json"), raiz_runs=str(tmp_path))
    assert os.path.isdir(ruta)
    assert os.path.isfile(os.path.join(ruta, "brief.json"))
    assert b["restricciones"]["edad_min"] == 25


def test_p0_rechaza_edad_invertida():
    brief = cargar("caso_01_radio.json")
    brief["segmento"]["edad_min"], brief["segmento"]["edad_max"] = 40, 25
    with pytest.raises(contracts.ContratoInvalido):
        contracts.brief(brief)


def test_p0_rechaza_sin_protagonista():
    brief = cargar("caso_01_radio.json")
    for p in brief["forma"]["participantes"]:
        p["protagonico"] = False
    with pytest.raises(contracts.ContratoInvalido):
        contracts.brief(brief)


def test_persona_respeta_el_rango_de_edad(flujo):
    b, _, per, *_ = flujo
    assert b["segmento"]["edad_min"] <= per["perfil"]["edad"] <= b["segmento"]["edad_max"]


def test_persona_tiene_anti_persona_y_frases(flujo):
    _, _, per, *_ = flujo
    assert per["anti_persona"]["quien_no_es"]
    assert len(per["lenguaje"]["diria"]) >= 3
    assert len(per["lenguaje"]["no_diria"]) >= 1


def test_competencia_sin_fuente_baja_a_inferido():
    datos = {"competencia": {"modo_solicitado": "ambas", "sin_datos": False,
                             "de_marca": [{"nombre": "X", "descripcion": "",
                                           "fuentes": [], "nivel": "T2", "hallazgos": []}],
                             "de_feed": []},
             "mercado": {"tendencias": []},
             "oportunidad": {"texto": "", "nivel": "T4"}, "fuentes_total": 0}
    out = contracts.research(datos)
    assert out["competencia"]["de_marca"][0]["nivel"] == "T4"


def test_tres_premisas_exactas(flujo):
    *_, pre, esc, gu, qa, ruta = flujo
    assert len(pre["premisas"]) == 3


def test_gancho_no_pasa_de_tres_segundos(flujo):
    *_, esc, gu, qa, ruta = flujo
    primero = esc["beats"][0]
    assert primero["funcion"] == "hook"
    assert (int(primero["tc_out"][3:]) - int(primero["tc_in"][3:])) <= 3


def test_escaleta_con_gancho_largo_falla():
    datos = {"beats": [
        {"tc_in": "00:00", "tc_out": "00:06", "funcion": "hook",
         "descripcion": "", "cuarta_pared": "indirecta"},
        {"tc_in": "00:06", "tc_out": "00:30", "funcion": "cierre",
         "descripcion": "", "cuarta_pared": "indirecta"}]}
    with pytest.raises(contracts.ContratoInvalido):
        contracts.escaleta(datos)


def test_guion_solo_tipos_permitidos(flujo):
    *_, gu, qa, ruta = flujo
    assert all(p["tipo"] in contracts.TIPOS_VALIDOS for p in gu["parrafos"])


def test_qa_reporta_dos_estimaciones(flujo):
    *_, qa, ruta = flujo
    assert qa["duracion"]["por_timecodes_s"] > 0
    assert qa["duracion"]["por_paginas_s"] > 0
    assert "excede_material" in qa["duracion"]


def test_qa_detecta_material_excedido():
    """Si se escribe mucho más de lo que cabe, el control debe avisar."""
    brief = {"forma": {"tipo": "sketch", "duracion_objetivo_s": 15, "tono": "neutro",
                       "especificaciones": ""}, "objetivo": ["views"]}
    ficha = {"lenguaje": {"no_diria": []}, "confianza": {"nivel_global": "T2"}}
    escaleta = {"beats": [{"tc_in": "00:00", "tc_out": "00:02", "funcion": "hook"},
                          {"tc_in": "00:02", "tc_out": "00:15", "funcion": "cierre"}],
                "duracion_estimada_s": 15.0}
    parrafos = []
    for _ in range(40):
        parrafos += [{"tipo": "character", "texto": "ANA"},
                     {"tipo": "dialogue", "texto": "Una línea larga de diálogo que ocupa bastante."}]
    guion = {"parrafos": parrafos, "meta": {"nivel_global": "T2"}}
    qa = p6_qa.ejecutar(brief, ficha, guion, escaleta)
    assert qa["duracion"]["excede_material"] is True
    assert any("sobra texto" in h for h in qa["hallazgos"])


def test_export_fdx_es_xml_valido(flujo):
    b, _, _, _, _, gu, _, _ = flujo
    datos = export_fdx.generar(gu, b)
    assert datos.startswith(b"<?xml")
    assert b"FinalDraft" in datos
    assert b"Scene Heading" in datos


def test_export_pdf_se_crea(flujo, tmp_path):
    b, _, _, _, _, gu, _, _ = flujo
    ruta = str(tmp_path / "g.pdf")
    export_pdf.generar(gu, b, ruta)
    with open(ruta, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_confianza_entre_cero_y_uno(flujo):
    _, _, per, *_ = flujo
    c = levels.confianza(per)
    assert 0.0 <= c["score"] <= 1.0
    assert c["nivel_global"] in levels.NIVELES




def test_dos_marcas_producen_guiones_distintos():
    """El modo seco debe responder al briefing, no devolver un ejemplo fijo."""
    from core.phases import p0_brief as p0

    base = {
        "ubicacion": {"pais": "Ecuador", "provincia": "Azuay", "ciudad": "Cuenca"},
        "segmento": {"edad_min": 25, "edad_max": 40, "sexo": "ambos", "nse": "C+"},
        "objetivo": ["ventas"],
        "forma": {"participantes": [{"nombre": "Ana", "protagonico": True}],
                  "tipo": "sketch", "especificaciones": "", "indicaciones": "",
                  "tono": "moderado", "duracion_objetivo_s": 30},
        "competencia": {"modo": "ambas"},
    }

    def correr(marca, producto):
        import tempfile
        brief = dict(base, marca={"nombre": marca, "producto": producto})
        b, _ = p0.ejecutar(brief, raiz_runs=tempfile.mkdtemp())
        res = p1_research.ejecutar(b)
        per = p2_persona.ejecutar(b, res)
        txt = p2_persona.inyectar(b, per)
        pre = p3_premisas.ejecutar(b, per, res, txt)
        esc = p4_escaleta.ejecutar(b, pre["premisas"][1], txt)
        gu = p5_guion.ejecutar(b, per, pre["premisas"][1], esc, txt)
        return per, pre, gu

    per1, pre1, gu1 = correr("Panadería La Espiga", "Pan artesanal")
    per2, pre2, gu2 = correr("Clínica Dental Sonrisa", "Odontología general")

    # el conflicto de la persona cambia según el producto
    assert per1["conflicto"]["problema"] != per2["conflicto"]["problema"]

    # y el guion menciona la marca correcta en cada caso
    texto1 = " ".join(p["texto"] for p in gu1["parrafos"])
    texto2 = " ".join(p["texto"] for p in gu2["parrafos"])
    assert "Panadería La Espiga" in texto1 and "Panadería La Espiga" not in texto2
    assert "Clínica Dental Sonrisa" in texto2


def test_guion_usa_el_nombre_del_protagonico():
    """El elenco declarado por el usuario debe aparecer en el guion."""
    from core.phases import p0_brief as p0
    import tempfile
    brief = cargar("caso_01_radio.json")
    brief["forma"]["participantes"] = [{"nombre": "Rosalía", "protagonico": True}]
    b, _ = p0.ejecutar(brief, raiz_runs=tempfile.mkdtemp())
    res = p1_research.ejecutar(b)
    per = p2_persona.ejecutar(b, res)
    txt = p2_persona.inyectar(b, per)
    pre = p3_premisas.ejecutar(b, per, res, txt)
    esc = p4_escaleta.ejecutar(b, pre["premisas"][1], txt)
    gu = p5_guion.ejecutar(b, per, pre["premisas"][1], esc, txt)
    personajes = [p["texto"] for p in gu["parrafos"] if p["tipo"] == "character"]
    assert all(c == "ROSALÍA" for c in personajes)


# --------------------------------------------------- robustez de las premisas
def test_extraer_premisas_acepta_variantes():
    """El modelo devuelve el JSON con formas distintas; hay que rescatarlas."""
    from core.phases.p3_premisas import _extraer, _normalizar, _completas

    p = {"caracter": "c", "conflicto": "x", "desenlace": "d", "proposicion": "p"}

    # dict con la clave esperada
    assert len(_extraer({"premisas": [p, p, p]})) == 3
    # lista suelta
    assert len(_extraer([p, p, p])) == 3
    # clave en inglés
    assert len(_extraer({"premises": [p, p, p]})) == 3
    # dict indexado por letras
    assert len(_extraer({"A": p, "B": p, "C": p})) == 3
    # un objeto suelto
    assert len(_extraer(p)) == 1
    # basura
    assert _extraer({"otra_cosa": 1}) == []
    assert _extraer(None) == []

    normal = _normalizar([p, p, p])
    assert _completas(normal)
    assert [x["id"] for x in normal] == ["A", "B", "C"]


def test_extraer_premisas_con_alias_de_campos():
    from core.phases.p3_premisas import _normalizar, _completas
    crudas = [
        {"character": "c", "conflict": "x", "resolution": "d", "premise": "p"},
        {"personaje": "c", "tension": "x", "final": "d", "idea": "p"},
        {"caracter": "c", "conflicto": "x", "desenlace": "d", "proposicion": "p"},
    ]
    assert _completas(_normalizar(crudas))


def test_premisas_incompletas_no_revientan_con_keyerror():
    """Si el modelo no da tres premisas, el error debe ser explícito, no KeyError."""
    from core.phases import p3_premisas
    from core import llm

    original = llm.pedir_json
    try:
        llm.pedir_json = lambda *a, **k: llm.Respuesta('{"otra_cosa": true}', "falso")
        brief = {"marca": {"nombre": "X", "producto": "Y"}, "objetivo": ["views"],
                 "forma": {"tipo": "sketch", "tono": "neutro", "duracion_objetivo_s": 30,
                           "especificaciones": ""},
                 "ubicacion": {"ciudad": "Cuenca"},
                 "segmento": {"edad_min": 25, "edad_max": 40},
                 "_dry_backup": True}
        import os
        os.environ["STORIDEX_DRY_RUN"] = "false"
        llm.DRY = False
        ficha = {"confianza": {"nivel_global": "T2"}}
        try:
            p3_premisas.ejecutar(brief, ficha, {"oportunidad": {"texto": ""}}, "")
        except p3_premisas.PremisasInvalidas as e:
            assert "tres premisas" in str(e)
        else:
            raise AssertionError("debería haber lanzado PremisasInvalidas")
    finally:
        llm.pedir_json = original
        llm.DRY = True
        import os
        os.environ["STORIDEX_DRY_RUN"] = "true"


# ------------------------------------------- normalización de lo que devuelve el modelo
def test_tiempo_a_segundos_acepta_formatos():
    from core.normaliza import tiempo_a_segundos as t
    assert t("00:03") == 3
    assert t("0:03") == 3
    assert t("00:00:03") == 3
    assert t("3") == 3
    assert t(3) == 3
    assert t("3s") == 3
    assert t(None) is None
    assert t("basura") is None


def test_normalizar_funcion_admite_sinonimos():
    from core.normaliza import normalizar_funcion as f
    assert f("hook") == "hook"
    assert f("Gancho") == "hook"
    assert f("GANCHO") == "hook"
    assert f("conflict") == "conflicto"
    assert f("Llamado a la acción") == "cta"
    assert f("closing") == "cierre"
    assert f("cualquier cosa") in ("planteamiento", "conflicto")


def test_normalizar_tipo_de_parrafo():
    from core.normaliza import normalizar_tipo as n
    assert n("scene_heading") == "scene_heading"
    assert n("Scene Heading") == "scene_heading"
    assert n("ENCABEZADO") == "scene_heading"
    assert n("Diálogo") == "dialogue"
    assert n("dialogo") == "dialogue"
    assert n("Acción") == "action"
    assert n("Personaje") == "character"
    assert n("Rótulo") == "title"
    assert n("inventado") is None


def test_escaleta_reconstruye_timecodes_ausentes():
    """Si el modelo no da códigos válidos, se calculan y cumplen el contrato."""
    from core.phases.p4_escaleta import _reconstruir, PESOS  # noqa: F401
    beats = [{"funcion": "gancho", "descripcion": "a"},
             {"funcion": "conflict", "descripcion": "b"},
             {"funcion": "resolution", "descripcion": "c"},
             {"funcion": "closing", "descripcion": "d"}]
    out = _reconstruir(beats, 30, "sketch")
    assert out[0]["funcion"] == "hook"
    # el gancho nunca pasa de tres segundos
    h = out[0]
    assert (int(h["tc_out"][3:]) - int(h["tc_in"][3:])) <= 3
    # contiguos y terminando en la duración objetivo
    for a, b in zip(out, out[1:]):
        assert a["tc_out"] == b["tc_in"]
    assert out[-1]["tc_out"] == "00:30"


def test_escaleta_inserta_gancho_si_falta():
    from core.phases.p4_escaleta import _reconstruir
    out = _reconstruir([{"funcion": "conflicto"}, {"funcion": "cierre"}], 30, "sketch")
    assert out[0]["funcion"] == "hook"


def test_guion_normaliza_tipos_en_ingles():
    from core.phases.p5_guion import _normalizar_parrafos
    crudos = [
        {"type": "Scene Heading", "text": "INT. ESTUDIO. DÍA."},
        {"type": "Action", "text": "Ana entra."},
        {"type": "Character", "text": "ANA"},
        {"type": "Diálogo", "text": "Hola."},
        {"type": "inventado", "text": "se descarta"},
    ]
    out = _normalizar_parrafos(crudos)
    assert [p["tipo"] for p in out] == ["scene_heading", "action", "character", "dialogue"]


def test_tomar_lista_rescata_estructuras_variadas():
    from core.normaliza import tomar_lista
    assert tomar_lista({"parrafos": [{"a": 1}]}, ("parrafos",)) == [{"a": 1}]
    assert tomar_lista({"paragraphs": [{"a": 1}]}, ("parrafos", "paragraphs")) == [{"a": 1}]
    assert tomar_lista([{"a": 1}], ("x",)) == [{"a": 1}]
    assert tomar_lista(None, ("x",)) == []
    assert tomar_lista({"otra": 1}, ("x",)) == []


def test_procedencia_exige_fragmento_del_catalogo(flujo):
    from copy import deepcopy
    from core import evidence

    _, _, ficha, *_ = flujo
    ficha = deepcopy(ficha)
    ficha["referencias"] = {
        "conflicto.objecion": {"id": "E1", "fragmento": "Ya probé algo similar"},
        "conflicto.detonante": {"id": "E1", "fragmento": "Texto inventado"},
    }
    evidence.annotate(ficha, [{
        "origen": "declaracion_dueno", "informante": "Dueña", "fecha": "2026-11-18",
        "fragmento": "Ya probé algo similar, según me contó una clienta.",
    }])
    claims = ficha["afirmaciones"]
    assert claims["conflicto.objecion"]["nivel"] == "T1"
    assert claims["conflicto.objecion"]["veracidad"] == "sin_verificacion"
    assert claims["conflicto.detonante"]["origen"] == "inferencia_ia"
    assert levels.confianza(ficha)["campos_con_fuente"] == 1
