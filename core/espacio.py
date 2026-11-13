"""El espacio escénico: interior/exterior, localización y momento del día.

Un encabezado de escena profesional no es texto libre: es la combinación de tres
decisiones fijas. Si se deja abierto, el modelo escribe variaciones y el formato
deja de ser heredado del oficio.

    INT. APARTAMENTO - SALA/COCINA. DÍA.

    tipo     INT | EXT | INT/EXT
    local    dónde ocurre
    momento  AMANECER | MAÑANA | DÍA | MEDIODÍA | TARDE | ATARDECER | NOCHE |
             MADRUGADA | CONTINUO
"""
from __future__ import annotations

import re
import unicodedata

TIPOS = {"INT": "Interior", "EXT": "Exterior", "INT/EXT": "Interior y exterior"}

MOMENTOS = ["AMANECER", "MAÑANA", "DÍA", "MEDIODÍA", "TARDE",
            "ATARDECER", "NOCHE", "MADRUGADA", "CONTINUO"]

ALIAS_TIPO = {
    "int": "INT", "interior": "INT", "i": "INT",
    "ext": "EXT", "exterior": "EXT", "e": "EXT",
    "int/ext": "INT/EXT", "int./ext.": "INT/EXT", "inte xt": "INT/EXT",
    "interior/exterior": "INT/EXT", "ambos": "INT/EXT", "mixto": "INT/EXT",
}

ALIAS_MOMENTO = {
    "amanecer": "AMANECER", "alba": "AMANECER", "madrugada temprana": "AMANECER",
    "mañana": "MAÑANA", "manana": "MAÑANA", "morning": "MAÑANA",
    "día": "DÍA", "dia": "DÍA", "day": "DÍA",
    "mediodía": "MEDIODÍA", "mediodia": "MEDIODÍA", "noon": "MEDIODÍA",
    "tarde": "TARDE", "afternoon": "TARDE",
    "atardecer": "ATARDECER", "ocaso": "ATARDECER", "sunset": "ATARDECER",
    "noche": "NOCHE", "night": "NOCHE", "nocturno": "NOCHE",
    "madrugada": "MADRUGADA", "night late": "MADRUGADA",
    "continuo": "CONTINUO", "continuous": "CONTINUO", "continua": "CONTINUO",
}

# momento sugerido según el rubro, para cuando el usuario deja que lo decida
# el guionista
MOMENTO_POR_RUBRO = {
    "radio": "MAÑANA", "gastronomia": "MEDIODÍA", "comercio": "TARDE",
    "servicios": "MAÑANA", "salud": "MAÑANA", "educacion": "TARDE",
    "belleza": "TARDE", "tecnologia": "MAÑANA", "turismo": "DÍA",
    "salud_animal": "MAÑANA", "otro": "DÍA",
}

TIPO_POR_RUBRO = {
    "radio": "INT", "gastronomia": "INT", "comercio": "INT",
    "servicios": "INT", "salud": "INT", "educacion": "INT",
    "belleza": "INT", "tecnologia": "INT", "turismo": "EXT",
    "salud_animal": "INT", "otro": "INT",
}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def normalizar_tipo(valor) -> str | None:
    t = _norm(valor).replace(" ", "")
    if t in ALIAS_TIPO:
        return ALIAS_TIPO[t]
    return ALIAS_TIPO.get(_norm(valor))


def normalizar_momento(valor) -> str | None:
    t = _norm(valor)
    if t in ALIAS_MOMENTO:
        return ALIAS_MOMENTO[t]
    for clave, canon in ALIAS_MOMENTO.items():
        if clave in t:
            return canon
    return None


def normalizar_local(valor: str) -> str:
    """Mayúsculas, sin puntos finales, guion entre localizaciones."""
    t = re.sub(r"\s+", " ", str(valor or "")).strip(" .")
    t = t.replace(" - ", " / ").replace("-", " / ") if "/" not in t else t
    return t.upper()


def construir(tipo: str, local: str, momento: str) -> dict:
    """Objeto de espacio con sus tres componentes ya normalizados."""
    return {
        "tipo": normalizar_tipo(tipo) or "INT",
        "local": normalizar_local(local) or "ESPACIO",
        "momento": normalizar_momento(momento) or "DÍA",
    }


def encabezado(espacio: dict) -> str:
    """Texto del encabezado, como se escribe en un guion."""
    tipo = espacio.get("tipo", "INT")
    local = espacio.get("local", "ESPACIO")
    momento = espacio.get("momento", "DÍA")
    return f"{tipo}. {local}. {momento}."


