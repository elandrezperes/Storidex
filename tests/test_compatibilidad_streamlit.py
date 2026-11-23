"""Regresiones conservadas del repositorio de GitHub."""
import os
import sys
from tests.test_flujo import cargar
from core.phases import p1_research, p2_persona, p3_premisas, p4_escaleta, p5_guion, p6_qa

# ------------------------------------------------------------- espacio escénico
def test_espacio_encabezado_y_normalizacion():
    from core import espacio as e
    esp = e.construir("int", "local - sala", "mediodia")
    assert esp == {"tipo": "INT", "local": "LOCAL / SALA", "momento": "MEDIODÍA"}
    assert e.encabezado(esp) == "INT. LOCAL / SALA. MEDIODÍA."


def test_espacio_acepta_los_tres_tipos():
    from core import espacio as e
    for valor in ("INT", "int", "Interior", "EXT", "exterior", "INT/EXT", "ambos"):
        assert e.normalizar_tipo(valor) in ("INT", "EXT", "INT/EXT")


def test_espacio_extrae_del_encabezado_profesional():
    from core import espacio as e
    assert e.extraer_del_texto("INT. APARTAMENTO - SALA/COCINA. DÍA.")["local"] \
        == "APARTAMENTO - SALA/COCINA"
    assert e.extraer_del_texto("EXT. CALLE. NOCHE.")["momento"] == "NOCHE"
    assert e.extraer_del_texto("HOOK — INT. ESTUDIO. DÍA.")["local"] == "ESTUDIO"
    assert e.extraer_del_texto("INT./EXT. AUTO EN MOVIMIENTO. CONTINUO.")["tipo"] == "INT/EXT"
    assert e.extraer_del_texto("sin espacio") is None


def test_espacio_validar_detecta_errores():
    from core import espacio as e
    assert e.validar(e.construir("INT", "LOCAL", "DÍA")) == []
    fallos = e.validar({"tipo": "XX", "local": "", "momento": "NOCHECITA"})
    assert len(fallos) == 3


def test_escaleta_declara_espacio_en_cada_unidad():
    from core.phases import p0_brief as p0
    import tempfile
    brief = cargar("caso_01_radio.json")
    b, _ = p0.ejecutar(brief, raiz_runs=tempfile.mkdtemp())
    res = p1_research.ejecutar(b)
    per = p2_persona.ejecutar(b, res)
    txt = p2_persona.inyectar(b, per)
    pre = p3_premisas.ejecutar(b, per, res, txt)
    esc = p4_escaleta.ejecutar(b, pre["premisas"][0], txt)
    for beat in esc["beats"]:
        assert set(beat["espacio"]) >= {"tipo", "local", "momento"}
        assert beat["espacio"]["momento"] in __import__("core.espacio", fromlist=["x"]).MOMENTOS


def test_espacio_fijo_se_respeta_en_todo_el_guion():
    from core.phases import p0_brief as p0
    import tempfile
    brief = cargar("caso_01_radio.json")
    brief["espacio"] = {"modo": "fijo", "tipo": "EXT", "local": "PARQUE CENTRAL",
                        "momento": "NOCHE"}
    b, _ = p0.ejecutar(brief, raiz_runs=tempfile.mkdtemp())
    res = p1_research.ejecutar(b)
    per = p2_persona.ejecutar(b, res)
    txt = p2_persona.inyectar(b, per)
    pre = p3_premisas.ejecutar(b, per, res, txt)
    esc = p4_escaleta.ejecutar(b, pre["premisas"][0], txt)
    gu = p5_guion.ejecutar(b, per, pre["premisas"][0], esc, txt)
    qa = p6_qa.ejecutar(b, per, gu, esc)

    encabezados = [p for p in gu["parrafos"] if p["tipo"] == "scene_heading"]
    assert encabezados
    for p in encabezados:
        assert p["espacio"]["local"] == "PARQUE CENTRAL"
        assert p["espacio"]["momento"] == "NOCHE"
        assert "EXT." in p["texto"]
    assert qa["espacio"]["ok"] is True


def test_qa_avisa_si_falta_el_espacio():
    from core.phases.p6_qa import ejecutar as qa
    brief = {"forma": {"tipo": "sketch", "duracion_objetivo_s": 30, "tono": "neutro",
                       "especificaciones": "", "participantes": [
                           {"nombre": "Ana", "protagonico": True}]},
             "objetivo": ["views"], "espacio": {"modo": "auto"}}
    ficha = {"lenguaje": {"no_diria": []}, "confianza": {"nivel_global": "T2"}}
    escaleta = {"beats": [{"tc_in": "00:00", "tc_out": "00:03", "funcion": "hook",
                           "espacio": {"tipo": "INT", "local": "X", "momento": "DÍA"}},
                          {"tc_in": "00:03", "tc_out": "00:30", "funcion": "cierre",
                           "espacio": {"tipo": "INT", "local": "X", "momento": "DÍA"}}],
                "duracion_estimada_s": 30.0}
    guion = {"parrafos": [
        {"tipo": "scene_heading", "texto": "SIN ESPACIO"},
        {"tipo": "character", "texto": "ANA"},
        {"tipo": "dialogue", "texto": "Hola."},
    ], "meta": {"nivel_global": "T2"}}
    out = qa(brief, ficha, guion, escaleta)
    assert out["espacio"]["ok"] is False
    assert any("no declara tipo" in h for h in out["hallazgos"])


# --------------------------------------------------------------- acceso y topes
def test_sin_clave_configurada_el_acceso_es_libre(monkeypatch):
    monkeypatch.delenv("STORIDEX_CLAVE", raising=False)
    from core import auth
    assert auth.hay_que_autenticarse() is False
    assert auth.verificar("lo que sea") is True


def test_con_clave_configurada_solo_pasa_la_correcta(monkeypatch):
    monkeypatch.setenv("STORIDEX_CLAVE", "secreta-123")
    from core import auth
    assert auth.hay_que_autenticarse() is True
    assert auth.verificar("secreta-123") is True
    assert auth.verificar("otra") is False
    assert auth.verificar("") is False


def test_tope_de_sesion(monkeypatch):
    monkeypatch.setenv("STORIDEX_TOPE_SESION", "2")
    from core import auth
    ok, aviso = auth.puede_generar(0)
    assert ok and "2" in aviso
    ok, _ = auth.puede_generar(1)
    assert ok
    ok, aviso = auth.puede_generar(2)
    assert not ok and "tope" in aviso


def test_tope_cero_es_sin_limite(monkeypatch):
    monkeypatch.setenv("STORIDEX_TOPE_SESION", "0")
    from core import auth
    assert auth.puede_generar(999)[0] is True


def test_clave_se_lee_de_secretos_de_streamlit(monkeypatch):
    """En la nube no hay .env: la clave llega por st.secrets."""
    monkeypatch.delenv("STORIDEX_CLAVE", raising=False)
    from core import auth

    class _Secretos(dict):
        pass

    class _Falso:
        secrets = _Secretos({"STORIDEX_CLAVE": "desde-secretos"})

    monkeypatch.setattr(auth, "_cfg", auth._cfg)
    import sys
    monkeypatch.setitem(sys.modules, "streamlit", _Falso)
    assert auth.clave_configurada() == "desde-secretos"
