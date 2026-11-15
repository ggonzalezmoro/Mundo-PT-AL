"""Servidor MCP local (stdio) para crear material con Claude Desktop, sin clave de la API.

Claude Desktop (con la suscripción Pro de la maestra) arranca este servidor como un
proceso hijo y habla con él por la entrada y salida estándar. No abre ningún puerto ni
ninguna ventana. Arranque:

    python -m mundoptal.mcp_server [--perfil <id o nombre>]
    MundoPTAL.exe --mcp [--perfil <id o nombre>]

Privacidad: a Claude solo le llega lo que devuelven estas herramientas. Los alumnos se
muestran como «Alumno 1», «Alumno 2»… (la correspondencia con su id no sale de aquí) y
solo si se ha activado en Ajustes (viene desactivado). Nunca se devuelven nombres.

Base de datos: se abre en solo lectura (sin migraciones). La única escritura es el
registro del material creado en la tabla «materiales», con una conexión aparte."""
from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Literal

from . import biblioteca
from .ia_material import anonimizar
from .material import ACTIVIDADES, NIVELES, TIPOS, MaterialSpec, plantilla

NOMBRE = "mundo-ptal"
AJUSTE_ALUMNOS = "mcp.alumnos"

INSTRUCCIONES = f"""Eres la ayudante de una maestra de Pedagogía Terapéutica (PT) y Audición y Lenguaje (AL) de \
Educación Infantil (3 a 5 años) en un colegio de España. Con estas herramientas creas material imprimible (Word) o \
proyectable (PowerPoint) para alumnos con necesidades educativas especiales; la aplicación Mundo PT-AL lo maqueta con \
el logo y la cabecera del colegio y con pictogramas de ARASAAC, y lo guarda en su carpeta de material.

Cómo trabajar:
1. Antes de crear material, llama a esquema_material para ver los campos exactos. Si te sirve una plantilla, mira \
listar_plantillas y usa crear_desde_plantilla, que es más rápido.
2. Diseña el material y llama a crear_material con formato "docx" (fichas para imprimir) o "pptx" (diapositivas).
3. Al terminar, di a la maestra el nombre del archivo y dónde está.

Criterios de diseño para PT/AL e Infantil:
- UNA actividad por página. Tipos de actividad: {", ".join(ACTIVIDADES)}.
- Enunciados de UNA sola línea, cortos, en segunda persona («Rodea la letra A», «Une cada animal con su sombra»).
- Vocabulario cotidiano, frases muy cortas, nada que exija leer textos largos; progresión de fácil a difícil.
- Pictograma: una palabra clave sencilla en español y en singular («perro», «manzana», «lavarse las manos»); "" si \
el elemento es solo una letra, número o sílaba.
- 4 años: 4 opciones por actividad y números hasta 5; 3 años: 3 opciones y hasta 3; 5 años: 5 opciones y hasta 10.
- «unir»: texto a la izquierda y pareja a la derecha (la aplicación desordena). «rodear» y «pregunta»: correcto=true \
en las respuestas. «completar»: hueco como ___ y la solución en pareja. «contar»: cantidad de 1 a 10. \
«clasificar»: grupo de cada elemento. «secuencia»: pasos en orden correcto (se desordenan). «tarjetas»: 4 por página.
- Los campos que no se usan: "" en texto, false en booleanos y 0 en números. «instrucciones_maestra»: 2 o 3 frases.
- No escribas nombres de alumnos ni datos personales en el material. Si la maestra los menciona, no los copies.
- listar_alumnos y objetivos_alumno solo funcionan si la maestra lo ha activado en Ajustes; dan un alias \
(«Alumno 1»…) y sus objetivos pendientes para orientar el material."""


class ErrorMCP(Exception):
    """Error con un mensaje claro para Claude y la maestra."""


