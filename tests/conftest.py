"""Activa el modo de pruebas antes de importar las fases o la interfaz."""
import os

os.environ.setdefault("STORIDEX_DRY_RUN", "true")
