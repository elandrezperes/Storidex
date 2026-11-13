"""Niveles de procedencia T1–T4 y su propagación.

Regla del proyecto (AGENTS.md §6.4):
- el nivel se asigna POR BLOQUE, no por ficha;
- el nivel del guion es el PEOR de los campos de los que dependió;
- nunca se bloquea por falta de datos: se degrada y se declara.
"""
from __future__ import annotations

T1 = "T1"  # declarado por la marca o el usuario
T2 = "T2"  # público de la marca: web, redes, reseñas
T3 = "T3"  # mercado: búsqueda fundamentada, tendencias, competencia
T4 = "T4"  # inferencia del modelo

NIVELES = (T1, T2, T3, T4)

ETIQUETAS = {
    T1: "declarado",
    T2: "fuente de la marca",
    T3: "fuente de mercado",
    T4: "inferido",
}


def peor(niveles) -> str:
    """Devuelve el nivel más débil de una colección."""
    niveles = [n for n in niveles if n in NIVELES]
    if not niveles:
        return T4
    return max(niveles, key=NIVELES.index)


def es_verificado(nivel: str) -> bool:
    """T1–T3 cuentan como sostenido en fuente; T4 no."""
    return nivel in (T1, T2, T3)


def confianza(persona: dict) -> dict:
    """Proporción de bloques de la ficha sostenidos en fuente."""
    bloques = ["perfil", "consumo", "conflicto", "lenguaje", "anti_persona"]
    niveles = [persona.get(b, {}).get("nivel", T4) for b in bloques]
    con_fuente = sum(1 for n in niveles if es_verificado(n))
    return {
        "score": round(con_fuente / len(bloques), 2),
        "campos_con_fuente": con_fuente,
        "campos_totales": len(bloques),
        "nivel_global": peor(niveles),
    }


def resumen(persona: dict) -> str:
    """Frase corta para mostrar en la interfaz."""
    c = confianza(persona)
    if c["score"] == 0:
        return "Ficha enteramente inferida: sin fuentes, el guion se marcará como inferido."
    if c["score"] < 0.4:
        return f"Ficha débil ({int(c['score']*100)}% sostenida en fuentes). Añade capturas o entrevistas."
    if c["score"] < 0.8:
        return f"Ficha parcialmente sostenida ({int(c['score']*100)}%)."
    return f"Ficha sólida ({int(c['score']*100)}% sostenida en fuentes)."

