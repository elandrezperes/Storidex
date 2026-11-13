"""Acceso y control de gasto.

Cuando la aplicación está publicada, cualquiera con el enlace puede generar
guiones con TU llave. Este módulo pone dos barreras:

1. Clave de acceso: si está configurada, hay que escribirla para entrar.
2. Tope por sesión: número máximo de guiones por visita, para que un curioso
   no consuma el saldo de golpe.

Si no hay clave configurada, la app queda abierta (uso local).
"""
from __future__ import annotations

import os


def _cfg(nombre: str, defecto: str = "") -> str:
    """Lee de variable de entorno y, si no existe, de los secretos de Streamlit."""
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


def clave_configurada() -> str:
    """Clave de acceso exigida. Vacía = acceso libre."""
    return _cfg("STORIDEX_CLAVE")


def hay_que_autenticarse() -> bool:
    return bool(clave_configurada())


def verificar(intento: str) -> bool:
    """Compara lo que escribió el usuario con la clave configurada."""
    esperada = clave_configurada()
    if not esperada:
        return True
    return (intento or "").strip() == esperada


def tope_sesion() -> int:
    """Guiones permitidos por sesión. 0 = sin límite."""
    try:
        return int(_cfg("STORIDEX_TOPE_SESION", "5"))
    except ValueError:
        return 5


def puede_generar(usadas: int) -> tuple[bool, str]:
    """¿Queda margen en esta sesión?"""
    tope = tope_sesion()
    if tope <= 0:
        return True, ""
    if usadas < tope:
        restantes = tope - usadas
        aviso = (f"Te {'queda' if restantes == 1 else 'quedan'} {restantes} "
                 f"guion{'es' if restantes != 1 else ''} en esta sesión.")
        return True, aviso
    return False, (f"Se alcanzó el tope de {tope} "
                   f"guion{'es' if tope != 1 else ''} por sesión. "
                   f"Recarga la página para empezar de nuevo.")


