"""Servicio WSGI de Storidex, accesible desde el Worker privado de Sites."""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from core import audience, contracts, export_fdx, export_pdf, llm, referencias, services
from core.phases import (
    p0_brief, p1_research, p2_persona, p3_premisas, p4_escaleta, p5_guion, p6_qa,
)

MAX_BODY = 98_304
ARTIFACTS = ("brief", "research", "persona", "premisas", "escaleta", "guion", "qa")


class RequestError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _root():
    return Path(os.environ.get("STORIDEX_RUNS_DIR", "runs/sites"))


def _read(directory, name):
    return json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))


def _write(directory, name, value):
    temporary = directory / f".{name}.{uuid4().hex}.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(directory / f"{name}.json")


@contextmanager
def _locked(directory):
    import fcntl

    with (directory / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RequestError("409 Conflict", "Este proyecto está procesando otra acción.") from exc
        yield


def _project(directory):
    result = {name: _read(directory, name) for name in ARTIFACTS
              if (directory / f"{name}.json").is_file()}
    result.update(_read(directory, "estado"))
    for name in ("revision", "edicion", "revision_humana"):
        if (directory / f"{name}.json").is_file():
            result[name] = _read(directory, name)
    # El flujo anterior publicaba el PDF junto con el guion y su QA.
    result["entregado"] = (
        "guion" in result and (
            result["revision"].get("aprobado", False) if "revision" in result
            else "qa" in result and (directory / "guion.pdf").is_file()
        )
    )
    result["id"] = directory.name
    result["demostracion"] = llm.DRY
    if result["entregado"]:
        result["media"] = services.media_state(directory, result.get("edicion", result["guion"]))
    return result


def _revision_literal_recuperable(project):
    revision = project.get("revision", {})
    history = revision.get("pasadas", [])
    findings = history[-1].get("hallazgos", []) if history else []
    return (
        not project["entregado"] and revision.get("agotado", False)
        and not revision.get("version_mensaje")
        and bool(revision.get("candidato")) and bool(findings)
        and all(item.startswith("Incumplimiento de mensaje_clave.") for item in findings)
    )


def _public(project):
    result = {
        "id": project["id"], "marca": project["brief"]["marca"]["nombre"],
        "demostracion": project["demostracion"],
        "investigado": "research" in project,
        "investigacion": {"sin_busqueda": project.get("research", {}).get("sin_busqueda", False),
                          "fuentes_total": project.get("research", {}).get("fuentes_total", 0)},
        "herramientas": project.get("research", {}).get("herramientas", {}),
        "services": {key: {**value, **{k: v for k, v in project.get("research", {}).get(
            "services", {}).get(key, {}).items() if k != "configured"}}
            for key, value in services.states().items()},
        "references": project.get("research", {}).get("dossier_referencias", {}).get("referencias", []),
        "frases": project.get("persona", {}).get("lenguaje", {}).get("diria", []),
        "audiencia": {key: value for key, value in project.get("persona", {}).items()
                      if key in {*audience.evidence.FIELDS, "version", "cobertura", "afirmaciones"}},
        "segmento": project["brief"]["segmento"],
        "premisas": [{"id": p["id"], "proposicion": p["proposicion"],
                      **{key: p[key] for key in ("conflicto", "recurso_visual",
                                                "desenlace", "razon_estrategica") if key in p},
                      "referencias_creativas": p.get("referencias_creativas", [])}
                     for p in project.get("premisas", {}).get("premisas", [])],
        "premisa_elegida": project.get("premisa_elegida"),
        "preparado": "escaleta" in project,
        "agotado": project.get("revision", {}).get("agotado", False),
        "puede_revisar": _revision_literal_recuperable(project),
    }
    if project["entregado"]:
        script = project.get("edicion", project["guion"])
        result["guion"] = script["parrafos"]
        result["version"] = script.get("version", 0)
        result["media"] = project.get("media", {})
        if "trazabilidad" in script:
            result["trazabilidad"] = (
                script["trazabilidad"] if not result["version"] else None
            )
        result["afirmaciones"] = project.get("persona", {}).get("afirmaciones", {})
        result["cobertura"] = project.get("persona", {}).get("cobertura")
        result["revision_humana"] = [
            record for record in project.get("revision_humana", [])
            if record["version"] == result["version"]
        ]
        if not result["version"]:
            qa = project.get("qa", {})
            result["qa"] = {key: qa[key] for key in (
                "duracion", "realizabilidad", "avisos_estimacion", "lista_brief",
                "revision_con_evidencia", "revision_creativa",
            ) if key in qa}
    return result


def _record_error(directory, action, kind):
    try:
        errors = _read(directory, "errors")
    except FileNotFoundError:
        errors = []
    errors.append({"fase": action, "tipo": kind})
    _write(directory, "errors", errors)


def _research(brief):
    try:
        return p1_research.ejecutar(brief)
    except Exception:
        return {
            "competencia": {"modo_solicitado": brief["competencia"]["modo"], "de_marca": [],
                            "de_feed": [], "sin_datos": True},
            "mercado": {"tendencias": []},
            "oportunidad": {"texto": "La búsqueda no estuvo disponible. Análisis inferido.",
                            "nivel": "T4"},
            "fuentes_total": 0,
            "sin_busqueda": True,
            "dossier_referencias": brief.get("dossier_referencias") or referencias.congelar(brief),
        }


def _advance(directory, action, data):
    project = _project(directory)
    brief = project["brief"]
    if action == "investigar" and "research" not in project:
        result = _research(brief)
        if result.get("sin_busqueda") and llm.hay_gemini():
            _record_error(directory, action, "Búsqueda no disponible")
        _write(directory, "research", result)
    elif action == "persona" and "research" in project and "persona" not in project:
        persona = p2_persona.ejecutar(brief, project["research"])
        persona["version"] = 1
        _write(directory, "persona_v1", persona)
        _write(directory, "persona", persona)
    elif action == "audiencia" and "persona" in project and "premisas" not in project:
        current = project["persona"]
        if data.get("version") != current.get("version", 1):
            raise RequestError("409 Conflict", "La ficha cambió. Reabre el proyecto antes de guardar.")
        try:
            updated, diff = audience.editar(current, data.get("campos"), brief)
        except contracts.ContratoInvalido as exc:
            raise RequestError("400 Bad Request", str(exc)) from exc
        if diff:
            _save_persona(directory, current, updated, diff)
    elif action == "premisas" and "persona" in project and "escaleta" not in project:
        count = project["regeneraciones"]
        if "premisas" in project and count >= 3:
            raise RequestError("409 Conflict", "Ya usaste las tres regeneraciones de premisas.")
        persona = project["persona"]
        if "premisas" not in project and data.get("frase") is not None:
            phrase = data["frase"]
            if phrase not in persona["lenguaje"]["diria"]:
                raise RequestError("400 Bad Request", "Elige una frase de la ficha.")
            persona = {**persona, "frase_validada": {"texto": phrase, "nivel": "T1"}}
            _save_persona(directory, project["persona"], persona,
                          {"frase_validada": persona["frase_validada"]})
        if "premisas" in project:
            _write(directory, "estado", {"regeneraciones": count + 1})
        context = p2_persona.inyectar(brief, persona)
        if persona.get("frase_validada"):
            context += "\n\n" + json.dumps(persona["frase_validada"], ensure_ascii=False)
        result = p3_premisas.ejecutar(brief, persona, project["research"], context)
        _write(directory, "premisas", result)
    elif action == "revisar" and project["entregado"]:
        script = project.get("edicion", project["guion"])
        version = script.get("version", 0)
        if data.get("version") != version:
            raise RequestError("409 Conflict", "Hay una edición más reciente. Reabre el proyecto.")
        try:
            review = p6_qa.revision_humana(data, project.get("persona", {}))
        except contracts.ContratoInvalido as exc:
            raise RequestError("400 Bad Request", str(exc)) from exc
        history = project.get("revision_humana", [])
        _write(directory, "revision_humana", [*history, {**review, "version": version}])
    elif action == "editar":
        _edit(directory, project, data)
    elif action in {"voz", "canva"} and project["entregado"]:
        script = project.get("edicion", project["guion"])
        if data.get("version") != script.get("version", 0):
            raise RequestError("409 Conflict", "Hay una edición más reciente. Reabre el proyecto.")
        try:
            services.production(directory, brief, script, action)
        except llm.ServicioNoDisponible as exc:
            raise RequestError("503 Service Unavailable", str(exc)) from exc
    elif action in {"escaleta", "preparar"} and "premisas" in project:
        _script(directory, project, action, data)
    else:
        raise RequestError("409 Conflict", "La acción no está disponible en esta fase.")
    return _public(_project(directory))


def _save_persona(directory, previous, updated, diff):
    version = previous.get("version", 1) + 1
    updated["version"] = version
    _write(directory, f"persona_v{version}", updated)
    record = {"desde_version": version - 1, "version": version, "campos": diff}
    _write(directory, f"persona_diff_v{version}", record)
    _write(directory, "persona_diff", record)
    _write(directory, "persona", updated)


def _script(directory, project, action, data):
    brief, persona = project["brief"], project["persona"]
    selected = data.get("premisa") if action == "escaleta" else project.get("premisa_elegida")
    premise = next((p for p in project["premisas"]["premisas"] if p["id"] == selected), None)
    if premise is None:
        raise RequestError("400 Bad Request", "Elige una de las tres premisas.")
    context = p2_persona.inyectar(brief, persona)
    if persona.get("frase_validada"):
        context += "\n\n" + json.dumps(persona["frase_validada"], ensure_ascii=False)
    state = _read(directory, "estado")
    if action == "escaleta" and "escaleta" not in project:
        _write(directory, "estado", {**state, "premisa_elegida": selected})
        _write(directory, "escaleta", p4_escaleta.ejecutar(brief, premise, context))
    elif action == "preparar" and "escaleta" in project:
        _review_pass(directory, project, premise, context)
    else:
        raise RequestError("409 Conflict", "La acción no está disponible en esta fase.")


MIN_REVIEWS = 3
MAX_REVIEWS = 5


def _review_pass(directory, project, premise, context):
    previous = project.get("revision", {})
    if _revision_literal_recuperable(project):
        _write(directory, "revision_mensaje_literal", previous)
        previous = {"pasadas": [], "candidato": previous["candidato"], "version_mensaje": 2}
        _write(directory, "revision", previous)
    if project["entregado"] or previous.get("agotado"):
        return
    history = previous.get("pasadas", [])
    if len(history) >= MAX_REVIEWS:
        _write(directory, "revision", {**previous, "agotado": True})
        return
    brief, person, outline = project["brief"], project["persona"], project["escaleta"]
    candidate = previous.get("candidato") or project.get("guion")
    findings = history[-1]["hallazgos"] if history else []
    try:
        if not candidate or findings:
            correction = None
            if findings:
                correction = json.dumps({"hallazgos": findings, "guion_anterior": candidate},
                                        ensure_ascii=False)
            candidate = p5_guion.ejecutar(brief, person, premise, outline, context,
                                         correccion=correction)
        review = p6_qa.revisar_brief(brief, person, candidate, outline)
    except (contracts.ContratoInvalido, llm.RespuestaInvalida) as exc:
        review = {"hallazgos": [f"Respuesta estructurada inválida ({type(exc).__name__})."]}
    if review["hallazgos"]:
        checks = [name for name, value in review.get("lista_brief", {}).items() if not value["ok"]]
        semantic = [key for key in p6_qa.CRITERIOS
                    if any(item.startswith(f"Verificar {key}.") for item in review["hallazgos"])]
        logging.getLogger(__name__).warning(
            "QA pass=%d checks=%s semantic=%s other=%d",
            len(history) + 1, checks, semantic, len(review["hallazgos"]) - len(checks) - len(semantic),
        )
    history = [*history, review]
    approved = len(history) >= MIN_REVIEWS and not review["hallazgos"]
    if approved:
        _write(directory, "guion", candidate)
        _write(directory, "qa", review)
    _write(directory, "revision", {"pasadas": history, "candidato": candidate,
                                   "version_mensaje": 2,
                                   "aprobado": approved,
                                   "agotado": len(history) >= MAX_REVIEWS and not approved})


def _edit(directory, project, data):
    if not project["entregado"]:
        raise RequestError("409 Conflict", "El guion aún se está preparando.")
    script = project.get("edicion", project["guion"])
    version = script.get("version", 0)
    if data.get("version") != version:
        raise RequestError("409 Conflict", "Hay una edición más reciente. Reabre el proyecto.")
    texts = data.get("textos")
    if (not isinstance(texts, list) or len(texts) != len(script["parrafos"])
            or any(not isinstance(t, str) or not t.strip() for t in texts)):
        raise RequestError("400 Bad Request", "Completa el texto de todos los párrafos.")
    edited = {**script, "version": version + 1,
              "parrafos": [{**p, "texto": t.strip()} for p, t in zip(script["parrafos"], texts)]}
    edited.pop("trazabilidad", None)
    _write(directory, "edicion", edited)


def _body(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if not 0 < length <= MAX_BODY:
        raise RequestError("413 Payload Too Large", "El tamaño del formulario no es válido.")
    data = json.loads(environ["wsgi.input"].read(length))
    if not isinstance(data, dict):
        raise ValueError
    return data


def _route(environ):
    path = environ.get("PATH_INFO", "")
    method = environ["REQUEST_METHOD"]
    viewer = environ.get("HTTP_X_STORIDEX_VIEWER", "")
    if not re.fullmatch(r"[0-9a-f]{64}", viewer):
        raise RequestError("403 Forbidden", "Inicia sesión para acceder a tus proyectos.")
    root = _root() / "usuarios" / viewer
    if path == "/api/proyectos" and method == "POST":
        if not (llm.DRY or llm.hay_llave()):
            raise RequestError("503 Service Unavailable", "Falta configurar el servicio de redacción.")
        brief = _body(environ)
        try:
            contracts.brief(brief)
        except contracts.ContratoInvalido as exc:
            raise RequestError("400 Bad Request", str(exc)) from exc
        _, directory = p0_brief.ejecutar(brief, str(root), identificador=uuid4().hex)
        directory = Path(directory)
        _write(directory, "estado", {"regeneraciones": 0})
        return _public(_project(directory))
    if path == "/api/proyectos" and method == "GET":
        projects = sorted(root.glob("*/estado.json"), key=lambda file: file.stat().st_mtime,
                          reverse=True)
        return [{"id": file.parent.name, "marca": _read(file.parent, "brief")["marca"]["nombre"]}
                for file in projects if re.fullmatch(r"[0-9a-f]{32}", file.parent.name)]
    match = re.fullmatch(r"/api/proyectos/([0-9a-f]{32})(?:/([a-z]+))?", path)
    if not match or not (directory := root / match[1]).is_dir():
        raise RequestError("404 Not Found", "Proyecto o acción no encontrado.")
    action = match[2]
    with _locked(directory):
        if method == "GET" and action is None:
            return _public(_project(directory))
        if method == "GET" and action == "pdf":
            project = _project(directory)
            if project["entregado"]:
                with TemporaryDirectory() as folder:
                    pdf = Path(folder) / "guion.pdf"
                    export_pdf.generar(project.get("edicion", project["guion"]),
                                       project["brief"], str(pdf))
                    return pdf.read_bytes(), "application/pdf", "guion.pdf"
        if method == "GET" and action == "fdx":
            project = _project(directory)
            if project["entregado"]:
                return (export_fdx.generar(project.get("edicion", project["guion"]),
                                           project["brief"]), "application/xml", "guion.fdx")
        if method == "GET" and action == "audio":
            project = _project(directory)
            if project["entregado"]:
                script = project.get("edicion", project["guion"])
                audio = directory / f"speech_{services.media_id(script)}.mp3"
                if (services.media_state(directory, script).get("elevenlabs", {}).get("status")
                        == "success" and audio.is_file()):
                    return audio.read_bytes(), "audio/mpeg", "lectura-sintetica.mp3"
        if method == "POST" and action in {
            "investigar", "persona", "audiencia", "premisas", "escaleta", "preparar", "editar", "revisar", "voz", "canva",
        }:
            data = _body(environ)
            try:
                with llm.auditar(directory):
                    return _advance(directory, action, data)
            except RequestError:
                raise
            except llm.CosteExcedido as exc:
                _record_error(directory, action, type(exc).__name__)
                raise RequestError("409 Conflict", "Se alcanzó el presupuesto estimado de este proyecto. "
                                   "Se conserva el trabajo y su diagnóstico; no se harán más llamadas.") from exc
            except Exception as exc:
                _record_error(directory, action, type(exc).__name__)
                raise RequestError("502 Bad Gateway", "No pudimos completar la operación. Inténtalo de nuevo.") from exc
    raise RequestError("404 Not Found", "Proyecto o acción no encontrado.")


def application(environ, start_response):
    secret = os.environ.get("STORIDEX_PROXY_SECRET", "")
    authorization = environ.get("HTTP_AUTHORIZATION", "")
    status = "200 OK"
    headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")]
    try:
        if not secret or not hmac.compare_digest(authorization.encode(), f"Bearer {secret}".encode()):
            raise RequestError("403 Forbidden", "Acceso denegado.")
        result = _route(environ)
    except RequestError as exc:
        status, result = exc.status, {"error": str(exc)}
    except (ValueError, KeyError, TypeError, AttributeError):
        status, result = "400 Bad Request", {"error": "El formulario no es válido."}
    except Exception:
        status, result = "500 Internal Server Error", {"error": "El servicio no pudo completar la acción."}
    if isinstance(result, tuple):
        body, mime, filename = result
        headers.append(("Content-Disposition", f'attachment; filename="{filename}"'))
    else:
        body = json.dumps(result, ensure_ascii=False).encode()
        mime = "application/json; charset=utf-8"
    start_response(status, headers + [("Content-Type", mime), ("Content-Length", str(len(body)))])
    return [body]
