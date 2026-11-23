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


SUFIJO_VIEJO = ".viejo-"  # p. ej. «MundoPTAL.exe.viejo-20261123220500»


def _ps(texto) -> str:
    return "'" + str(texto).replace("'", "''") + "'"


def guion_apartar(origen: Path, destino: Path, sello: str) -> str:
    """Guion de PowerShell para sustituir archivos que están en uso SIN cerrar a nadie.

    Claude Desktop tiene abierto «MundoPTAL.exe --mcp» (el servidor de material) y eso
    bloquea el .exe y sus DLL: no se pueden sobrescribir, pero Windows sí deja
    renombrarlos. Con «-Modo apartar» cada archivo bloqueado que la versión nueva trae
    se renombra a «<nombre>.viejo-<sello>» y así robocopy puede poner el nuevo en su
    sitio; las copias abiertas siguen funcionando con el archivo viejo hasta que se
    reinician. «-Modo restaurar» deshace el cambio si la copia ha fallado, para que el
    programa nunca se quede sin su .exe. Los restos se borran al abrir la app
    (limpiar_restos).
    """
    return "\r\n".join([
        "param([string]$Modo = 'apartar')",
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"$origen = {_ps(str(origen).rstrip(chr(92) + '/'))}",
        f"$destino = {_ps(str(destino).rstrip(chr(92) + '/'))}",
        f"$sufijo = {_ps(SUFIJO_VIEJO + sello)}",
        "if ($Modo -eq 'restaurar') {",
        "  Get-ChildItem -LiteralPath $destino -Recurse -File -Filter ('*' + $sufijo) | ForEach-Object {",
        "    $original = $_.FullName.Substring(0, $_.FullName.Length - $sufijo.Length)",
        "    if (-not (Test-Path -LiteralPath $original)) { Rename-Item -LiteralPath $_.FullName -NewName (Split-Path $original -Leaf) }",
        "  }",
        "  exit 0",
        "}",
        "Get-ChildItem -LiteralPath $origen -Recurse -File | ForEach-Object {",
        "  $d = Join-Path $destino $_.FullName.Substring($origen.Length).TrimStart('\\')",
        "  if (Test-Path -LiteralPath $d) {",
        "    try { $s = [IO.File]::Open($d, 'Open', 'ReadWrite', 'None'); $s.Close() }",
        "    catch { Rename-Item -LiteralPath $d -NewName ((Split-Path $d -Leaf) + $sufijo) }",
        "  }",
        "}",
        "",
    ])


def limpiar_restos(carpeta: Path | None = None) -> int:
    """Borra los archivos «.viejo-…» que dejó una actualización. Los que siguen en uso
    (p. ej. por un «--mcp» que aún no se ha reiniciado) se quedan para la próxima vez."""
    if carpeta is None:
        if not puede_instalar():
            return 0
        carpeta = carpeta_programa()
    borrados = 0
    for f in Path(carpeta).rglob(f"*{SUFIJO_VIEJO}*"):
        try:
            if f.is_file():
                f.unlink()
                borrados += 1
        except OSError:
            pass
    return borrados


def guion_reemplazo(pid: int, origen: Path, destino: Path, temporal: Path) -> str:
    """Guion .bat que espera a que se cierre la aplicación, aparta los archivos en uso
    (sin cerrar ningún proceso), copia la versión nueva y la abre."""
    ps = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{temporal / "apartar.ps1"}"'
    return "\r\n".join([
        "@echo off",
        "chcp 65001 >nul",
        ":espera",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  ping -n 2 127.0.0.1 >nul",
        "  goto espera",
        ")",
        f"{ps} -Modo apartar >nul 2>&1",
        f'robocopy "{origen}" "{destino}" /E /R:3 /W:2 /NFL /NDL /NJH /NJS /NP >nul',
        "if errorlevel 8 (",
        f'  echo No se pudo copiar la version nueva > "{temporal}\\error.txt"',
        f"  {ps} -Modo restaurar >nul 2>&1",
        ")",
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
    sello = time.strftime("%Y%m%d%H%M%S")
    # newline="": los guiones ya llevan \r\n. PowerShell 5.1 necesita el BOM para las tildes.
    (temporal / "apartar.ps1").write_text(guion_apartar(origen, destino, sello),
                                          encoding="utf-8-sig", newline="")
    guion = temporal / "actualizar.bat"
    guion.write_text(guion_reemplazo(os.getpid(), origen, destino, temporal),
                     encoding="utf-8", newline="")
    subprocess.Popen(
        ["cmd", "/c", str(guion)], cwd=str(temporal), close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    def _cerrar():
        time.sleep(1.5)  # deja que la respuesta llegue a la ventana
        (salir or (lambda: os._exit(0)))()

    threading.Thread(target=_cerrar, daemon=True).start()
    return {"ok": True}
