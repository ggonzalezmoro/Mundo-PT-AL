"""Expediente privado de cada alumno: informes médicos y de gabinetes y el resumen del diagnóstico.

Son datos de salud de menores, así que se guardan aparte y cifrados:

* Un archivo por perfil (``privado/perfil_<id>.mpx``, una base SQLite) junto a los datos de la
  aplicación, nunca dentro de ``mundo_ptal.db``. Por eso no salen en «Exportar datos», en las copias
  de seguridad normales, en el servidor de Claude Desktop (MCP) ni en ninguna ruta genérica de la API.
* Todo el contenido (resumen, título, profesional, nombre del archivo y el propio documento) va
  cifrado con AES-256-GCM. La clave de datos es aleatoria y solo se guarda «envuelta» con una clave
  derivada (scrypt) de la contraseña de la maestra, y otra copia con el código de recuperación.
  Sin la contraseña o el código no hay forma de leerlo, ni siquiera desde el código fuente.
* Al abrirlo, la clave se queda solo en memoria y se olvida al cerrar el expediente, al cerrar la
  aplicación o tras unos minutos sin usarlo.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 1
MINUTOS_CIERRE = 10            # se cierra solo tras este tiempo sin usarlo
MIN_CONTRASENA = 8
MAX_DOCUMENTO = 25 * 1024 * 1024
# scrypt: ~64 MB de memoria y ~0,3 s por intento en un portátil: inviable probar contraseñas a millones
KDF = {"n": 2 ** 16, "r": 8, "p": 1}

TIPOS_DOC = {
    "psiquiatria": "Psiquiatría",
    "neurologia": "Neurología",
    "pediatria": "Pediatría / médico",
    "gabinete": "Gabinete (psicología, logopedia…)",
    "orientacion": "Orientación / EOEP",
    "atencion_temprana": "Atención temprana",
    "dictamen": "Dictamen de escolarización",
    "otro": "Otro",
}

CAMPOS_FICHA = {
    "diagnostico": "Diagnóstico actual",
    "fecha_diagnostico": "Fecha del último diagnóstico o revisión",
    "otros_diagnosticos": "Otros diagnósticos o sospechas",
    "profesionales": "Profesionales y centros que le siguen",
    "tratamiento": "Tratamiento y medicación",
    "alertas": "Alertas (alergias, crisis, qué hacer si…)",
    "pautas": "Pautas y recomendaciones para el aula",
    "notas": "Otras notas",
}

# Lo que el visor integrado sabe mostrar sin sacar el archivo del programa
MOSTRABLES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "text/plain")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clave (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL,
    kdf TEXT NOT NULL,
    sal_contrasena BLOB NOT NULL,
    clave_contrasena BLOB NOT NULL,
    sal_codigo BLOB NOT NULL,
    clave_codigo BLOB NOT NULL,
    creado TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fichas (
    alumno_id INTEGER PRIMARY KEY,
    datos BLOB NOT NULL,
    actualizado TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL,
    meta BLOB NOT NULL,
    contenido BLOB NOT NULL,
    tamano INTEGER NOT NULL DEFAULT 0,
    creado TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS documentos_alumno ON documentos(alumno_id);
"""


class ErrorPrivado(Exception):
    """Error que se muestra tal cual a la maestra."""


class Bloqueado(ErrorPrivado):
    """El expediente está cerrado: hay que escribir la contraseña."""


# ----------------------------------------------------------------- cifrado
def _derivar(secreto: str, sal: bytes, kdf: dict) -> bytes:
    return hashlib.scrypt(secreto.encode("utf-8"), salt=sal, n=kdf["n"], r=kdf["r"], p=kdf["p"],
                          maxmem=256 * 1024 * 1024, dklen=32)