def sugerido(rubro: str, ciudad: str = "") -> dict:
    """Espacio propuesto cuando el usuario deja que lo decida el guionista."""
    tipo = TIPO_POR_RUBRO.get(rubro, "INT")
    momento = MOMENTO_POR_RUBRO.get(rubro, "DÍA")
    locales = {
        "radio": "ESTUDIO", "gastronomia": "LOCAL", "comercio": "TIENDA",
        "servicios": "OFICINA", "salud": "CONSULTORIO", "educacion": "AULA",
        "belleza": "SALÓN", "tecnologia": "OFICINA", "turismo": "EXTERIOR",
        "salud_animal": "CONSULTORIO", "otro": "ESPACIO",
    }
    return construir(tipo, locales.get(rubro, "ESPACIO"), momento)


def bloque_prompt(espacio: dict, modo: str = "fijo") -> str:
    """Instrucción para el modelo sobre el espacio escénico."""
    if modo == "fijo" and espacio:
        return (
            "ESPACIO ESCÉNICO (obligatorio, no lo cambies)\n"
            f"Tipo: {espacio['tipo']} ({TIPOS.get(espacio['tipo'], '')})\n"
            f"Localización: {espacio['local']}\n"
            f"Momento del día: {espacio['momento']}\n"
            "Todos los encabezados de escena deben repetir este espacio. "
            "No inventes otras localizaciones ni otros momentos del día.\n"
        )
    return (
        "ESPACIO ESCÉNICO (decídelo tú, con criterio de producción)\n"
        "Cada encabezado de escena debe declarar los tres componentes:\n"
        "  tipo: INT (interior), EXT (exterior) o INT/EXT (ambos)\n"
        f"  momento: {' | '.join(MOMENTOS)}\n"
        "Usa el menor número de localizaciones posible: un reel de este formato "
        "no debería cambiar de espacio más de dos veces.\n"
    )


def validar(espacio: dict) -> list[str]:
    """Problemas del espacio declarado. Lista vacía = válido."""
    problemas = []
    if not isinstance(espacio, dict):
        return ["El espacio escénico no está declarado."]
    if espacio.get("tipo") not in TIPOS:
        problemas.append(
            f"Tipo de espacio no válido: «{espacio.get('tipo')}». "
            f"Debe ser INT, EXT o INT/EXT.")
    if not str(espacio.get("local", "")).strip():
        problemas.append("La localización del espacio está vacía.")
    if espacio.get("momento") not in MOMENTOS:
        problemas.append(
            f"Momento del día no válido: «{espacio.get('momento')}». "
            f"Debe ser uno de: {', '.join(MOMENTOS)}.")
    return problemas


def extraer_del_texto(texto: str) -> dict | None:
    """Rescata el espacio si el modelo lo devolvió dentro del encabezado.

    Se parte por puntos en vez de usar una expresión regular con acentos:
    «INT. APARTAMENTO - SALA/COCINA. DÍA.» → ['INT', 'APARTAMENTO - SALA/COCINA', 'DÍA']
    También acepta prefijos como «HOOK — INT. ESTUDIO. DÍA.».
    """
    t = str(texto or "").strip()
    if not t:
        return None

    # «INT./EXT.» se parte por el punto: se protege antes de dividir
    t = re.sub(r"INT\.?\s*/\s*EXT\.?", "INT/EXT", t, flags=re.IGNORECASE)

    # localiza el token del tipo aunque venga precedido de texto
    partes = [p.strip() for p in re.split(r"[.\n]", t) if p.strip()]
    if not partes:
        return None

    inicio = None
    for i, p in enumerate(partes):
        if normalizar_tipo(p):
            inicio = i
            break
    if inicio is None:
        # puede venir «HOOK — INT. ESTUDIO. DÍA.» con el tipo pegado a la raya
        for i, p in enumerate(partes):
            m = re.search(r"\b(INT\.?\s*/\s*EXT|INT|EXT)\b\s*(.*)", p, re.IGNORECASE)
            if m:
                partes[i] = m.group(1)
                if m.group(2).strip():
                    partes.insert(i + 1, m.group(2).strip())
                inicio = i
                break
    if inicio is None or len(partes) < inicio + 3:
        return None

    tipo = normalizar_tipo(partes[inicio])
    local = partes[inicio + 1]
    momento = normalizar_momento(partes[inicio + 2])

    # el momento puede venir al final, después de varias localizaciones
    if not momento:
        for p in reversed(partes[inicio + 2:]):
            momento = normalizar_momento(p)
            if momento:
                break
    if not tipo or not momento or not local:
        return None

    return construir(tipo, local, momento)



