"""Base de datos local SQLite (incluida en Python, no necesita instalación)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 15

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
    creado TEXT DEFAULT CURRENT_TIMESTAMP,
    -- 'aci': con Adaptación Curricular; 'observacion': en valoración, sin ACI (informe de observación)
    seguimiento TEXT NOT NULL DEFAULT 'aci' CHECK (seguimiento IN ('aci', 'observacion'))
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
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    -- Franja que ya no está en el horario: se guarda solo para conservar las sesiones pasadas y sus notas
    archivada INTEGER NOT NULL DEFAULT 0
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
    falta INTEGER NOT NULL DEFAULT 0,
    motivo TEXT DEFAULT '',
    UNIQUE (franja_id, alumno_id, fecha)
);

CREATE TABLE IF NOT EXISTS sesion_items (
    sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    trabajado INTEGER NOT NULL DEFAULT 0,
    observacion TEXT NOT NULL DEFAULT '',  -- apunte rápido de la maestra sobre el ítem en esa sesión
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

-- Informe de observación: alumnos sin ACI (en valoración) y cómo se muestran en las sesiones
CREATE TABLE IF NOT EXISTS informes_observacion (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL DEFAULT 'INFORME DE OBSERVACIÓN',
    curso TEXT DEFAULT '',
    curso_escolar TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL DEFAULT '',        -- fecha del informe (AAAA-MM-DD)
    desde TEXT NOT NULL DEFAULT '',        -- periodo observado
    hasta TEXT NOT NULL DEFAULT '',        -- vacío: hasta hoy
    maestra TEXT DEFAULT '',
    destinatario TEXT DEFAULT '',          -- p. ej. Departamento de Orientación
    creado TEXT DEFAULT CURRENT_TIMESTAMP,
    actualizado TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS observacion_apartados (
    id INTEGER PRIMARY KEY,
    informe_id INTEGER NOT NULL REFERENCES informes_observacion(id) ON DELETE CASCADE,
    clave TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    texto TEXT DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0
);

-- Trabajo personal de la maestra: tareas pendientes y agenda mensual de citas
CREATE TABLE IF NOT EXISTS tareas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    texto TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT 'otros',
    alumno_id INTEGER REFERENCES alumnos(id) ON DELETE SET NULL,
    fecha_limite TEXT,
    hecha INTEGER NOT NULL DEFAULT 0,
    hecha_en TEXT,
    orden INTEGER NOT NULL DEFAULT 0,
    creada TEXT DEFAULT CURRENT_TIMESTAMP,
    cita_id INTEGER REFERENCES citas(id) ON DELETE SET NULL  -- reunión de la que salió la tarea
);

CREATE TABLE IF NOT EXISTS citas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    hora_inicio TEXT NOT NULL DEFAULT '',
    hora_fin TEXT,
    tipo TEXT NOT NULL DEFAULT 'otra',
    alumno_id INTEGER REFERENCES alumnos(id) ON DELETE SET NULL,
    con_quien TEXT NOT NULL DEFAULT '',
    lugar TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    hecha INTEGER NOT NULL DEFAULT 0
);

-- Material creado (fichas de Word y diapositivas de PowerPoint)
CREATE TABLE IF NOT EXISTS materiales (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    alumno_id INTEGER REFERENCES alumnos(id) ON DELETE SET NULL,
    titulo TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT '',
    origen TEXT NOT NULL DEFAULT 'plantilla',
    formato TEXT NOT NULL DEFAULT 'docx',
    paginas INTEGER NOT NULL DEFAULT 0,
    ruta TEXT NOT NULL DEFAULT '',
    drive_id TEXT NOT NULL DEFAULT '',   -- copia en Google Drive (Documentos/Presentaciones de Google)
    drive_url TEXT NOT NULL DEFAULT '',
    creado TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Calendarios externos de solo lectura (Google Calendar…). La URL pública se guarda aquí (viaja al
-- exportar los datos); la secreta (/private-…) NUNCA: va al keyring con el nombre «clave_secreta».
CREATE TABLE IF NOT EXISTS calendarios_externos (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#2B7BB9',
    origen TEXT NOT NULL DEFAULT 'url',
    url_publica TEXT NOT NULL DEFAULT '',
    clave_secreta TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT 'colegio',
    visible INTEGER NOT NULL DEFAULT 1,
    actualizado TEXT,
    error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS eventos_externos (
    id INTEGER PRIMARY KEY,
    calendario_id INTEGER NOT NULL REFERENCES calendarios_externos(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    uid TEXT NOT NULL DEFAULT '',
    inicio TEXT NOT NULL,
    fin TEXT NOT NULL,
    todo_el_dia INTEGER NOT NULL DEFAULT 0,
    titulo TEXT NOT NULL DEFAULT '',
    lugar TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL DEFAULT ''
);

-- Juntas de evaluación: una por perfil, curso y trimestre, con notas por alumno que después se
-- redactan para el informe del trimestre (informe a familias o informe de observación)
CREATE TABLE IF NOT EXISTS juntas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    curso_escolar TEXT NOT NULL DEFAULT '',
    trimestre INTEGER NOT NULL DEFAULT 1 CHECK (trimestre BETWEEN 1 AND 3),
    fecha TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    creado TEXT DEFAULT CURRENT_TIMESTAMP,
    actualizado TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS junta_alumnos (
    id INTEGER PRIMARY KEY,
    junta_id INTEGER NOT NULL REFERENCES juntas(id) ON DELETE CASCADE,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    notas TEXT NOT NULL DEFAULT '',
    pasado TEXT,          -- cuándo se pasó por última vez al informe
    actualizado TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (junta_id, alumno_id)
);

CREATE INDEX IF NOT EXISTS ix_juntas_usuario ON juntas(usuario_id, curso_escolar, trimestre);
CREATE INDEX IF NOT EXISTS ix_eventos_ext ON eventos_externos(usuario_id, inicio);
CREATE INDEX IF NOT EXISTS ix_materiales_usuario ON materiales(usuario_id);
CREATE INDEX IF NOT EXISTS ix_tareas_usuario ON tareas(usuario_id);
CREATE INDEX IF NOT EXISTS ix_tareas_cita ON tareas(cita_id);
CREATE INDEX IF NOT EXISTS ix_citas_fecha ON citas(usuario_id, fecha);
CREATE INDEX IF NOT EXISTS ix_acis_alumno ON acis(alumno_id);
CREATE INDEX IF NOT EXISTS ix_informes_alumno ON informes(alumno_id);
CREATE INDEX IF NOT EXISTS ix_infareas_informe ON informe_areas(informe_id);
CREATE INDEX IF NOT EXISTS ix_infobs_alumno ON informes_observacion(alumno_id);
CREATE INDEX IF NOT EXISTS ix_obsap_informe ON observacion_apartados(informe_id);
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
    if "alumnos" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(alumnos)")}
        if "seguimiento" not in cols:
            conn.execute("ALTER TABLE alumnos ADD COLUMN seguimiento TEXT NOT NULL DEFAULT 'aci' "
                         "CHECK (seguimiento IN ('aci', 'observacion'))")
    if "franjas" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(franjas)")}
        if "archivada" not in cols:
            conn.execute("ALTER TABLE franjas ADD COLUMN archivada INTEGER NOT NULL DEFAULT 0")
    if "items" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        if "nota" not in cols:
            conn.execute("ALTER TABLE items ADD COLUMN nota TEXT NOT NULL DEFAULT ''")
    if "informes" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(informes)")}
        if "estrategias" not in cols:
            conn.execute("ALTER TABLE informes ADD COLUMN estrategias TEXT DEFAULT ''")
    if "sesiones" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sesiones)")}
        if "falta" not in cols:
            conn.execute("ALTER TABLE sesiones ADD COLUMN falta INTEGER NOT NULL DEFAULT 0")
        if "motivo" not in cols:
            conn.execute("ALTER TABLE sesiones ADD COLUMN motivo TEXT DEFAULT ''")
    if "sesion_items" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sesion_items)")}
        if "observacion" not in cols:
            conn.execute("ALTER TABLE sesion_items ADD COLUMN observacion TEXT NOT NULL DEFAULT ''")
    if "calendarios_externos" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(calendarios_externos)")}
        for col, tipo in (("url_publica", "TEXT NOT NULL DEFAULT ''"), ("clave_secreta", "TEXT NOT NULL DEFAULT ''"),
                          ("tipo", "TEXT NOT NULL DEFAULT 'colegio'"), ("visible", "INTEGER NOT NULL DEFAULT 1")):
            if col not in cols:
                conn.execute(f"ALTER TABLE calendarios_externos ADD COLUMN {col} {tipo}")
    if "tareas" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tareas)")}
        if "cita_id" not in cols:
            conn.execute("ALTER TABLE tareas ADD COLUMN cita_id INTEGER REFERENCES citas(id) ON DELETE SET NULL")
    if "materiales" in tablas:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(materiales)")}
        for col in ("drive_id", "drive_url"):
            if col not in cols:
                conn.execute(f"ALTER TABLE materiales ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    if "meta" in tablas:
        conn.execute("UPDATE meta SET valor = ? WHERE clave = 'schema_version'", (str(SCHEMA_VERSION),))


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]
