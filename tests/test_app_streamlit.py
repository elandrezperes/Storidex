"""Comprueba la navegación real de Streamlit sin modelos ni navegador."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core import auth, llm


def _widget(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def test_contexto_y_forma_con_espacio_fijo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(llm, "DRY", True)
    monkeypatch.setattr(auth, "clave_configurada", lambda: "")
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "app.py"), default_timeout=10).run()
    assert not app.exception
    _widget(app.button, "Crear un guion").click().run()
    assert not app.exception
    _widget(app.text_input, "Nombre de la marca *").set_value("Marca de prueba")
    _widget(app.text_input, "Producto o servicio *").set_value("Producto artesanal")
    _widget(app.multiselect, "Objetivo *").set_value(["views"])
    app.run()
    _widget(app.button, "Continuar →").click().run()
    assert not app.exception
    _widget(app.text_input, "Nombre 1 *").set_value("Ana")
    _widget(app.radio, "¿Quién decide el espacio? *").set_value("fijo")
    app.run()
    assert _widget(app.button, "Generar guion →").disabled
    _widget(app.text_input, "Localización *").set_value("TALLER")
    app.run()
    assert not app.exception
    assert not _widget(app.button, "Generar guion →").disabled
    _widget(app.button, "Generar guion →").click().run()
    assert not app.exception
    assert app.session_state["brief"]["espacio"]["local"] == "TALLER"
    assert app.session_state["premisas"] is None
    _widget(app.button, "Confirmar audiencia y generar premisas").click().run()
    assert not app.exception
    assert len(app.session_state["premisas"]["premisas"]) == 3
    _widget(app.button, "Escribir el guion").click().run()
    assert not app.exception
    assert app.session_state["guion"]["trazabilidad"]
    assert app.session_state["qa"]["espacio"]["ok"]
    assert app.session_state["guiones_sesion"] == 1
