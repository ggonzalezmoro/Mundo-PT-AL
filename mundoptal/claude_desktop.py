"""Alta de Mundo PT-AL como servidor MCP en Claude Desktop (claude_desktop_config.json).

Se añade o actualiza solo la entrada «mundo-ptal» dentro de «mcpServers», sin tocar el
resto del archivo, y antes se guarda una copia del archivo tal como estaba. Apunta al
ejecutable que está en uso (o, en desarrollo, a este Python con -m mundoptal.mcp_server),
así funciona en cualquier ordenador donde se instale la aplicación."""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

from .config import base_dir
from .store import StoreError

ENTRADA = "mundo-ptal"


def ruta_config() -> Path:
    """%APPDATA%\\Claude\\claude_desktop_config.json. Si Claude Desktop se instaló desde la
    Microsoft Store (MSIX), Windows redirige esa carpeta a LocalCache dentro del paquete."""
    otra = os.environ.get("MUNDOPTAL_CLAUDE_CONFIG")  # solo para las pruebas automáticas
    if otra:
        return Path(otra)
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        normal = appdata / "Claude" / "claude_desktop_config.json"
        if not normal.parent.exists():
            paquetes = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Packages"
            for p in sorted(paquetes.glob("Claude_*")) if paquetes.exists() else []:
                msix = p / "LocalCache" / "Roaming" / "Claude"
                if msix.exists():
                    return msix / "claude_desktop_config.json"
        return normal
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def entrada() -> dict:
    """Cómo arrancar el servidor MCP en este ordenador."""
    if getattr(sys, "frozen", False):  # MundoPTAL.exe
        e = {"command": sys.executable, "args": ["--mcp"]}
    else:  # desde el código (desarrollo)
        e = {"command": sys.executable, "args": ["-m", "mundoptal.mcp_server"],
             "env": {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)}}
    if os.environ.get("MUNDOPTAL_DATA_DIR"):
        e.setdefault("env", {})["MUNDOPTAL_DATA_DIR"] = os.environ["MUNDOPTAL_DATA_DIR"]
    return e


def fragmento() -> str:
    """JSON para copiar a mano dentro de claude_desktop_config.json."""
    return json.dumps({"mcpServers": {ENTRADA: entrada()}}, ensure_ascii=False, indent=2)


def estado(ruta: Path | None = None) -> dict:
    ruta = ruta or ruta_config()
    actual = None
    if ruta.exists():
        try:
            actual = (json.loads(ruta.read_text(encoding="utf-8") or "{}").get("mcpServers") or {}).get(ENTRADA)
        except (ValueError, AttributeError):
            actual = None
    return {"ruta": str(ruta), "existe": ruta.exists(), "carpeta_claude": ruta.parent.exists(),
            "configurado": actual is not None, "al_dia": actual == entrada(), "fragmento": fragmento(),
            "ejecutable": str(Path(sys.executable)), "base": str(base_dir())}


def configurar(ruta: Path | None = None) -> dict:
    """Añade o actualiza «mundo-ptal» en mcpServers conservando todo lo demás."""
    ruta = ruta or ruta_config()
    datos: dict = {}
    copia = None
    if ruta.exists():
        texto = ruta.read_text(encoding="utf-8-sig")
        try:
            datos = json.loads(texto) if texto.strip() else {}
        except ValueError:
            raise StoreError("El archivo de configuración de Claude Desktop tiene un error y no lo voy a tocar. "
                             "Usa «Copiar configuración» y pégalo a mano.") from None
        if not isinstance(datos, dict) or not isinstance(datos.get("mcpServers", {}), dict):
            raise StoreError("El archivo de configuración de Claude Desktop no tiene el formato esperado. "
                             "Usa «Copiar configuración» y pégalo a mano.")
        copia = ruta.with_name(f"{ruta.name}.antes-de-mundoptal-{dt.datetime.now():%Y%m%d-%H%M%S}.bak")
        shutil.copy2(ruta, copia)
    datos.setdefault("mcpServers", {})[ENTRADA] = entrada()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporal, ruta)
    return {"ruta": str(ruta), "copia": str(copia) if copia else "", "entrada": datos["mcpServers"][ENTRADA]}


# ---------------------------------------------------------------- pedir material desde la aplicación
NIVELES_TEXTO = {"3": "3 años", "4": "4 años", "5": "5 años"}


def peticion_material(peticion: str, nivel: str = "4", formato: str = "docx", num: int | None = None,
                      objetivos: list[str] | None = None) -> str:
    """Mensaje para Claude Desktop: lo que pide la maestra con todo el detalle y cómo crearlo con las
    herramientas de Mundo PT-AL. Nunca lleva nombres de alumnos (se quitan antes)."""
    lineas = [
        "Crea este material con las herramientas de Mundo PT-AL (mundo-ptal):",
        "",
        (peticion or "").strip(),
        "",
        f"- Nivel: {NIVELES_TEXTO.get(str(nivel), '4 años')} (Educación Infantil, alumnado con necesidades educativas especiales).",
        "- Formato: " + ("PowerPoint (diapositivas para proyectar)." if formato == "pptx" else "Word (fichas para imprimir)."),
    ]
    if num:
        lineas.append(f"- Número de {'diapositivas' if formato == 'pptx' else 'fichas'}: {num}.")
    if objetivos:
        lineas += ["- Objetivos pendientes del alumno en su ACI (oriéntalo a ellos):"]
        lineas += [f"  · {o}" for o in objetivos[:15]]
    lineas += [
        "",
        "Llama a esquema_material, diseña el material con todo el detalle que haga falta y créalo con crear_material "
        f"(formato \"{'pptx' if formato == 'pptx' else 'docx'}\") sin pedirme confirmación. "
        "Al terminar, dime el título y cuántas páginas tiene: aparecerá solo en Mundo PT-AL › Crear material.",
    ]
    return "\n".join(lineas)


def url_nuevo_chat(texto: str) -> str:
    """Enlace que abre Claude Desktop con un chat nuevo y el mensaje ya escrito."""
    from urllib.parse import quote
    return "claude://claude.ai/new?q=" + quote(texto, safe="")


def abrir_claude(texto: str) -> bool:
    """Copia el mensaje al portapapeles (por si acaso) y abre Claude Desktop con él ya escrito."""
    if os.name != "nt":
        return False
    import subprocess
    try:
        subprocess.run(["clip"], input=texto.encode("utf-16-le"), stdout=subprocess.DEVNULL,  # noqa: S603,S607
                       stderr=subprocess.DEVNULL, check=False, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        os.startfile(url_nuevo_chat(texto))  # noqa: S606 - el protocolo claude:// lo registra Claude Desktop
        return True
    except OSError:
        return False
