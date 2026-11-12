"""Actualizaciones desde las versiones («Releases») publicadas en GitHub.

- Solo se consulta GitHub cuando el usuario lo pide o al abrir Ajustes; no se envía
  ningún dato del colegio, solo se pregunta cuál es la última versión publicada.
- La instalación descarga el .zip de la versión, cierra la aplicación, sustituye los
  archivos del programa y la vuelve a abrir. Los datos (carpeta %APPDATA%\\MundoPTAL)
  no se tocan.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .config import APP_VERSION

REPO = os.environ.get("MUNDOPTAL_REPO", "ggonzalezmoro/Mundo-PT-AL")
NOMBRE_ZIP = "MundoPTAL-windows.zip"
EXE = "MundoPTAL.exe"


class ErrorActualizacion(RuntimeError):
    pass


def version_tupla(texto: str) -> tuple[int, ...]:
    numeros = re.findall(r"\d+", texto or "")
    return tuple(int(n) for n in numeros[:3]) or (0,)


def es_mas_nueva(remota: str, local: str | None = None) -> bool:
    return version_tupla(remota) > version_tupla(local or APP_VERSION)


def puede_instalar() -> bool:
    """Solo el ejecutable de Windows se puede sustituir a sí mismo."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _pedir(url: str, timeout: float = 10):
    req = urllib.request.Request(url, headers={
        "User-Agent": "MundoPTAL-actualizador",
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def comprobar(abrir=_pedir) -> dict:
    """Devuelve la última versión publicada y si es más nueva que la instalada."""
    try:
        with abrir(f"https://api.github.com/repos/{REPO}/releases/latest") as r:
            datos = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ErrorActualizacion("Todavía no hay ninguna versión publicada.") from e
        raise ErrorActualizacion(f"GitHub ha respondido con un error ({e.code}). Prueba más tarde.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorActualizacion("No se ha podido conectar con GitHub. Comprueba la conexión a Internet.") from e
    etiqueta = datos.get("tag_name") or ""
    zip_url = next((a.get("browser_download_url") for a in datos.get("assets", [])
                    if a.get("name") == NOMBRE_ZIP), None)
    return {
        "actual": APP_VERSION,
        "ultima": etiqueta.lstrip("vV"),
        "hay_nueva": bool(zip_url) and es_mas_nueva(etiqueta),
        "notas": (datos.get("body") or "").strip(),
        "fecha": (datos.get("published_at") or "")[:10],
        "url": zip_url,
        "puede_instalar": puede_instalar(),
    }


def carpeta_programa() -> Path:
    return Path(sys.executable).resolve().parent


def _buscar_nueva(raiz: Path) -> Path:
    """Carpeta del .zip que contiene MundoPTAL.exe (normalmente «MundoPTAL»)."""
    for exe in sorted(raiz.rglob(EXE), key=lambda p: len(p.parts)):
        return exe.parent
    raise ErrorActualizacion("El archivo descargado no contiene el programa.")


def guion_reemplazo(pid: int, origen: Path, destino: Path, temporal: Path) -> str:
    """Guion .bat que espera a que se cierre la aplicación, copia la versión nueva y la abre."""
    return "\r\n".join([
        "@echo off",
        "chcp 65001 >nul",
        ":espera",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  ping -n 2 127.0.0.1 >nul",
        "  goto espera",
        ")",
        f'robocopy "{origen}" "{destino}" /E /R:10 /W:2 /NFL /NDL /NJH /NJS /NP >nul',
        f'if errorlevel 8 echo No se pudo copiar la version nueva > "{temporal}\\error.txt"',
        f'start "" "{destino / EXE}"',
        f'rmdir /s /q "{temporal / "nuevo"}"',
        f'del /q "{temporal / NOMBRE_ZIP}"',
        "",
    ])


def instalar(url: str, abrir=_pedir, salir=None) -> dict:
    """Descarga la versión nueva, prepara el reemplazo y cierra la aplicación."""
    if not puede_instalar():
        raise ErrorActualizacion("La instalación automática solo funciona en el programa de Windows.")
    if not url or not url.startswith("https://github.com/"):
        raise ErrorActualizacion("Dirección de descarga no válida.")
    destino = carpeta_programa()
    if not (destino / EXE).exists():
        raise ErrorActualizacion("No se encuentra la carpeta del programa.")
    temporal = Path(tempfile.mkdtemp(prefix="MundoPTAL_act_"))
    archivo = temporal / NOMBRE_ZIP
    try:
        with abrir(url, timeout=60) as r, open(archivo, "wb") as f:
            while bloque := r.read(1024 * 1024):
                f.write(bloque)
        with zipfile.ZipFile(archivo) as z:
            if z.testzip() is not None:
                raise ErrorActualizacion("El archivo descargado está dañado. Prueba otra vez.")
            z.extractall(temporal / "nuevo")
    except (urllib.error.URLError, OSError, zipfile.BadZipFile) as e:
        raise ErrorActualizacion("No se ha podido descargar la versión nueva. Prueba otra vez.") from e
    origen = _buscar_nueva(temporal / "nuevo")
    guion = temporal / "actualizar.bat"
    guion.write_text(guion_reemplazo(os.getpid(), origen, destino, temporal), encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(guion)], cwd=str(temporal), close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    def _cerrar():
        time.sleep(1.5)  # deja que la respuesta llegue a la ventana
        (salir or (lambda: os._exit(0)))()

    threading.Thread(target=_cerrar, daemon=True).start()
    return {"ok": True}
