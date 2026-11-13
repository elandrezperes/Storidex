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

import json
import os
import re
import time

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


# ------------------------------------------------------------------ estado
def hay_llave() -> bool:
    return bool(_cfg("OPENAI_API_KEY"))


def hay_gemini() -> bool:
    return bool(_cfg("GEMINI_API_KEY"))


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
        return Respuesta(json.dumps(seco, ensure_ascii=False, indent=2), "prueba")

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
            if coste > MAX_COST:
                raise CosteExcedido(
                    f"Esta generación costaría {coste:.2f} USD, por encima del techo "
                    f"de {MAX_COST:.2f} USD. Revisa STORIDEX_MAX_COST_USD.")
            return Respuesta(_json_limpio(texto), nombre, ent, sal, coste=coste)
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
    try:
        for cand in r.candidates or []:
            gm = getattr(cand, "grounding_metadata", None)
            for chunk in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    fuentes.append(web.uri)
    except Exception:  # noqa: BLE001
        pass

    ent = getattr(getattr(r, "usage_metadata", None), "prompt_token_count", 0) or 0
    sal = getattr(getattr(r, "usage_metadata", None), "candidates_token_count", 0) or 0
    return Respuesta(_json_limpio(r.text or "{}"), MODEL_RESEARCH, ent, sal, fuentes,
                     _coste(MODEL_RESEARCH, ent, sal))


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


def cargar_prompt(nombre: str) -> str:
    ruta = os.path.join(os.path.dirname(__file__), "prompts", nombre)
    with open(ruta, encoding="utf-8") as f:
        return f.read()



