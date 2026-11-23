"""Contratos de entrega y edición del servicio WSGI."""
import io
import json
from pathlib import Path

import pytest

import sites_backend
from core import llm
from core.phases import p6_qa


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIDEX_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("STORIDEX_PROXY_SECRET", "fixture")
    monkeypatch.setattr(llm, "DRY", True)

    def call(path="", data=None, expected=200):
        raw = json.dumps(data).encode() if data is not None else b""
        env = {
            "REQUEST_METHOD": "GET" if data is None else "POST",
            "PATH_INFO": "/api/proyectos" + path,
            "CONTENT_LENGTH": str(len(raw)),
            "HTTP_AUTHORIZATION": "Bearer fixture",
            "HTTP_X_STORIDEX_VIEWER": "a" * 64,
            "wsgi.input": io.BytesIO(raw),
        }
        headers = []
        body = b"".join(sites_backend.application(env, lambda status, fields: headers.append(status)))
        assert int(headers[0].split()[0]) == expected, body
        return body if expected == 200 and path.endswith(("/pdf", "/fdx")) else json.loads(body)

    return call


def preparar_proyecto(api, name="caso_02_producto", *, three=False):
    brief = json.loads(Path(f"examples/{name}.json").read_text())
    if three:
        brief["forma"]["participantes"] = [
            {"nombre": name, "protagonico": i == 0}
            for i, name in enumerate(("Ana", "Bea", "Camila"))
        ]
        brief["forma"]["mensaje_clave"] = "El grano conserva su aroma."
    project = api(data=brief)
    path = "/" + project["id"]
    for phase in ("investigar", "persona", "premisas"):
        project = api(path + "/" + phase, {})
        assert not {"research", "persona", "qa", "escaleta"} & project.keys()
    return path, api(path + "/escaleta", {"premisa": project["premisas"][0]["id"]})


def test_elenco_y_mensaje_exigidos():
    brief = {"marca": {"nombre": "Ejemplo"}, "forma": {
        "duracion_objetivo_s": 15, "tipo": "sketch", "mensaje_clave": "Hecho aquí",
        "participantes": [{"nombre": n} for n in ("Ana", "Bea", "Camila")],
    }}
    outline = {"beats": [
        {"tc_in": "00:00", "tc_out": "00:03", "funcion": "hook", "cuarta_pared": "indirecta"},
        {"tc_in": "00:03", "tc_out": "00:15", "funcion": "cierre", "cuarta_pared": "indirecta"},
    ]}
    paragraphs = [
        {"tipo": "scene_heading", "tc": "00:00", "texto": "INT. TIENDA"},
        {"tipo": "character", "texto": "ANA"},
        {"tipo": "action", "texto": "BEA sirve café."},
        {"tipo": "title", "texto": "Ejemplo"},
    ]
    script = {"parrafos": paragraphs}
    checks = p6_qa.lista_brief(brief, script, outline)
    assert checks["elenco"]["faltantes"] == ["camila"]
    assert "mensaje_clave" not in checks
    paragraphs.extend([
        {"tipo": "action", "texto": "CAMILA abre la puerta."},
        {"tipo": "title", "texto": "Hecho aquí"},
    ])
    assert all(result["ok"] for result in p6_qa.lista_brief(brief, script, outline).values())
    paragraphs.append({"tipo": "character", "texto": "DIEGO"})
    assert p6_qa.lista_brief(brief, script, outline)["elenco"]["fuera_del_elenco"] == ["diego"]


@pytest.mark.parametrize("failures, total, approved", [(0, 3, True), (3, 4, True), (5, 5, False)])
def test_revision_automatica(api, monkeypatch, failures, total, approved):
    path, project = preparar_proyecto(api)
    reviews, corrections = [], []
    original = sites_backend.p5_guion.ejecutar

    def generate(*args, correccion=None):
        corrections.append(correccion)
        return original(*args, correccion=correccion)

    def review(*args):
        reviews.append(args)
        return {"hallazgos": ["Falta una intervención."] if len(reviews) <= failures else []}

    monkeypatch.setattr(p6_qa, "revisar_brief", review)
    monkeypatch.setattr(sites_backend.p5_guion, "ejecutar", generate)
    for _ in range(total - 1):
        assert "guion" not in api(path + "/preparar", {})
        api(path + "/pdf", expected=404)
    result = api(path + "/preparar", {})
    assert ("guion" in result) == approved
    assert result["agotado"] == (not approved)
    assert len(reviews) == total
    assert sum(bool(c) for c in corrections) == min(failures, total - 1)
    api(path + "/preparar", {})
    assert len(reviews) == total


