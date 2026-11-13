"""Base de datos local SQLite (incluida en Python, no necesita instalación)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

-- Perfiles de los maestros que usan la aplicación en este equipo
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    especialidad TEXT NOT NULL DEFAULT 'PT/AL' CHECK (especialidad IN ('PT', 'AL', 'PT/AL')),
    creado TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alumnos (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    curso TEXT DEFAULT '',
    observaciones TEXT DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    creado TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Una ACI por alumno y trimestre/curso. La más reciente es la "vigente".
CREATE TABLE IF NOT EXISTS acis (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    curso TEXT DEFAULT '',
    curso_escolar TEXT DEFAULT '',
    trimestre INTEGER NOT NULL DEFAULT 1 CHECK (trimestre BETWEEN 1 AND 3),
    titulo TEXT DEFAULT 'INFORME DE EVALUACIÓN TRIMESTRAL',
    materia TEXT DEFAULT 'AUDICIÓN Y LENGUAJE',
    prof_area TEXT DEFAULT '',
    prof_ptal TEXT DEFAULT '',
    observaciones TEXT DEFAULT '',
    creado TEXT DEFAULT CURRENT_TIMESTAMP,
    actualizado TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Tabla "Tipos de adaptaciones" (resumen de áreas)
CREATE TABLE IF NOT EXISTS adaptaciones (
    id INTEGER PRIMARY KEY,
    aci_id INTEGER NOT NULL REFERENCES acis(id) ON DELETE CASCADE,
    area TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT '' CHECK (tipo IN ('', 'significativa', 'no_significativa', 'ninguna')),
    nivel_curricular TEXT DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0
);

-- Jerarquía: Área > Subárea > Competencia > Ítem
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY,
    aci_id INTEGER NOT NULL REFERENCES acis(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL DEFAULT '',
    especialidad TEXT NOT NULL DEFAULT '' CHECK (especialidad IN ('', 'PT', 'AL')),
    orden INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subareas (
    id INTEGER PRIMARY KEY,
    area_id INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL DEFAULT '',   -- '' = competencias sin subárea
    orden INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competencias (
    id INTEGER PRIMARY KEY,
    subarea_id INTEGER NOT NULL REFERENCES subareas(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    competencia_id INTEGER NOT NULL REFERENCES competencias(id) ON DELETE CASCADE,
    texto TEXT NOT NULL DEFAULT '',
    eval_1t TEXT NOT NULL DEFAULT '',
    eval_2t TEXT NOT NULL DEFAULT '',
    eval_3t TEXT NOT NULL DEFAULT '',
    destacado INTEGER NOT NULL DEFAULT 0,
    nota TEXT NOT NULL DEFAULT '',     -- observación breve junto al ítem
    orden INTEGER NOT NULL DEFAULT 0
);

-- Horario semanal del maestro
CREATE TABLE IF NOT EXISTS franjas (
    id INTEGER PRIMARY KEY,
    dia INTEGER NOT NULL CHECK (dia BETWEEN 0 AND 4),
    inicio TEXT NOT NULL,
    fin TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'sesion' CHECK (tipo IN ('sesion', 'otro')),
    etiqueta TEXT DEFAULT '',
    especialidad TEXT NOT NULL DEFAULT 'PT/AL' CHECK (especialidad IN ('PT', 'AL', 'PT/AL')),
    items_por_sesion INTEGER NOT NULL DEFAULT 3,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS franja_alumnos (
    franja_id INTEGER NOT NULL REFERENCES franjas(id) ON DELETE CASCADE,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    PRIMARY KEY (franja_id, alumno_id)
);

-- Sesiones concretas (una por alumno, franja y fecha)
CREATE TABLE IF NOT EXISTS sesiones (
    id INTEGER PRIMARY KEY,
    franja_id INTEGER NOT NULL REFERENCES franjas(id) ON DELETE CASCADE,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'planificada' CHECK (estado IN ('planificada', 'realizada', 'cancelada')),
    notas TEXT DEFAULT '',
    UNIQUE (franja_id, alumno_id, fecha)
);

CREATE TABLE IF NOT EXISTS sesion_items (
    sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    trabajado INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sesion_id, item_id)
);

-- Informe trimestral descriptivo para las familias
CREATE TABLE IF NOT EXISTS informes (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    aci_id INTEGER REFERENCES acis(id) ON DELETE SET NULL,
    trimestre INTEGER NOT NULL DEFAULT 1 CHECK (trimestre BETWEEN 1 AND 3),
    curso_escolar TEXT NOT NULL DEFAULT '',
    curso TEXT DEFAULT '',
    maestra TEXT DEFAULT '',
    social TEXT DEFAULT '',
    actitud_pt TEXT DEFAULT '',
    actitud_al TEXT DEFAULT '',
    valoracion TEXT DEFAULT '',
    orientaciones TEXT DEFAULT '',
    estrategias TEXT DEFAULT '',
    despedida TEXT DEFAULT '',
    prof_area TEXT DEFAULT '',
    creado TEXT DEFAULT CURRENT_TIMESTAMP,
    actualizado TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (alumno_id, trimestre, curso_escolar)
);

CREATE TABLE IF NOT EXISTS informe_areas (
    id INTEGER PRIMARY KEY,
    informe_id INTEGER NOT NULL REFERENCES informes(id) ON DELETE CASCADE,
    area TEXT NOT NULL DEFAULT '',
    texto TEXT DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_acis_alumno ON acis(alumno_id);
CREATE INDEX IF NOT EXISTS ix_informes_alumno ON informes(alumno_id);
CREATE INDEX IF NOT EXISTS ix_infareas_informe ON informe_areas(informe_id);
CREATE INDEX IF NOT EXISTS ix_alumnos_usuario ON alumnos(usuario_id);
CREATE INDEX IF NOT EXISTS ix_franjas_usuario ON franjas(usuario_id);
CREATE INDEX IF NOT EXISTS ix_areas_aci ON areas(aci_id);
CREATE INDEX IF NOT EXISTS ix_sub_area ON subareas(area_id);
CREATE INDEX IF NOT EXISTS ix_comp_sub ON competencias(subarea_id);
CREATE INDEX IF NOT EXISTS ix_items_comp ON items(competencia_id);
CREATE INDEX IF NOT EXISTS ix_sesiones_fecha ON sesiones(fecha);
CREATE INDEX IF NOT EXISTS ix_sesitems_item ON sesion_items(item_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _migrar(conn)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(clave, valor) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    return conn


def _migrar(conn: sqlite3.Connection) -> None:
    """Actualiza bases de datos creadas con versiones anteriores sin perder datos."""
    tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for tabla in ("alumnos", "franjas"):
        if tabla in tablas:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")}
            if "usuario_id" not in cols:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE")
    if "items" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        if "nota" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN nota TEXT NOT NULL DEFAULT ''")
    if "informes" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(informes)")}
        if "estrategias" not in cols:
            conn.execute("ALTER TABLE informes ADD COLUMN estrategias TEXT DEFAULT ''")
    if "meta" in tablas:
        conn.execute("UPDATE meta SET valor = ? WHERE clave = 'schema_version'", (str(SCHEMA_VERSION),))


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]