def _cifrar(clave: bytes, datos: bytes, contexto: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(clave).encrypt(nonce, datos, contexto.encode())


def _descifrar(clave: bytes, blob: bytes, contexto: str) -> bytes:
    return AESGCM(clave).decrypt(blob[:12], blob[12:], contexto.encode())


def _normalizar_codigo(codigo: str) -> str:
    return "".join(c for c in codigo.upper() if c.isalnum())


def nuevo_codigo() -> str:
    """Código de recuperación: 25 caracteres (125 bits) en grupos de 5, sin letras que se confundan."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    crudo = "".join(secrets.choice(alfabeto) for _ in range(25))
    return "-".join(crudo[i:i + 5] for i in range(0, 25, 5))


# ----------------------------------------------------------------- expediente
class Expediente:
    """Archivo cifrado de un perfil."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.lock = threading.RLock()
        self._clave: bytes | None = None
        self._ultimo = 0.0
        self._fallos = 0
        self.minutos = MINUTOS_CIERRE

    # --- conexión: se abre y se cierra en cada operación (así se puede copiar o sustituir el archivo)
    def _conectar(self) -> sqlite3.Connection:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.ruta))
        c.row_factory = sqlite3.Row
        c.executescript(ESQUEMA)
        return c

    def _con(self):
        return _Conexion(self)

    # --- estado
    def configurado(self) -> bool:
        if not self.ruta.exists():
            return False
        with self._con() as c:
            return c.execute("SELECT 1 FROM clave WHERE id = 1").fetchone() is not None

    def abierto(self) -> bool:
        with self.lock:
            if self._clave and time.monotonic() - self._ultimo > self.minutos * 60:
                self.cerrar()
            return self._clave is not None

    def estado(self) -> dict:
        abierto = self.abierto()
        quedan = max(0, int(self.minutos * 60 - (time.monotonic() - self._ultimo))) if abierto else 0
        return {"configurado": self.configurado(), "abierto": abierto, "minutos": self.minutos,
                "segundos_restantes": quedan}

    def _clave_abierta(self) -> bytes:
        with self.lock:
            if not self.abierto():
                raise Bloqueado("El expediente privado está cerrado. Escribe tu contraseña para abrirlo.")
            self._ultimo = time.monotonic()
            return self._clave  # type: ignore[return-value]

    def cerrar(self) -> None:
        with self.lock:
            self._clave = None

    # --- contraseña
    @staticmethod
    def _validar(contrasena: str) -> None:
        if len(contrasena or "") < MIN_CONTRASENA:
            raise ErrorPrivado(f"La contraseña debe tener al menos {MIN_CONTRASENA} caracteres.")

    def configurar(self, contrasena: str) -> str:
        """Crea el expediente con su contraseña. Devuelve el código de recuperación (solo se muestra una vez)."""
        self._validar(contrasena)
        with self.lock:
            if self.configurado():
                raise ErrorPrivado("El expediente privado ya tiene contraseña.")
            dek = AESGCM.generate_key(bit_length=256)
            codigo = nuevo_codigo()
            sal_p, sal_c = os.urandom(16), os.urandom(16)
            with self._con() as c:
                c.execute("INSERT INTO clave(id, version, kdf, sal_contrasena, clave_contrasena, sal_codigo, clave_codigo) "
                          "VALUES (1, ?, ?, ?, ?, ?, ?)",
                          (VERSION, json.dumps(KDF), sal_p, _cifrar(_derivar(contrasena, sal_p, KDF), dek, "clave"),
                           sal_c, _cifrar(_derivar(_normalizar_codigo(codigo), sal_c, KDF), dek, "clave")))
            self._clave, self._ultimo, self._fallos = dek, time.monotonic(), 0
            return codigo

    def _fila_clave(self) -> sqlite3.Row:
        if not self.configurado():
            raise ErrorPrivado("Todavía no has creado tu expediente privado.")
        with self._con() as c:
            return c.execute("SELECT * FROM clave WHERE id = 1").fetchone()

    def _esperar_si_fallos(self) -> None:
        # Tras varios fallos seguidos, cada intento tarda más (además del coste de scrypt)
        if self._fallos >= 3:
            time.sleep(min(2 ** (self._fallos - 3), 30))

    def abrir(self, contrasena: str = "", codigo: str = "") -> None:
        fila = self._fila_clave()
        kdf = json.loads(fila["kdf"])
        with self.lock:
            self._esperar_si_fallos()
            try:
                if codigo:
                    k = _derivar(_normalizar_codigo(codigo), fila["sal_codigo"], kdf)
                    dek = _descifrar(k, fila["clave_codigo"], "clave")
                else:
                    k = _derivar(contrasena or "", fila["sal_contrasena"], kdf)
                    dek = _descifrar(k, fila["clave_contrasena"], "clave")
            except InvalidTag:
                self._fallos += 1
                raise ErrorPrivado("El código de recuperación no es correcto." if codigo
                                   else "La contraseña no es correcta.") from None
            self._clave, self._ultimo, self._fallos = dek, time.monotonic(), 0

    def cambiar_contrasena(self, nueva: str, actual: str = "", codigo: str = "") -> None:
        """Cambia la contraseña comprobando la actual (o el código de recuperación si se ha olvidado)."""
        self._validar(nueva)
        self.abrir(contrasena=actual, codigo=codigo)
        dek = self._clave_abierta()
        sal = os.urandom(16)
        with self._con() as c:
            c.execute("UPDATE clave SET sal_contrasena = ?, clave_contrasena = ?, kdf = ? WHERE id = 1",
                      (sal, _cifrar(_derivar(nueva, sal, KDF), dek, "clave"), json.dumps(KDF)))

    def nuevo_codigo_recuperacion(self, contrasena: str) -> str:
        """Genera otro código de recuperación (el anterior deja de valer)."""
        self.abrir(contrasena=contrasena)
        dek = self._clave_abierta()
        codigo = nuevo_codigo()
        sal = os.urandom(16)
        with self._con() as c:
            c.execute("UPDATE clave SET sal_codigo = ?, clave_codigo = ? WHERE id = 1",
                      (sal, _cifrar(_derivar(_normalizar_codigo(codigo), sal, KDF), dek, "clave")))
        return codigo

    # --- ficha con el diagnóstico
    def ficha(self, alumno_id: int) -> dict:
        dek = self._clave_abierta()
        with self._con() as c:
            f = c.execute("SELECT datos, actualizado FROM fichas WHERE alumno_id = ?", (alumno_id,)).fetchone()
        datos = json.loads(_descifrar(dek, f["datos"], f"ficha:{alumno_id}")) if f else {}
        return {**{k: datos.get(k, "") for k in CAMPOS_FICHA}, "actualizado": f["actualizado"] if f else ""}

    def guardar_ficha(self, alumno_id: int, cambios: dict) -> dict:
        dek = self._clave_abierta()
        with self.lock:
            datos = {k: v for k, v in self.ficha(alumno_id).items() if k in CAMPOS_FICHA}
            datos.update({k: str(v)[:20000] for k, v in cambios.items() if k in CAMPOS_FICHA})
            blob = _cifrar(dek, json.dumps(datos, ensure_ascii=False).encode(), f"ficha:{alumno_id}")
            with self._con() as c:
                c.execute("INSERT INTO fichas(alumno_id, datos, actualizado) VALUES (?, ?, datetime('now', 'localtime')) "
                          "ON CONFLICT(alumno_id) DO UPDATE SET datos = excluded.datos, actualizado = excluded.actualizado",
                          (alumno_id, blob))
        return self.ficha(alumno_id)

    # --- documentos
    def _meta(self, dek: bytes, fila) -> dict:
        m = json.loads(_descifrar(dek, fila["meta"], f"meta:{fila['alumno_id']}:{fila['id']}"))
        m.update(id=fila["id"], alumno_id=fila["alumno_id"], tamano=fila["tamano"], subido=fila["creado"],
                 tipo_texto=TIPOS_DOC.get(m.get("tipo"), "Otro"),
                 mostrable=m.get("mime", "") in MOSTRABLES)
        return m

    def documentos(self, alumno_id: int) -> list[dict]:
        dek = self._clave_abierta()
        with self._con() as c:
            filas = c.execute("SELECT id, alumno_id, meta, tamano, creado FROM documentos WHERE alumno_id = ?",
                              (alumno_id,)).fetchall()
        docs = [self._meta(dek, f) for f in filas]
        # Lo más reciente arriba (por la fecha del informe; si no tiene, por la de subida)
        return sorted(docs, key=lambda d: (d.get("fecha") or d["subido"][:10], d["id"]), reverse=True)

    def anadir_documento(self, alumno_id: int, nombre: str, mime: str, contenido: bytes, meta: dict) -> int:
        dek = self._clave_abierta()
        if not contenido:
            raise ErrorPrivado("El archivo está vacío.")
        if len(contenido) > MAX_DOCUMENTO:
            raise ErrorPrivado("El archivo es demasiado grande (máximo 25 MB). Si es un escaneo, guárdalo en PDF con menos calidad.")
        with self.lock, self._con() as c:
            cur = c.execute("INSERT INTO documentos(alumno_id, meta, contenido, tamano, creado) "
                            "VALUES (?, x'', x'', ?, datetime('now', 'localtime'))", (alumno_id, len(contenido)))
            did = cur.lastrowid
            datos = {"titulo": (meta.get("titulo") or Path(nombre).stem)[:300], "tipo": meta.get("tipo") or "otro",
                     "profesional": (meta.get("profesional") or "")[:300], "fecha": (meta.get("fecha") or "")[:10],
                     "notas": (meta.get("notas") or "")[:5000], "nombre": Path(nombre).name[:200] or "documento",
                     "mime": mime or "application/octet-stream"}
            c.execute("UPDATE documentos SET meta = ?, contenido = ? WHERE id = ?",
                      (_cifrar(dek, json.dumps(datos, ensure_ascii=False).encode(), f"meta:{alumno_id}:{did}"),
                       _cifrar(dek, contenido, f"doc:{alumno_id}:{did}"), did))
        return did

    def _fila_doc(self, c, doc_id: int):
        f = c.execute("SELECT * FROM documentos WHERE id = ?", (doc_id,)).fetchone()
        if not f:
            raise ErrorPrivado("Documento no encontrado.")
        return f

    def editar_documento(self, doc_id: int, cambios: dict) -> dict:
        dek = self._clave_abierta()
        with self.lock, self._con() as c:
            f = self._fila_doc(c, doc_id)
            m = {k: v for k, v in self._meta(dek, f).items()
                 if k in ("titulo", "tipo", "profesional", "fecha", "notas", "nombre", "mime")}
            for k in ("titulo", "tipo", "profesional", "fecha", "notas"):
                if k in cambios:
                    m[k] = str(cambios[k])[:5000]
            c.execute("UPDATE documentos SET meta = ? WHERE id = ?",
                      (_cifrar(dek, json.dumps(m, ensure_ascii=False).encode(), f"meta:{f['alumno_id']}:{doc_id}"), doc_id))
            return self._meta(dek, c.execute("SELECT * FROM documentos WHERE id = ?", (doc_id,)).fetchone())

    def leer_documento(self, doc_id: int) -> tuple[dict, bytes]:
        dek = self._clave_abierta()
        with self._con() as c:
            f = self._fila_doc(c, doc_id)
        return self._meta(dek, f), _descifrar(dek, f["contenido"], f"doc:{f['alumno_id']}:{doc_id}")

    def borrar_documento(self, doc_id: int) -> None:
        self._clave_abierta()
        with self.lock, self._con() as c:
            c.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))
        self._compactar()

    def borrar_alumno(self, alumno_id: int) -> None:
        """Al borrar un alumno se borra también su expediente (no hace falta la contraseña)."""
        if not self.ruta.exists():
            return
        with self.lock, self._con() as c:
            c.execute("DELETE FROM documentos WHERE alumno_id = ?", (alumno_id,))
            c.execute("DELETE FROM fichas WHERE alumno_id = ?", (alumno_id,))
        self._compactar()

    def _compactar(self) -> None:
        # Reescribe el archivo para que lo borrado (aunque iba cifrado) no quede en páginas libres
        with self.lock:
            c = sqlite3.connect(str(self.ruta))
            try:
                c.execute("VACUUM")
            finally:
                c.close()

    def resumen(self) -> dict[int, int]:
        """Número de documentos por alumno (no necesita la contraseña: no revela contenido)."""
        if not self.ruta.exists():
            return {}
        with self._con() as c:
            return {r["alumno_id"]: r["n"] for r in
                    c.execute("SELECT alumno_id, COUNT(*) AS n FROM documentos GROUP BY alumno_id")}

    # --- pasar el expediente a otro ordenador (sigue cifrado con la misma contraseña)
    def exportar(self) -> bytes:
        if not self.configurado():
            raise ErrorPrivado("Todavía no has creado tu expediente privado.")
        with self.lock:
            return self.ruta.read_bytes()

    def importar(self, datos: bytes, contrasena: str) -> Path | None:
        """Sustituye el expediente por una copia exportada. Comprueba antes que la contraseña la abre;
        el expediente anterior se guarda al lado por si acaso."""
        with self.lock:
            tmp = self.ruta.with_suffix(".importando")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(datos)
            try:
                prueba = Expediente(tmp)
                try:
                    if not prueba.configurado():
                        raise ErrorPrivado("Ese archivo no es un expediente privado de Mundo PT-AL.")
                except sqlite3.DatabaseError:
                    raise ErrorPrivado("Ese archivo no es un expediente privado de Mundo PT-AL.") from None
                prueba.abrir(contrasena=contrasena)
                previo = None
                if self.ruta.exists():
                    previo = self.ruta.with_name(f"{self.ruta.stem}_antes_de_importar_{time.strftime('%Y%m%d_%H%M%S')}.mpx")
                    shutil.copy2(self.ruta, previo)
                os.replace(tmp, self.ruta)
            finally:
                if tmp.exists():
                    tmp.unlink()
            self._clave, self._ultimo, self._fallos = prueba._clave, time.monotonic(), 0
            return previo