@pytest.mark.parametrize("name", ["caso_01_radio", "caso_02_producto", "caso_03_servicio"])
def test_demostracion_completa_y_pdf_editado(api, name):
    path, project = preparar_proyecto(api, name, three=True)
    for _ in range(3):
        project = api(path + "/preparar", {})
    assert "guion" in project, project
    original = api(path + "/pdf")
    texts = [p["texto"] for p in project["guion"]]
    texts[1] = "Texto guardado por el usuario"
    edited = api(path + "/editar", {"version": project["version"], "textos": texts})
    assert edited["version"] == project["version"] + 1
    assert api(path)["guion"][1]["texto"] == texts[1]
    api(path + "/editar", {"version": project["version"], "textos": texts}, expected=409)
    pdf = api(path + "/pdf")
    assert pdf.startswith(b"%PDF") and pdf != original
    assert b"Texto guardado por el usuario" in pdf
    from xml.etree import ElementTree
    fdx = ElementTree.fromstring(api(path + "/fdx"))
    assert fdx.tag == "FinalDraft"
    assert any(node.text == texts[1] for node in fdx.iter("Text"))


def test_compatibilidad_con_guion_ya_entregado(api, monkeypatch):
    path, _ = preparar_proyecto(api)
    directory = sites_backend._root() / "usuarios" / ("a" * 64) / path[1:]
    legacy = {"parrafos": [{"tipo": "action", "texto": "Guion entregado anteriormente"}]}
    sites_backend._write(directory, "guion", legacy)
    sites_backend._write(directory, "qa", {"hallazgos": ["Advertencia del flujo anterior"]})
    assert "guion" not in api(path)
    api(path + "/pdf", expected=404)

    # El PDF persistido identifica una entrega del flujo anterior.
    sites_backend.export_pdf.generar(legacy, sites_backend._read(directory, "brief"),
                                     str(directory / "guion.pdf"))

    def unexpected(*args, **kwargs):
        pytest.fail("Un guion ya entregado no debe volver a revisarse")

    monkeypatch.setattr(p6_qa, "revisar_brief", unexpected)
    assert api(path)["guion"] == legacy["parrafos"]
    assert api(path + "/preparar", {})["guion"] == legacy["parrafos"]
    assert b"Guion entregado anteriormente" in api(path + "/pdf")
    api(path + "/editar", {"version": 0, "textos": ["Guion anterior actualizado"]})
    assert api(path)["version"] == 1
    assert b"Guion anterior actualizado" in api(path + "/pdf")
    assert not (directory / "revision.json").exists()


@pytest.mark.parametrize("tipo", ["sketch", "publicitario"])
def test_escaleta_corrige_formato_y_reparte_quince_segundos(tipo):
    from core.phases.p4_escaleta import _reconstruir

    raw = [{"funcion": "hook", "cuarta_pared": "indirecta_con_tag"}]
    raw += [{"funcion": "conflicto", "cuarta_pared": "indirecta_con_tag"}] * 20
    beats = _reconstruir(raw, 15, tipo)
    assert beats[0]["tc_in"] == "00:00"
    assert beats[-1]["tc_out"] == "00:15"
    assert all(beat["tc_in"] < beat["tc_out"] for beat in beats)
    assert all(first["tc_out"] == second["tc_in"] for first, second in zip(beats, beats[1:]))
    assert all(b["cuarta_pared"] == ("directa" if tipo == "publicitario" else "indirecta")
               for b in beats[:-1])


@pytest.mark.parametrize("tipo, texto, ok", [
    ("action", "Mateo habla directamente al lente.", True),
    ("parenthetical", "(a cámara)", True),
    ("action", "Mateo toma la taza.", False),
])
def test_publicitario_reconoce_indicaciones_a_camara(tipo, texto, ok):
    brief = {"marca": {"nombre": "Café"}, "forma": {
        "tipo": "publicitario", "duracion_objetivo_s": 15,
        "participantes": [{"nombre": "Mateo"}],
    }}
    script = {"parrafos": [
        {"tipo": "scene_heading", "tc": "00:00", "texto": "INT. LOCAL"},
        {"tipo": "character", "texto": "MATEO"},
        {"tipo": tipo, "texto": texto},
        {"tipo": "dialogue", "texto": "Café recién tostado."},
    ]}
    outline = {"beats": [
        {"tc_in": "00:00", "tc_out": "00:02", "funcion": "hook", "cuarta_pared": "directa"},
        {"tc_in": "00:02", "tc_out": "00:15", "funcion": "cierre", "cuarta_pared": "directa"},
    ]}
    assert p6_qa.lista_brief(brief, script, outline)["formato"]["ok"] is ok


