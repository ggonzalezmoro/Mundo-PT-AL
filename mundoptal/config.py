"""Rutas y constantes de la aplicación.

Todo se guarda en el propio equipo del maestro:
  Windows: %APPDATA%\\MundoPTAL\\mundo_ptal.db
  Otros:   ~/.mundoptal/mundo_ptal.db
Se puede cambiar con la variable de entorno MUNDOPTAL_DATA_DIR.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Mundo PT-AL"
APP_VERSION = "0.4.2"
COLEGIO = "Colegio San Ignacio de Loyola"

# Escala de evaluación de las ACIs (orden de menor a mayor logro)
ESCALA = ["NI", "I", "ED", "ED+", "C"]
ESCALA_TEXTO = {
    "NI": "No iniciado",
    "I": "Iniciado",
    "ED": "En desarrollo",
    "ED+": "En desarrollo avanzado",
    "C": "Conseguido",
}

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


def base_dir() -> Path:
    """Carpeta donde están los recursos (static, modelos) tanto en desarrollo
    como dentro del ejecutable de PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def static_dir() -> Path:
    return base_dir() / "static"


def data_dir() -> Path:
    env = os.environ.get("MUNDOPTAL_DATA_DIR")
    if env:
        p = Path(env)
    elif sys.platform == "win32":
        p = Path(os.environ.get("APPDATA", Path.home())) / "MundoPTAL"
    else:
        p = Path.home() / ".mundoptal"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "mundo_ptal.db"


def model_dirs() -> list[Path]:
    """Lugares donde buscar el modelo de voz Vosk en español."""
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else base_dir().parent
    return [
        base_dir() / "models",
        exe_dir / "models",
        data_dir() / "models",
    ]