class _Lector:
    """Lo mínimo de Store que usa Planificador.items_pendientes, sobre una conexión de solo lectura."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def q(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def q1(self, sql: str, params=()) -> dict | None:
        r = self.q(sql, params)
        return r[0] if r else None

    def aci_vigente(self, alumno_id: int) -> int | None:
        r = self.conn.execute("SELECT MAX(id) FROM acis WHERE alumno_id = ?", (alumno_id,)).fetchone()
        return r[0] if r else None


class Herramientas:
    """La lógica de las herramientas, sin depender del SDK de MCP (así se prueba sin él)."""

    def __init__(self, db_path: str | Path, perfil: str | None = None):
        self.db_path = Path(db_path)
        self.perfil_pedido = perfil

    # ------------------------------------------------------------ base de datos
    @contextlib.contextmanager
    def _leer(self):
        if not self.db_path.exists():
            raise ErrorMCP("No encuentro los datos de Mundo PT-AL. Abre la aplicación al menos una vez en este ordenador.")
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def _escribir(self):
        """Solo para registrar el material creado (sin migraciones ni cambios de esquema)."""
        conn = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(Exception):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def perfil(self, conn: sqlite3.Connection) -> int | None:
        """Perfil pedido con --perfil (id o nombre), si no el último usado en la aplicación, si no el único."""
        usuarios = [dict(r) for r in conn.execute("SELECT id, nombre FROM usuarios ORDER BY id")]
        if not usuarios:
            return None
        pedido = (self.perfil_pedido or "").strip()
        if pedido:
            from .store import normalizar
            for u in usuarios:
                if pedido == str(u["id"]) or normalizar(pedido) == normalizar(u["nombre"]):
                    return u["id"]
            raise ErrorMCP("El perfil indicado con --perfil no existe en Mundo PT-AL.")
        ultimo = biblioteca.ajuste(conn, "ultimo_perfil", "")
        if ultimo.isdigit() and any(u["id"] == int(ultimo) for u in usuarios):
            return int(ultimo)
        return usuarios[0]["id"]

    # ------------------------------------------------------------ plantillas y esquema
    def listar_plantillas(self) -> dict:
        return {
            "actividades": ACTIVIDADES,
            "plantillas": [{"tipo": k, "nombre": v["nombre"], "descripcion": v["ayuda"], "ejemplo_contenido": v["ejemplo"]}
                           for k, v in TIPOS.items()],
            "parametros": {"contenido": "Texto según la plantilla (ver ejemplo_contenido)",
                           "nivel": f"Edad: {' | '.join(NIVELES)} (años); por defecto 4",
                           "num": "Número de páginas (opcional; 0 = el que traiga la plantilla)"},
            "formatos": {"docx": "Fichas para imprimir (Word)", "pptx": "Diapositivas para proyectar (PowerPoint)"},
        }

    def esquema_material(self) -> dict:
        return MaterialSpec.model_json_schema()

    # ------------------------------------------------------------ crear
    def crear_material(self, spec, formato: str = "docx", titulo_archivo: str = "", tipo: str = "",
                       origen: str = "claude_desktop") -> dict:
        try:
            spec = spec if isinstance(spec, MaterialSpec) else MaterialSpec.model_validate(spec)
        except Exception as e:  # noqa: BLE001
            raise ErrorMCP(f"El material no cumple el esquema (llama a esquema_material): {e}") from None
        if not spec.paginas:
            raise ErrorMCP("El material no tiene páginas.")
        if len(spec.paginas) > biblioteca.MAX_PAGINAS:
            raise ErrorMCP(f"Demasiadas páginas: como máximo {biblioteca.MAX_PAGINAS}.")
        if formato not in ("docx", "pptx"):
            raise ErrorMCP("El formato es «docx» (Word) o «pptx» (PowerPoint).")
        with self._leer() as conn:
            uid = self.perfil(conn)
            rec = biblioteca.recursos(conn, uid)
        datos = biblioteca.maquetar(spec, formato, rec)
        titulo = re.sub(r"\s+", " ", titulo_archivo or "").strip() or spec.titulo
        ruta = biblioteca.nombre_archivo(titulo, formato)
        ruta.write_bytes(datos)
        with self._escribir() as conn:
            mid = biblioteca.registrar(conn, uid, spec, formato, ruta, tipo, origen)
        actividades = [p.actividad for p in spec.paginas]
        return {"ruta": str(ruta), "archivo": ruta.name, "carpeta": str(ruta.parent), "id": mid,
                "resumen": {"titulo": spec.titulo, "formato": "Word" if formato == "docx" else "PowerPoint",
                            "paginas": len(spec.paginas), "actividades": sorted(set(actividades), key=actividades.index),
                            "pictogramas_arasaac": rec.usados_pictos}}

    def crear_desde_plantilla(self, tipo: str, parametros: dict | None = None, formato: str = "docx") -> dict:
        p = parametros or {}
        if tipo not in TIPOS:
            raise ErrorMCP(f"Plantilla desconocida: {tipo}. Las que hay: {', '.join(TIPOS)}.")
        try:
            spec = plantilla(tipo, str(p.get("contenido") or ""), str(p.get("nivel") or "4"), int(p.get("num") or 0) or None,
                             p.get("semilla"))
        except ValueError as e:
            raise ErrorMCP(str(e)) from None
        return self.crear_material(spec, formato, tipo=tipo, origen="plantilla_claude_desktop")

    # ------------------------------------------------------------ alumnos (con alias, desactivado por defecto)
    def _alias(self, conn) -> list[tuple[str, int]]:
        if biblioteca.ajuste(conn, AJUSTE_ALUMNOS, "0") != "1":
            raise ErrorMCP("La maestra no ha activado el acceso a los objetivos de los alumnos "
                           "(Mundo PT-AL › Ajustes › Usar con Claude Desktop). Crea el material sin ellos.")
        uid = self.perfil(conn)
        filas = conn.execute("SELECT id FROM alumnos WHERE activo = 1 AND usuario_id IS ? ORDER BY id", (uid,)).fetchall()
        return [(f"Alumno {i}", f[0]) for i, f in enumerate(filas, 1)]

    def _objetivos(self, conn, alumno_id: int) -> list[str]:
        from .planificador import Planificador
        nombres = [r[0] for r in conn.execute("SELECT nombre FROM alumnos")]
        return [anonimizar(i["texto"], nombres)[0] for i in Planificador(_Lector(conn)).items_pendientes(alumno_id)]

    def listar_alumnos(self) -> list[dict]:
        with self._leer() as conn:
            return [{"alumno": alias, "objetivos_pendientes": len(self._objetivos(conn, aid))} for alias, aid in self._alias(conn)]

    def objetivos_alumno(self, alumno: str | int) -> dict:
        m = re.search(r"\d+", str(alumno))
        with self._leer() as conn:
            alias = self._alias(conn)
            if not m or not 1 <= int(m.group()) <= len(alias):
                raise ErrorMCP(f"No existe ese alumno. Usa uno de: {', '.join(a for a, _ in alias) or '(ninguno)'}.")
            nombre, aid = alias[int(m.group()) - 1]
            return {"alumno": nombre, "objetivos": self._objetivos(conn, aid)}

    # ------------------------------------------------------------ materiales
    def listar_materiales(self, n: int = 10) -> list[dict]:
        n = max(1, min(int(n or 10), 50))
        with self._leer() as conn:
            uid = self.perfil(conn)
            nombres = [r[0] for r in conn.execute("SELECT nombre FROM alumnos")]
            filas = conn.execute("""SELECT titulo, formato, paginas, origen, creado, ruta FROM materiales
                                    WHERE usuario_id IS ? ORDER BY id DESC LIMIT ?""", (uid, n)).fetchall()
        return [{"titulo": anonimizar(f["titulo"], nombres)[0], "formato": f["formato"], "paginas": f["paginas"],
                 "origen": f["origen"], "creado": f["creado"], "archivo": Path(f["ruta"]).name,
                 "existe": Path(f["ruta"]).exists()} for f in filas]


# ---------------------------------------------------------------- servidor FastMCP
def crear_servidor(h: Herramientas):
    from mcp.server.fastmcp import FastMCP

    servidor = FastMCP(NOMBRE, instructions=INSTRUCCIONES)

    def _seguro(funcion, *args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except ErrorMCP as e:
            raise ValueError(str(e)) from None  # FastMCP lo devuelve como error de la herramienta, con este texto

    @servidor.tool()
    def listar_plantillas() -> dict:
        """Tipos de actividad que entiende la maqueta y plantillas rápidas, con su descripción y parámetros."""
        return _seguro(h.listar_plantillas)

    @servidor.tool()
    def esquema_material() -> dict:
        """JSON Schema de MaterialSpec. Llámala antes de crear_material para rellenar bien todos los campos."""
        return _seguro(h.esquema_material)

    @servidor.tool()
    def crear_material(spec: MaterialSpec, formato: Literal["docx", "pptx"] = "docx", titulo_archivo: str = "") -> dict:
        """Valida el material, lo maqueta con el logo, la cabecera y pictogramas de ARASAAC, lo guarda en la carpeta
        de material de Mundo PT-AL y lo registra. Devuelve la ruta del archivo y un resumen.
        formato: "docx" = fichas para imprimir (Word); "pptx" = diapositivas para proyectar (PowerPoint)."""
        return _seguro(h.crear_material, spec, formato, titulo_archivo)

    @servidor.tool()
    def crear_desde_plantilla(tipo: str, parametros: dict | None = None, formato: Literal["docx", "pptx"] = "docx") -> dict:
        """Crea material con una plantilla de listar_plantillas. parametros: {"contenido": str, "nivel": "3"|"4"|"5",
        "num": int}. Ejemplo: tipo="letras", parametros={"contenido": "vocales", "nivel": "4"}."""
        return _seguro(h.crear_desde_plantilla, tipo, parametros, formato)

    @servidor.tool()
    def listar_alumnos() -> list[dict]:
        """Alumnos del perfil como alias («Alumno 1»…) con cuántos objetivos tienen pendientes. Nunca da nombres.
        Solo funciona si la maestra lo ha activado en Ajustes."""
        return _seguro(h.listar_alumnos)

    @servidor.tool()
    def objetivos_alumno(alumno_id: str) -> dict:
        """Objetivos no conseguidos de la ACI vigente de un alumno, para orientar el material.
        alumno_id: el alias de listar_alumnos («Alumno 2» o «2»)."""
        return _seguro(h.objetivos_alumno, alumno_id)

    @servidor.tool()
    def listar_materiales(n: int = 10) -> list[dict]:
        """Últimos materiales creados (título, formato, páginas, archivo)."""
        return _seguro(h.listar_materiales, n)

    return servidor


def _asegurar_stdio() -> None:
    """En el .exe sin consola (PyInstaller, console=False), si Python no ha creado sys.stdin o
    sys.stdout, se abren a partir de los handles heredados de Claude Desktop."""
    if sys.stdin is not None and sys.stdout is not None:
        return
    if sys.platform != "win32":
        raise SystemExit("No hay entrada/salida estándar para el modo --mcp")
    import ctypes
    import io
    import msvcrt
    k32 = ctypes.windll.kernel32
    for nombre, std, modo in (("stdin", -10, "rb"), ("stdout", -11, "wb"), ("stderr", -12, "wb")):
        if getattr(sys, nombre) is None:
            handle = k32.GetStdHandle(std)
            if handle in (0, -1, None):
                if nombre == "stderr":
                    continue
                raise SystemExit("Claude Desktop no ha pasado la entrada/salida estándar")
            fd = msvcrt.open_osfhandle(handle, 0)
            crudo = io.open(fd, modo, buffering=0, closefd=False)
            setattr(sys, nombre, io.TextIOWrapper(io.BufferedReader(crudo) if "r" in modo else io.BufferedWriter(crudo),
                                                  encoding="utf-8", line_buffering=True))


def _valor(argv: list[str], opcion: str) -> str | None:
    if opcion in argv:
        i = argv.index(opcion)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv: list[str] | None = None) -> int:
    from .config import data_dir, db_path

    argv = sys.argv[1:] if argv is None else argv
    _asegurar_stdio()
    # Nada a stdout salvo el protocolo: el registro va a un archivo
    logging.basicConfig(filename=str(data_dir() / "mundo_ptal_mcp.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    logging.info("Servidor MCP arrancado (perfil: %s)", _valor(argv, "--perfil") or "último usado")
    crear_servidor(Herramientas(db_path(), _valor(argv, "--perfil"))).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