def test_revision_humana_se_asocia_a_la_version_del_guion(api):
    path, project = preparar_proyecto(api)
    for _ in range(3):
        project = api(path + "/preparar", {})
    assert project["cobertura"]["campos_totales"] == 12
    assert not project["cobertura"]["campos_con_fuente"]

    record = {"version": 0, "revisor": "Evaluadora", "metodo": "lectura", "segundos": 28.5}
    reviewed = api(path + "/revisar", record)
    assert reviewed["revision_humana"][0]["segundos"] == 28.5
    assert api(path)["revision_humana"] == reviewed["revision_humana"]

    api(path + "/revisar", {**record, "segundos": -1}, expected=400)
    texts = [p["texto"] for p in project["guion"]]
    edited = api(path + "/editar", {"version": 0, "textos": texts})
    assert not edited["revision_humana"]
    assert not edited.get("trazabilidad")
    api(path + "/revisar", record, expected=409)


def test_sketch_solo_admite_el_aparte_en_el_beat_final():
    brief = {"forma": {"tipo": "sketch"}}
    outline = {"beats": [
        {"tc_in": "00:00", "cuarta_pared": "indirecta"},
        {"tc_in": "00:12", "cuarta_pared": "indirecta_con_tag"},
    ]}
    paragraph = {"tipo": "parenthetical", "texto": "(a cámara)", "tc": "00:00"}
    script = {"parrafos": [paragraph]}
    assert not p6_qa.comprobar_cuarta_pared(brief, script, outline)["ok"]
    paragraph["tc"] = "00:12"
    assert p6_qa.comprobar_cuarta_pared(brief, script, outline)["ok"]


def test_dossier_y_revision_creativa_recorrida_normal(api):
    data = json.loads(Path("examples/caso_02_producto.json").read_text())
    data["referencias"] = [{
        "fuente": "meta", "url": "https://www.facebook.com/ads/library/?id=123",
        "fecha": "2026-11-18", "mercado": "EC", "hallazgo": "Apertura con producto",
    }]
    data["trends_csv"] = "Semana,Consulta: (Ecuador)\n2026-11-01,42\n"
    project = api(data=data)
    path = "/" + project["id"]
    for action in ("investigar", "persona", "premisas"):
        project = api(path + "/" + action, {})
    project = api(path + "/escaleta", {"premisa": "A"})
    for _ in range(3):
        project = api(path + "/preparar", {})
    assert project["qa"]["revision_creativa"]["estado"] == "pendiente"
    directory = sites_backend._root() / "usuarios" / ("a" * 64) / project["id"]
    stored = sites_backend._read(directory, "brief")
    dossier = stored["dossier_referencias"]
    assert dossier["referencias"][0]["id"] == "R1"
    assert dossier["trends"]["filas"][0][1] == "42"
    trace = sites_backend._read(directory, "trace")
    assert trace["llamadas"]
    assert all("tokens" in call for call in trace["llamadas"])


@pytest.mark.parametrize("message_ok", [True, False])
def test_mensaje_clave_se_evalua_por_sentido(api, monkeypatch, message_ok):
    path, _ = preparar_proyecto(api)
    api(path + "/preparar", {})
    directory = sites_backend._root() / "usuarios" / ("a" * 64) / path[1:]
    project = sites_backend._project(directory)
    brief = project["brief"]
    brief["forma"]["mensaje_clave"] = "Comunicar que el producto acompaña un momento cotidiano"
    candidate = project["revision"]["candidato"]
    audit = {key: {"ok": True, "evidencia": "Fragmento del guion"} for key in p6_qa.CRITERIOS}
    audit["mensaje"] = {"ok": message_ok, "evidencia": "El beneficio aparece en la acción"}
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.setattr(llm, "pedir_json",
                        lambda *a, **kw: llm.Respuesta(json.dumps(audit), "prueba"))
    result = p6_qa.revisar_brief(brief, project["persona"], candidate, project["escaleta"])
    assert "mensaje_clave" not in result["lista_brief"]
    assert any(h.startswith("Verificar mensaje.") for h in result["hallazgos"]) is not message_ok


