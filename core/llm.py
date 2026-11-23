"""Único punto de acceso a los modelos.

Toda llamada pasa por aquí: control de gasto, reintentos y un único proveedor
por fase. Sin llave no hay generación: el sistema no inventa contenido.

Variables de entorno (.env):
    OPENAI_API_KEY        obligatoria para generar
    STORIDEX_MODEL_WRITE  modelo de redacción (por defecto gpt-4o)
    STORIDEX_MODEL_MID    modelo de fases intermedias (por defecto gpt-4o-mini)
    GEMINI_API_KEY        opcional: solo para investigación con búsqueda
    STORIDEX_DRY_RUN      solo para pruebas automáticas (no para uso real)
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from dotenv import load_dotenv

load_dotenv()


def _cfg(nombre: str, defecto: str = "") -> str:
    """Lee de variable de entorno y, si no existe, de los secretos de Streamlit.

    En Streamlit Community Cloud no hay archivo `.env`: las llaves se pegan en el
    panel de *Secrets*, y se leen aquí.
    """
    valor = os.getenv(nombre)
    if valor:
        return valor.strip()
    try:
        import streamlit as st

        if nombre in st.secrets:  # type: ignore[operator]
            return str(st.secrets[nombre]).strip()
    except Exception:  # noqa: BLE001
        pass
    return defecto

# ------------------------------------------------------------------ ajustes
DRY = _cfg("STORIDEX_DRY_RUN", "false").lower() in ("1", "true", "yes")

MODEL_WRITE = _cfg("STORIDEX_MODEL_WRITE", "gpt-4o")
MODEL_MID = _cfg("STORIDEX_MODEL_MID", "gpt-4o-mini")
MODEL_RESEARCH = _cfg("STORIDEX_MODEL_RESEARCH", "gemini-2.5-flash")

MAX_COST = float(_cfg("STORIDEX_MAX_COST_USD", "0.30"))

# Tarifas de referencia (USD por millón de tokens). Solo para estimar el gasto.
PRECIOS = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
}

# Si el modelo configurado no existe en la cuenta, se prueba esta cadena.
FALLBACK = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4-turbo"]


class SinLlave(RuntimeError):
    """No hay OPENAI_API_KEY configurada."""


class CosteExcedido(RuntimeError):
    """La llamada superaría el techo de gasto por generación."""


_RUN = ContextVar("storidex_run", default=None)


@contextmanager
def auditar(ruta):
    token = _RUN.set(Path(ruta) if ruta else None)
    try:
        yield
    finally:
        _RUN.reset(token)


def _guardar_json(path, data):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def _trazar(respuesta, prompt, *, cache=False, busquedas=None):
    run = _RUN.get()
    if run is not None:
        path = run / "trace.json"
        trace = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"llamadas": []}
        entrada, salida = (0, 0) if cache else (respuesta.entrada, respuesta.salida)
        trace["llamadas"].append({
            "modelo": respuesta.modelo, "prompt": getattr(prompt, "version", None),
            "tokens": {"entrada": entrada, "salida": salida},
            "costo_estimado": 0 if cache else respuesta.coste,
            "desde_cache": cache, "consultas_grounding": busquedas,
        })
        trace["tokens"] = {kind: sum(call["tokens"][kind] for call in trace["llamadas"])
                           for kind in ("entrada", "salida")}
        trace["costo_estimado"] = round(sum(call["costo_estimado"] for call in trace["llamadas"]), 8)
        trace["alcance_costo"] = "Estimación por tokens reportados; excluye infraestructura y cargos de búsqueda."
        _guardar_json(path, trace)
    return respuesta


# ------------------------------------------------------------------ estado
def hay_llave() -> bool:
    return bool((_cfg("OPENAI_API_KEY") or "").strip())


def hay_gemini() -> bool:
    return bool((_cfg("GEMINI_API_KEY") or "").strip())


def motivo_sin_llave() -> str:
    return ("No hay ninguna llave de API configurada. Sin llave, el sistema no puede "
            "escribir: no hay generación posible. Crea un archivo `.env` junto a "
            "`app.py` con la línea OPENAI_API_KEY=sk-... y reinicia la aplicación.")


# ------------------------------------------------------------------ utilidades
def _coste(modelo: str, entrada: int, salida: int) -> float:
    p_in, p_out = PRECIOS.get(modelo, (2.0, 10.0))
    return (entrada / 1_000_000) * p_in + (salida / 1_000_000) * p_out


def _json_limpio(texto: str) -> str:
    """Recorta vallas de markdown o texto alrededor del objeto JSON."""
    t = (texto or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        return t[i:j + 1]
    return t


def _cliente():
    from openai import OpenAI
    return OpenAI(api_key=_cfg("OPENAI_API_KEY"))


def _pedir_openai(prompt_sistema: str, prompt_usuario: str, modelo: str,
                  temperatura: float):
    """Una llamada. Si el modelo no existe, prueba la cadena de respaldo."""
    cliente = _cliente()
    intentos = [modelo] + [m for m in FALLBACK if m != modelo]

    ultimo = None
    for nombre in intentos:
        try:
            r = cliente.chat.completions.create(
                model=nombre,
                temperature=temperatura,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": prompt_sistema},
                          {"role": "user", "content": prompt_usuario}],
            )
            return nombre, r
        except Exception as e:  # noqa: BLE001
            texto = str(e)
            ultimo = e
            # solo se cambia de modelo si el problema es de nombre o de acceso
            if not any(k in texto.lower() for k in
                       ("model", "does not exist", "not found", "invalid_request_error")):
                raise
    raise RuntimeError(f"Ningún modelo disponible respondió. Último error: {ultimo}")


# ------------------------------------------------------------------ API pública
class Respuesta:
    def __init__(self, texto: str, modelo: str, entrada: int = 0, salida: int = 0,
                 fuentes: list[str] | None = None, coste: float = 0.0):
        self.texto = texto
        self.modelo = modelo
        self.entrada = entrada
        self.salida = salida
        self.fuentes = fuentes or []
        self.coste = coste

    def dict(self) -> dict:
        return json.loads(self.texto)


def pedir_json(prompt_sistema: str, prompt_usuario: str, *,
               modelo: str | None = None, seco: dict | None = None,
               temperatura: float = 0.8, max_reintentos: int = 1) -> Respuesta:
    """Pide una respuesta JSON al modelo. En pruebas (`DRY`) devuelve `seco`."""
    modelo = modelo or MODEL_MID

    if DRY:
        if seco is None:
            raise ValueError("En modo de prueba hay que pasar `seco`.")
        return _trazar(Respuesta(json.dumps(seco, ensure_ascii=False, indent=2), "prueba"), prompt_sistema)

    if not hay_llave():
        raise SinLlave(motivo_sin_llave())

    ultimo = None
    for intento in range(max_reintentos + 1):
        try:
            nombre, r = _pedir_openai(prompt_sistema, prompt_usuario, modelo, temperatura)
            texto = r.choices[0].message.content or "{}"
            ent = r.usage.prompt_tokens if r.usage else 0
            sal = r.usage.completion_tokens if r.usage else 0
            coste = _coste(nombre, ent, sal)
            response = _trazar(Respuesta(_json_limpio(texto), nombre, ent, sal, coste=coste),
                               prompt_sistema)
            if coste > MAX_COST:
                raise CosteExcedido(
                    f"Esta generación costaría {coste:.2f} USD, por encima del techo "
                    f"de {MAX_COST:.2f} USD. Revisa STORIDEX_MAX_COST_USD.")
            return response
        except (SinLlave, CosteExcedido):
            raise
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if intento < max_reintentos:
                time.sleep(1.5 * (intento + 1))
    raise RuntimeError(f"El modelo no respondió tras varios intentos: {ultimo}")


def investigar(prompt_sistema: str, prompt_usuario: str, *,
               seco: dict | None = None) -> Respuesta:
    """Investigación con búsqueda. Si no hay llave de Gemini, devuelve vacío.

    No se inventa nada: la fase declarará `sin_datos`.
    """
    if DRY:
        return Respuesta(json.dumps(seco or {}, ensure_ascii=False, indent=2), "prueba")

    if not hay_gemini():
        # sin Gemini no hay búsqueda fundamentada: se devuelve vacío explícito
        return Respuesta(json.dumps({
            "competencia": {"modo_solicitado": "ambas", "de_marca": [], "de_feed": [],
                            "sin_datos": True},
            "mercado": {"tendencias": []},
            "oportunidad": {"texto": "", "nivel": "T4"},
            "fuentes_total": 0,
            "sin_busqueda": True,
        }, ensure_ascii=False), "sin-busqueda")

    run = _RUN.get()
    cache_path = None
    if run is not None:
        folder = run.parent / ".research-cache"
        folder.mkdir(exist_ok=True)
        digest = sha256(json.dumps([MODEL_RESEARCH, prompt_sistema, prompt_usuario],
                                   ensure_ascii=False).encode()).hexdigest()
        cache_path = folder / f"{digest}.json"
        try:
            if time.time() - cache_path.stat().st_mtime < 86400:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                response = Respuesta(cached["texto"], MODEL_RESEARCH, fuentes=cached["fuentes"])
                return _trazar(response, prompt_sistema, cache=True, busquedas=0)
        except (FileNotFoundError, ValueError, KeyError):
            pass

    from google import genai
    from google.genai import types

    cliente = genai.Client(api_key=_cfg("GEMINI_API_KEY"))
    r = cliente.models.generate_content(
        model=MODEL_RESEARCH,
        contents=prompt_usuario,
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            response_mime_type="application/json",
        ),
    )
    fuentes: list[str] = []
    busquedas = 0
    try:
        for cand in r.candidates or []:
            gm = getattr(cand, "grounding_metadata", None)
            busquedas += len(getattr(gm, "web_search_queries", None) or [])
            for chunk in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    fuentes.append(web.uri)
    except Exception:  # noqa: BLE001
        pass

    ent = getattr(getattr(r, "usage_metadata", None), "prompt_token_count", 0) or 0
    sal = getattr(getattr(r, "usage_metadata", None), "candidates_token_count", 0) or 0
    response = _trazar(Respuesta(_json_limpio(r.text or "{}"), MODEL_RESEARCH, ent, sal, fuentes,
                                 _coste(MODEL_RESEARCH, ent, sal)),
                       prompt_sistema, busquedas=busquedas)
    if cache_path is not None and fuentes:
        try:
            valid = isinstance(response.dict(), dict)
        except ValueError:
            valid = False
        if valid:
            _guardar_json(cache_path, {"texto": response.texto, "fuentes": fuentes})
    return response


class RespuestaInvalida(RuntimeError):
    """El modelo no devolvió un JSON utilizable."""


def parsear(r: Respuesta, que: str = "la respuesta") -> dict:
    """Convierte la respuesta en dict, con un error legible si no es JSON."""
    try:
        datos = json.loads(r.texto)
    except Exception as e:  # noqa: BLE001
        raise RespuestaInvalida(
            f"El modelo no devolvió {que} en formato válido. "
            f"Vuelve a intentarlo.") from e
    if not isinstance(datos, dict):
        raise RespuestaInvalida(
            f"El modelo devolvió {que} con una forma inesperada "
            f"({type(datos).__name__} en lugar de un objeto). Vuelve a intentarlo.")
    return datos


class Prompt(str):
    """Texto del prompt con su versión para auditoría."""

    def __new__(cls, texto, version):
        value = super().__new__(cls, texto)
        value.version = version
        return value


def cargar_prompt(nombre: str) -> str:
    ruta = os.path.join(os.path.dirname(__file__), "prompts", nombre)
    with open(ruta, encoding="utf-8") as f:
        return Prompt(f.read(), nombre)


class ServicioNoDisponible(RuntimeError):
    """Error seguro para la interfaz, sin URL, cuerpo remoto ni credenciales."""


class _SinRedireccion(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def servicio_json(provider, url, *, body=None, headers=None, method=None, retry=False):
    """Transporte externo centralizado. Solo destinos fijos seleccionados por el servidor."""
    from urllib.parse import urlsplit

    allowed = {"firecrawl": "api.firecrawl.dev", "vidiq": "mcp.vidiq.com",
               "elevenlabs": "api.elevenlabs.io", "canva": "api.canva.com"}
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != allowed.get(provider)
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ServicioNoDisponible("El destino del servicio no está autorizado.")
    payload = body if isinstance(body, bytes) else (
        json.dumps(body).encode() if body is not None else None
    )
    request = Request(url, data=payload, method=method,
                      headers={"Content-Type": "application/json", **(headers or {})})
    for attempt in range(2 if retry else 1):
        try:
            with build_opener(_SinRedireccion()).open(request, timeout=18) as response:
                if "text/event-stream" in response.headers.get("Content-Type", ""):
                    total, lines, data = 0, [], {}
                    while True:
                        line = response.readline(5_000_001 - total)
                        total += len(line)
                        if total > 5_000_000:
                            raise ServicioNoDisponible("La respuesta del servicio supera el límite.")
                        if line in (b"\n", b"\r\n", b""):
                            if lines:
                                item = json.loads("\n".join(lines))
                                if item.get("id") == (body or {}).get("id") and (
                                        "result" in item or "error" in item):
                                    data = item
                                    break
                                lines = []
                            if not line:
                                break
                        elif line.startswith(b"data:"):
                            lines.append(line[5:].decode("utf-8").strip())
                else:
                    raw = response.read(5_000_001)
                    if len(raw) > 5_000_000:
                        raise ServicioNoDisponible("La respuesta del servicio supera el límite.")
                    text = raw.decode("utf-8")
                    data = json.loads(text) if text else {}
                return data, dict(response.headers)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            code = getattr(exc, "code", None)
            if attempt == 0 and retry and (code is None or code == 429 or code >= 500):
                time.sleep(1)
                continue
            raise ServicioNoDisponible("El servicio externo no está disponible. Inténtalo más tarde.") from None


def registrar_servicio(provider, status, *, units=0, cache=False):
    run = _RUN.get()
    if run is None:
        return
    path = run / "trace.json"
    trace = json.loads(path.read_text()) if path.exists() else {"llamadas": []}
    trace.setdefault("services", []).append({"provider": provider, "status": status,
        "units": units, "cached": cache, "cost_usd": None,
        "cost_note": "Cargo externo no incluido en la estimación por tokens."})
    _guardar_json(path, trace)


def error_servicio(provider):
    run = _RUN.get()
    if run is not None:
        path = run / "errors.json"
        errors = json.loads(path.read_text()) if path.exists() else []
        errors.append({"fase": "services", "provider": provider,
                       "tipo": "Servicio externo no disponible"})
        _guardar_json(path, errors)