class _Conexion:
    def __init__(self, exp: Expediente):
        self.exp = exp

    def __enter__(self) -> sqlite3.Connection:
        self.exp.lock.acquire()
        self.c = self.exp._conectar()
        return self.c

    def __exit__(self, tipo, *_):
        try:
            if tipo is None:
                self.c.commit()
            self.c.close()
        finally:
            self.exp.lock.release()


class Gestor:
    """Un expediente por perfil, en <carpeta de datos>/privado/."""

    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self._exps: dict[int, Expediente] = {}
        self._lock = threading.Lock()

    def de(self, usuario_id: int | None) -> Expediente:
        uid = int(usuario_id or 0)
        with self._lock:
            if uid not in self._exps:
                self._exps[uid] = Expediente(self.carpeta / f"perfil_{uid}.mpx")
            return self._exps[uid]

    def carpeta_temporal(self) -> Path:
        return self.carpeta / "abiertos"

    def limpiar_temporales(self) -> None:
        """Borra las copias que se sacaron para abrir con otro programa (Word, visor de fotos…)."""
        shutil.rmtree(self.carpeta_temporal(), ignore_errors=True)

    def cerrar_todos(self) -> None:
        with self._lock:
            for e in self._exps.values():
                e.cerrar()
        self.limpiar_temporales()