def test_recuperacion_unica_conserva_revisiones_anteriores(api):
    path, _ = preparar_proyecto(api)
    api(path + "/preparar", {})
    directory = sites_backend._root() / "usuarios" / ("a" * 64) / path[1:]
    candidate = sites_backend._read(directory, "revision")["candidato"]
    old = {"pasadas": [{"hallazgos": ["Incumplimiento de mensaje_clave. {}"]}] * 5,
           "candidato": candidate, "agotado": True, "aprobado": False}
    sites_backend._write(directory, "revision", old)
    assert api(path)["puede_revisar"]
    for _ in range(3):
        result = api(path + "/preparar", {})
    assert "guion" in result
    assert not result["puede_revisar"]
    assert sites_backend._read(directory, "revision_mensaje_literal") == old
    assert len(sites_backend._read(directory, "revision")["pasadas"]) == 3


def test_otro_incumplimiento_no_habilita_recuperacion(api):
    path, _ = preparar_proyecto(api)
    api(path + "/preparar", {})
    directory = sites_backend._root() / "usuarios" / ("a" * 64) / path[1:]
    revision = sites_backend._read(directory, "revision")
    revision.update(agotado=True)
    revision["pasadas"][-1]["hallazgos"] = ["Incumplimiento de frase_exacta. {}"]
    sites_backend._write(directory, "revision", revision)
    assert not api(path)["puede_revisar"]


@pytest.mark.parametrize("cue", ["(sin mirar a cámara)", "(no mira directamente al lente)",
                                  "Ana evita mirar a cámara."])
def test_sketch_no_confunde_negacion_con_aparte(cue):
    brief = {"forma": {"tipo": "sketch"}}
    outline = {"beats": [
        {"tc_in": "00:00", "cuarta_pared": "indirecta"},
        {"tc_in": "00:12", "cuarta_pared": "indirecta"},
    ]}
    script = {"parrafos": [{"tipo": "action", "texto": cue, "tc": "00:00"}]}
    assert p6_qa.comprobar_cuarta_pared(brief, script, outline)["ok"]


@pytest.mark.parametrize("objective_ok", [True, False])
def test_marca_visible_y_resumen_semantico_coherente(monkeypatch, objective_ok):
    brief = {"marca": {"nombre": "Café"}, "forma": {
        "tipo": "sketch", "tono": "moderado", "duracion_objetivo_s": 15,
        "participantes": [{"nombre": "Ana"}],
    }, "objetivo": ["ventas"]}
    outline = {"beats": [
        {"tc_in": "00:00", "tc_out": "00:02", "funcion": "hook", "cuarta_pared": "indirecta"},
        {"tc_in": "00:02", "tc_out": "00:15", "funcion": "cierre", "cuarta_pared": "indirecta"},
    ]}
    script = {"parrafos": [
        {"tipo": "scene_heading", "tc": "00:00", "texto": "INT. LOCAL"},
        {"tipo": "action", "texto": "Ana muestra una taza con el nombre Café."},
        {"tipo": "character", "texto": "ANA"},
        {"tipo": "dialogue", "texto": "Una pausa para ti."},
    ]}
    persona = {"lenguaje": {"no_diria": []}, "confianza": {"nivel_global": "T4"}}
    audit = {key: {"ok": True, "evidencia": "Una pausa para ti."} for key in p6_qa.CRITERIOS}
    audit["objetivos"]["ok"] = objective_ok
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.setattr(llm, "pedir_json",
                        lambda *a, **kw: llm.Respuesta(json.dumps(audit), "prueba"))
    result = p6_qa.revisar_brief(brief, persona, script, outline)
    assert result["lista_brief"]["marca"]["ok"]
    assert result["objetivo_cumplido"]["ok"] is objective_ok
    assert result["objetivo_cumplido"]["evidencia"] == "Una pausa para ti."
    assert result["tono"]["ok"]
    assert any(h.startswith("Verificar objetivos.") for h in result["hallazgos"]) is not objective_ok


@pytest.mark.parametrize("kind,text,expected", [
    ("publicitario", "Ana no mira a cámara.", False),
    ("sketch", "Ana no mira a cámara. Después habla al público.", False),
    ("publicitario", "Ana no mira a cámara. Después habla al público.", True),
])
def test_negacion_no_oculta_una_indicacion_directa_posterior(kind, text, expected):
    outline = {"beats": [
        {"tc_in": "00:00", "cuarta_pared": "directa" if kind == "publicitario" else "indirecta"},
        {"tc_in": "00:12", "cuarta_pared": "directa" if kind == "publicitario" else "indirecta"},
    ]}
    script = {"parrafos": [{"tipo": "action", "texto": text, "tc": "00:00"}]}
    assert p6_qa.comprobar_cuarta_pared({"forma": {"tipo": kind}}, script, outline)["ok"] is expected
