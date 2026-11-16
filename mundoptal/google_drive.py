"""Llevar el material a Google Drive en los ordenadores sin Word ni PowerPoint, sin cuentas ni claves.

No se usa la API de Google (no hay acceso a un cliente OAuth del colegio). En su lugar:
- Si está instalado «Google Drive para ordenadores», su unidad (G:\\Mi unidad…) se detecta y el
  archivo se copia a la carpeta «material mundo pt al» de Mi unidad: Drive lo sube solo y se abre
  esa carpeta en Chrome, donde un doble clic lo abre con Documentos o Presentaciones de Google.
- Si no, se abre la carpeta de Drive en Chrome y el Explorador con el archivo seleccionado,
  para arrastrarlo a la ventana de Drive.
- Chrome se busca en sus rutas de instalación; si no está, se usa el navegador predeterminado.
"""
from __future__ import annotations

import os
import re
import shutil
import string
import subprocess
import unicodedata
import webbrowser
from pathlib import Path

NOMBRE_CARPETA = "material mundo pt al"
URL_MI_UNIDAD = "https://drive.google.com/drive/my-drive"
NOMBRES_MI_UNIDAD = ("Mi unidad", "My Drive", "La meva unitat", "Nire unitatea", "A miña unidade")


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", texto)


# ------------------------------------------------------------------ navegador
def rutas_chrome() -> list[Path]:
    rutas = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "PROGRAMW6432"):
        base = os.environ.get(var)
        if base:
            rutas.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    return rutas


def chrome() -> Path | None:
    return next((r for r in rutas_chrome() if r.is_file()), None)


def abrir_navegador(url: str) -> str:
    """Abre la dirección en Chrome (o en el navegador predeterminado). Devuelve cuál se ha usado."""
    exe = chrome()
    if exe:
        try:
            # Sin consola (exe con ventana): las tres salidas a DEVNULL para evitar «identificador no válido»
            subprocess.Popen([str(exe), url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,  # noqa: S603
                             stderr=subprocess.DEVNULL, close_fds=True)
            return "chrome"
        except OSError:
            pass
    if hasattr(os, "startfile"):
        try:
            os.startfile(url)  # noqa: S606 - navegador predeterminado de Windows
            return "predeterminado"
        except OSError:
            pass
    return "predeterminado" if webbrowser.open(url) else ""


# ------------------------------------------------------------------ Google Drive para ordenadores
def unidades_drive() -> list[Path]:
    """Carpetas «Mi unidad» de Google Drive para ordenadores (G:\\Mi unidad…) en este equipo.
    MUNDOPTAL_MI_UNIDAD la fija en las pruebas automáticas."""
    fija = os.environ.get("MUNDOPTAL_MI_UNIDAD")
    if fija is not None:
        return [Path(fija)] if fija and Path(fija).is_dir() else []
    encontradas = []
    if os.name == "nt":
        for letra in string.ascii_uppercase[3:]:  # de D: a Z:
            raiz = Path(f"{letra}:\\")
            try:
                if not raiz.exists():
                    continue
                encontradas += [raiz / n for n in NOMBRES_MI_UNIDAD if (raiz / n).is_dir()]
            except OSError:
                continue
    for n in NOMBRES_MI_UNIDAD:  # instalaciones antiguas («Copia de seguridad y sincronización»)
        p = Path.home() / "Google Drive" / n
        if p.is_dir():
            encontradas.append(p)
    return encontradas


def mi_unidad(preferida: str = "") -> Path | None:
    if preferida and Path(preferida).is_dir():
        return Path(preferida)
    unidades = unidades_drive()
    return unidades[0] if unidades else None


def carpeta_material_drive(unidad: Path) -> Path:
    """Busca «material mundo pt al» (o «material mundo pt/al», con o sin mayúsculas) en Mi unidad y en sus
    subcarpetas (por ejemplo «cuenta personal»). Si no existe, la crea en Mi unidad."""
    objetivo = _normalizar(NOMBRE_CARPETA)
    nivel = [unidad]
    for _ in range(3):
        siguiente = []
        for carpeta in nivel:
            try:
                hijos = [h for h in carpeta.iterdir() if h.is_dir() and not h.name.startswith(".")]
            except OSError:
                continue
            for h in hijos:
                if _normalizar(h.name) == objetivo:
                    return h
            siguiente += hijos[:200]
        nivel = siguiente
    destino = unidad / NOMBRE_CARPETA
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def copiar_a_drive(ruta: Path, unidad: Path) -> Path:
    """Copia el material a la carpeta de Drive (Drive para ordenadores lo sube solo)."""
    carpeta = carpeta_material_drive(unidad)
    destino = carpeta / ruta.name
    if not destino.exists() or destino.stat().st_size != ruta.stat().st_size:
        shutil.copy2(ruta, destino)
    return destino


def url_busqueda(nombre: str) -> str:
    from urllib.parse import quote
    return "https://drive.google.com/drive/search?q=" + quote(nombre)


def es_url_drive(url: str) -> bool:
    return bool(re.match(r"^https://drive\.google\.com/", (url or "").strip()))
