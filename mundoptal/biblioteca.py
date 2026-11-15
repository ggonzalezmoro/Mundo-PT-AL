"""Dónde se guarda el material y cómo se maqueta y se registra.

Lo comparten la aplicación (servidor.py) y el servidor MCP para Claude Desktop
(mcp_server.py), para que el material salga igual por las dos vías: logo, cabecera del
perfil, pictogramas de ARASAAC y registro en la tabla «materiales».

Las funciones reciben una conexión sqlite3 (no un Store) para que el servidor MCP pueda
leer la base de datos en solo lectura, sin migraciones."""
from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
from pathlib import Path

from . import maqueta
from .material import MaterialSpec

MAX_PAGINAS = 30


def carpeta_documentos() -> Path:
    """Documentos › Mundo PT-AL (MUNDOPTAL_DOCUMENTOS la cambia en las pruebas automáticas)."""
    otra = os.environ.get("MUNDOPTAL_DOCUMENTOS")
    if otra:
        Path(otra).mkdir(parents=True, exist_ok=True)
        return Path(otra)
    destino = Path.home() / "Documents"
    if not destino.exists():
        destino = Path.home()
    destino = destino / "Mundo PT-AL"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def carpeta_material() -> Path:
    d = carpeta_documentos() / "Material"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logo_perfil(uid) -> Path:
    return carpeta_material() / f"logo_fichas_{uid or 0}.png"


def ajuste(conn: sqlite3.Connection, clave: str, defecto: str = "") -> str:
    fila = conn.execute("SELECT valor FROM meta WHERE clave = ?", (clave,)).fetchone()
    return fila[0] if fila and fila[0] is not None else defecto


def cabecera_perfil(conn: sqlite3.Connection, uid) -> str:
    fila = conn.execute("SELECT nombre FROM usuarios WHERE id = ?", (uid,)).fetchone() if uid else None
    return ajuste(conn, f"material.cabecera.{uid or 0}", fila[0] if fila else "")


def pictos_activados(conn: sqlite3.Connection) -> bool:
    return ajuste(conn, "material.pictos", "1") == "1"


def recursos(conn: sqlite3.Connection, uid, alumno: str = "") -> maqueta.Recursos:
    logo = logo_perfil(uid)
    pictos = pictos_activados(conn)
    return maqueta.Recursos(carpeta_pictos=carpeta_documentos() / "Pictogramas" if pictos else None,
                            descargar_pictos=pictos, logo=logo if logo.exists() else None,
                            cabecera=cabecera_perfil(conn, uid), alumno=alumno)


def nombre_archivo(titulo: str, formato: str) -> Path:
    """AAAA-MM-DD_titulo.docx en la carpeta de material, sin pisar uno que ya exista."""
    base = re.sub(r"[^\w\-]+", "_", f"{dt.date.today():%Y-%m-%d}_{titulo}").strip("_")[:80] or "material"
    ruta = carpeta_material() / f"{base}.{formato}"
    n = 2
    while ruta.exists():
        ruta = carpeta_material() / f"{base}_{n}.{formato}"
        n += 1
    return ruta


def maquetar(spec: MaterialSpec, formato: str, rec: maqueta.Recursos) -> bytes:
    return maqueta.a_word(spec, rec) if formato == "docx" else maqueta.a_powerpoint(spec, rec)


def registrar(conn: sqlite3.Connection, uid, spec: MaterialSpec, formato: str, ruta: Path,
              tipo: str = "", origen: str = "plantilla", alumno_id=None) -> int:
    return conn.execute("""INSERT INTO materiales(usuario_id, alumno_id, titulo, tipo, origen, formato, paginas, ruta)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (uid, alumno_id or None, spec.titulo, tipo, origen, formato, len(spec.paginas), str(ruta))).lastrowid
