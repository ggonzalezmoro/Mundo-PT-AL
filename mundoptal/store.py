"""Acceso a datos: alumnos, ACIs y su jerarquía Área > Subárea > Competencia > Ítem."""
from __future__ import annotations

import threading
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from . import db
from .config import ESCALA

# Tabla hija -> (tabla padre, columna que apunta al padre)
JERARQUIA = {
    "areas": ("acis", "aci_id"),
    "subareas": ("areas", "area_id"),
    "competencias": ("subareas", "subarea_id"),
    "items": ("competencias", "competencia_id"),
}

CAMPOS_EDITABLES = {
    "usuarios": {"nombre", "especialidad"},
    "alumnos": {"nombre", "curso", "observaciones", "activo"},
    "acis": {"curso", "curso_escolar", "trimestre", "titulo", "materia", "prof_area",
             "prof_ptal", "observaciones"},
    "adaptaciones": {"area", "tipo", "nivel_curricular", "orden"},
    "areas": {"nombre", "especialidad", "orden"},
    "subareas": {"nombre", "orden"},
    "competencias": {"nombre", "orden"},
    "items": {"texto", "eval_1t", "eval_2t", "eval_3t", "destacado", "nota", "orden"},
    "informes": {"curso", "maestra", "prof_area", "social", "actitud_pt", "actitud_al", "valoracion",
                 "orientaciones", "despedida"},
    "informe_areas": {"area", "texto", "orden"},
}

ADAPTACIONES_POR_DEFECTO = [
    "CRECIMIENTO EN ARMONÍA",
    "DESCUBRIMIENTO Y EXPLORACIÓN DEL ENTORNO",
    "COMUNICACIÓN Y REPRESENTACIÓN DE LA REALIDAD",
    "MÚSICA",
    "INGLÉS",
]


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni espacios sobrantes (para comparar nombres)."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().replace(":", " ").split())


class StoreError(ValueError):
    pass


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = db.connect(self.path)
        self.lock = threading.RLock()

    # ------------------------------------------------------------ utilidades
    @contextmanager
    def tx(self):
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")

    def q(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            return db.rows(self.conn.execute(sql, params))

    def q1(self, sql: str, params=()) -> dict | None:
        r = self.q(sql, params)
        return r[0] if r else None

    def _siguiente_orden(self, tabla: str, col: str, padre_id: int) -> int:
        r = self.conn.execute(
            f"SELECT COALESCE(MAX(orden), -1) + 1 FROM {tabla} WHERE {col} = ?", (padre_id,)
        ).fetchone()
        return r[0]

    def _tocar_aci(self, aci_id: int | None):
        if aci_id:
            self.conn.execute(
                "UPDATE acis SET actualizado = CURRENT_TIMESTAMP WHERE id = ?", (aci_id,)
            )

    def aci_de(self, tabla: str, id_: int) -> int | None:
        """Devuelve el id de la ACI a la que pertenece un nodo de la jerarquía."""
        sql = {
            "acis": "SELECT id FROM acis WHERE id = ?",
            "adaptaciones": "SELECT aci_id FROM adaptaciones WHERE id = ?",
            "areas": "SELECT aci_id FROM areas WHERE id = ?",
            "subareas": "SELECT a.aci_id FROM subareas s JOIN areas a ON a.id = s.area_id WHERE s.id = ?",
            "competencias": """SELECT a.aci_id FROM competencias c JOIN subareas s ON s.id = c.subarea_id
                               JOIN areas a ON a.id = s.area_id WHERE c.id = ?""",
            "items": """SELECT a.aci_id FROM items i JOIN competencias c ON c.id = i.competencia_id
                        JOIN subareas s ON s.id = c.subarea_id JOIN areas a ON a.id = s.area_id
                        WHERE i.id = ?""",
        }.get(tabla)
        if not sql:
            return None
        r = self.conn.execute(sql, (id_,)).fetchone()
        return r[0] if r else None

    # ------------------------------------------------------------ usuarios (perfiles)
    def listar_usuarios(self) -> list[dict]:
        return self.q(
            """SELECT u.*, (SELECT COUNT(*) FROM alumnos WHERE usuario_id = u.id AND activo = 1) AS num_alumnos
               FROM usuarios u ORDER BY u.nombre COLLATE NOCASE"""
        )

    def crear_usuario(self, nombre: str, especialidad: str = "PT/AL") -> int:
        nombre = (nombre or "").strip()
        if not nombre:
            raise StoreError("El nombre del perfil es obligatorio")
        if especialidad not in ("PT", "AL", "PT/AL"):
            raise StoreError("Especialidad no válida (PT, AL o PT/AL)")
        with self.tx():
            primero = not self.conn.execute("SELECT 1 FROM usuarios").fetchone()
            uid = self.conn.execute(
                "INSERT INTO usuarios(nombre, especialidad) VALUES (?, ?)", (nombre, especialidad)
            ).lastrowid
            if primero:
                # Los datos creados antes de existir perfiles pasan al primer perfil
                self.conn.execute("UPDATE alumnos SET usuario_id = ? WHERE usuario_id IS NULL", (uid,))
                self.conn.execute("UPDATE franjas SET usuario_id = ? WHERE usuario_id IS NULL", (uid,))
            return uid

    def obtener_usuario(self, usuario_id: int) -> dict | None:
        return self.q1("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))

    def buscar_usuario(self, nombre: str) -> dict | None:
        for u in self.listar_usuarios():
            if normalizar(u["nombre"]) == normalizar(nombre):
                return u
        return None

    # ------------------------------------------------------------ alumnos
    def listar_alumnos(self, usuario_id: int | None = None, incluir_inactivos: bool = False) -> list[dict]:
        condiciones, params = [], []
        if not incluir_inactivos:
            condiciones.append("al.activo = 1")
        if usuario_id is not None:
            condiciones.append("al.usuario_id = ?")
            params.append(usuario_id)
        where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
        return self.q(
            f"""SELECT al.*, (SELECT COUNT(*) FROM acis WHERE alumno_id = al.id) AS num_acis,
                       (SELECT MAX(id) FROM acis WHERE alumno_id = al.id) AS aci_vigente_id
                FROM alumnos al {where} ORDER BY al.nombre COLLATE NOCASE""",
            params,
        )

    def crear_alumno(self, nombre: str, curso: str = "", observaciones: str = "",
                     usuario_id: int | None = None) -> int:
        nombre = (nombre or "").strip()
        if not nombre:
            raise StoreError("El nombre del alumno es obligatorio")
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO alumnos(nombre, curso, observaciones, usuario_id) VALUES (?, ?, ?, ?)",
                (nombre, curso or "", observaciones or "", usuario_id),
            )
            return cur.lastrowid

    def buscar_alumno(self, nombre: str, usuario_id: int | None = None) -> dict | None:
        for a in self.listar_alumnos(usuario_id, incluir_inactivos=True):
            if normalizar(a["nombre"]) == normalizar(nombre):
                return a
        return None

    def obtener_alumno(self, alumno_id: int) -> dict | None:
        al = self.q1("SELECT * FROM alumnos WHERE id = ?", (alumno_id,))
        if al:
            al["acis"] = self.q(
                "SELECT id, curso_escolar, trimestre, curso, actualizado FROM acis WHERE alumno_id = ? ORDER BY id DESC",
                (alumno_id,),
            )
            al["informes"] = self.q(
                """SELECT id, trimestre, curso_escolar, actualizado FROM informes WHERE alumno_id = ?
                   ORDER BY curso_escolar DESC, trimestre DESC""", (alumno_id,))
        return al

    # ------------------------------------------------------------ edición genérica
    def actualizar(self, tabla: str, id_: int, cambios: dict) -> None:
        permitidos = CAMPOS_EDITABLES.get(tabla)
        if not permitidos:
            raise StoreError(f"Tabla no editable: {tabla}")
        cambios = {k: v for k, v in (cambios or {}).items() if k in permitidos}
        for k in ("eval_1t", "eval_2t", "eval_3t"):
            if k in cambios and cambios[k] not in ("", *ESCALA):
                raise StoreError(f"Valor de evaluación no válido: {cambios[k]}")
        if not cambios:
            return
        sets = ", ".join(f"{k} = ?" for k in cambios)
        with self.tx():
            self.conn.execute(f"UPDATE {tabla} SET {sets} WHERE id = ?", (*cambios.values(), id_))
            self._tocar_aci(self.aci_de(tabla, id_))
            if tabla == "informes":
                self.conn.execute("UPDATE informes SET actualizado = CURRENT_TIMESTAMP WHERE id = ?", (id_,))
            elif tabla == "informe_areas":
                self.conn.execute("""UPDATE informes SET actualizado = CURRENT_TIMESTAMP
                                     WHERE id = (SELECT informe_id FROM informe_areas WHERE id = ?)""", (id_,))

    def borrar(self, tabla: str, id_: int) -> None:
        if tabla not in CAMPOS_EDITABLES:
            raise StoreError(f"Tabla no válida: {tabla}")
        with self.tx():
            aci = self.aci_de(tabla, id_) if tabla != "acis" else None
            self.conn.execute(f"DELETE FROM {tabla} WHERE id = ?", (id_,))
            self._tocar_aci(aci)

    def mover(self, tabla: str, id_: int, direccion: int) -> None:
        """Sube (-1) o baja (+1) un elemento entre sus hermanos."""
        if tabla == "adaptaciones":
            padre_col = "aci_id"
        elif tabla in JERARQUIA:
            padre_col = JERARQUIA[tabla][1]
        else:
            raise StoreError(f"Tabla no válida: {tabla}")
        with self.tx():
            fila = self.conn.execute(f"SELECT {padre_col} AS p FROM {tabla} WHERE id = ?", (id_,)).fetchone()
            if not fila:
                return
            hermanos = [r[0] for r in self.conn.execute(
                f"SELECT id FROM {tabla} WHERE {padre_col} = ? ORDER BY orden, id", (fila["p"],))]
            i = hermanos.index(id_)
            j = i + (1 if direccion > 0 else -1)
            if 0 <= j < len(hermanos):
                hermanos[i], hermanos[j] = hermanos[j], hermanos[i]
            for pos, hid in enumerate(hermanos):
                self.conn.execute(f"UPDATE {tabla} SET orden = ? WHERE id = ?", (pos, hid))
            self._tocar_aci(self.aci_de(tabla, id_))

    def crear_hijo(self, tabla: str, padre_id: int, datos: dict | None = None) -> int:
        """Crea un área, subárea, competencia o ítem bajo su padre."""
        datos = dict(datos or {})
        if tabla == "adaptaciones":
            padre_col = "aci_id"
        elif tabla in JERARQUIA:
            padre_col = JERARQUIA[tabla][1]
        else:
            raise StoreError(f"Tabla no válida: {tabla}")
        permitidos = CAMPOS_EDITABLES[tabla]
        datos = {k: v for k, v in datos.items() if k in permitidos}
        with self.tx():
            datos.setdefault("orden", self._siguiente_orden(tabla, padre_col, padre_id))
            cols = [padre_col, *datos.keys()]
            cur = self.conn.execute(
                f"INSERT INTO {tabla}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                (padre_id, *datos.values()),
            )
            self._tocar_aci(self.aci_de(tabla, cur.lastrowid))
            return cur.lastrowid

    # ------------------------------------------------------------ ACIs
    def crear_aci(self, alumno_id: int, datos: dict | None = None, con_adaptaciones: bool = True) -> int:
        datos = {k: v for k, v in (datos or {}).items() if k in CAMPOS_EDITABLES["acis"]}
        al = self.q1("SELECT * FROM alumnos WHERE id = ?", (alumno_id,))
        if not al:
            raise StoreError("Alumno no encontrado")
        datos.setdefault("curso", al["curso"])
        with self.tx():
            cols = ["alumno_id", *datos.keys()]
            cur = self.conn.execute(
                f"INSERT INTO acis({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                (alumno_id, *datos.values()),
            )
            aci_id = cur.lastrowid
            if con_adaptaciones:
                for i, area in enumerate(ADAPTACIONES_POR_DEFECTO):
                    self.conn.execute(
                        "INSERT INTO adaptaciones(aci_id, area, orden) VALUES (?, ?, ?)", (aci_id, area, i)
                    )
            return aci_id

    def aci_vigente(self, alumno_id: int) -> int | None:
        r = self.conn.execute("SELECT MAX(id) FROM acis WHERE alumno_id = ?", (alumno_id,)).fetchone()
        return r[0] if r else None

    def obtener_aci(self, aci_id: int) -> dict | None:
        with self.lock:
            aci = self.q1(
                """SELECT acis.*, alumnos.nombre AS alumno_nombre FROM acis
                   JOIN alumnos ON alumnos.id = acis.alumno_id WHERE acis.id = ?""",
                (aci_id,),
            )
            if not aci:
                return None
            aci["adaptaciones"] = self.q(
                "SELECT * FROM adaptaciones WHERE aci_id = ? ORDER BY orden, id", (aci_id,)
            )
            areas = self.q("SELECT * FROM areas WHERE aci_id = ? ORDER BY orden, id", (aci_id,))
            subs = self.q(
                """SELECT s.* FROM subareas s JOIN areas a ON a.id = s.area_id
                   WHERE a.aci_id = ? ORDER BY s.orden, s.id""", (aci_id,))
            comps = self.q(
                """SELECT c.* FROM competencias c JOIN subareas s ON s.id = c.subarea_id
                   JOIN areas a ON a.id = s.area_id WHERE a.aci_id = ? ORDER BY c.orden, c.id""", (aci_id,))
            items = self.q(
                """SELECT i.* FROM items i JOIN competencias c ON c.id = i.competencia_id
                   JOIN subareas s ON s.id = c.subarea_id JOIN areas a ON a.id = s.area_id
                   WHERE a.aci_id = ? ORDER BY i.orden, i.id""", (aci_id,))
        por_comp: dict[int, list] = {}
        for it in items:
            por_comp.setdefault(it["competencia_id"], []).append(it)
        por_sub: dict[int, list] = {}
        for c in comps:
            c["items"] = por_comp.get(c["id"], [])
            por_sub.setdefault(c["subarea_id"], []).append(c)
        por_area: dict[int, list] = {}
        for s in subs:
            s["competencias"] = por_sub.get(s["id"], [])
            por_area.setdefault(s["area_id"], []).append(s)
        for a in areas:
            a["subareas"] = por_area.get(a["id"], [])
        aci["areas"] = areas
        aci["resumen"] = resumen_evaluacion(aci)
        return aci

    def duplicar_aci(self, aci_id: int, siguiente_trimestre: bool = True) -> int:
        """Copia una ACI completa (útil para la revisión del trimestre siguiente).
        Las evaluaciones ya registradas se conservan."""
        aci = self.obtener_aci(aci_id)
        if not aci:
            raise StoreError("ACI no encontrada")
        trimestre = aci["trimestre"]
        if siguiente_trimestre:
            trimestre = min(3, trimestre + 1)
        datos = {k: aci[k] for k in CAMPOS_EDITABLES["acis"]}
        datos["trimestre"] = trimestre
        nuevo = self.crear_aci(aci["alumno_id"], datos, con_adaptaciones=False)
        self.importar_arbol(nuevo, aci, conservar_evaluaciones=True)
        return nuevo

    def importar_arbol(self, aci_id: int, arbol: dict, conservar_evaluaciones: bool = True) -> None:
        """Inserta adaptaciones y áreas (formato de obtener_aci) en una ACI."""
        with self.tx():
            for i, ad in enumerate(arbol.get("adaptaciones", [])):
                self.conn.execute(
                    "INSERT INTO adaptaciones(aci_id, area, tipo, nivel_curricular, orden) VALUES (?,?,?,?,?)",
                    (aci_id, ad.get("area", ""), ad.get("tipo", ""), ad.get("nivel_curricular", ""), i),
                )
            base = self._siguiente_orden("areas", "aci_id", aci_id)
            for ia, a in enumerate(arbol.get("areas", [])):
                area_id = self.conn.execute(
                    "INSERT INTO areas(aci_id, nombre, especialidad, orden) VALUES (?,?,?,?)",
                    (aci_id, a.get("nombre", ""), a.get("especialidad", ""), base + ia),
                ).lastrowid
                for isub, s in enumerate(a.get("subareas", [])):
                    sub_id = self.conn.execute(
                        "INSERT INTO subareas(area_id, nombre, orden) VALUES (?,?,?)",
                        (area_id, s.get("nombre", ""), isub),
                    ).lastrowid
                    for ic, c in enumerate(s.get("competencias", [])):
                        comp_id = self.conn.execute(
                            "INSERT INTO competencias(subarea_id, nombre, orden) VALUES (?,?,?)",
                            (sub_id, c.get("nombre", ""), ic),
                        ).lastrowid
                        for ii, it in enumerate(c.get("items", [])):
                            ev = [it.get(k, "") if conservar_evaluaciones else "" for k in ("eval_1t", "eval_2t", "eval_3t")]
                            ev = [e if e in ESCALA else "" for e in ev]
                            self.conn.execute(
                                """INSERT INTO items(competencia_id, texto, eval_1t, eval_2t, eval_3t, destacado, nota, orden)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (comp_id, it.get("texto", ""), *ev, int(bool(it.get("destacado"))),
                                 it.get("nota", "") or "", ii),
                            )
            self._tocar_aci(aci_id)

    # ------------------------------------------------------------ dictado
    def fusionar_dictado(self, aci_id: int, arbol: list[dict], contexto: dict | None = None) -> dict:
        """Añade a la ACI lo dictado. Si un área/subárea/competencia ya existe
        (mismo nombre, sin importar tildes ni mayúsculas) se reutiliza.

        `contexto` puede indicar area_id / subarea_id / competencia_id donde
        colocar lo que se dicte sin nivel superior."""
        contexto = contexto or {}
        creados = {"areas": 0, "subareas": 0, "competencias": 0, "items": 0}

        def buscar_o_crear(tabla, col, padre_id, nombre, extra=None):
            for r in self.conn.execute(f"SELECT id, nombre FROM {tabla} WHERE {col} = ?", (padre_id,)):
                if normalizar(r["nombre"]) == normalizar(nombre):
                    return r["id"]
            orden = self._siguiente_orden(tabla, col, padre_id)
            extra = extra or {}
            cols = [col, "nombre", "orden", *extra.keys()]
            creados[tabla] += 1
            return self.conn.execute(
                f"INSERT INTO {tabla}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                (padre_id, nombre, orden, *extra.values()),
            ).lastrowid

        with self.tx():
            if not self.conn.execute("SELECT 1 FROM acis WHERE id = ?", (aci_id,)).fetchone():
                raise StoreError("ACI no encontrada")
            for a in arbol:
                if a.get("nombre"):
                    area_id = buscar_o_crear("areas", "aci_id", aci_id, a["nombre"],
                                             {"especialidad": a.get("especialidad", "")})
                elif contexto.get("area_id"):
                    area_id = int(contexto["area_id"])
                else:
                    area_id = buscar_o_crear("areas", "aci_id", aci_id, "Nueva área")
                for s in a.get("subareas", []):
                    if s.get("nombre"):
                        sub_id = buscar_o_crear("subareas", "area_id", area_id, s["nombre"])
                    elif contexto.get("subarea_id") and not a.get("nombre"):
                        sub_id = int(contexto["subarea_id"])
                    else:
                        sub_id = buscar_o_crear("subareas", "area_id", area_id, "")
                    for c in s.get("competencias", []):
                        if c.get("nombre"):
                            comp_id = buscar_o_crear("competencias", "subarea_id", sub_id, c["nombre"])
                        elif contexto.get("competencia_id") and not a.get("nombre") and not s.get("nombre"):
                            comp_id = int(contexto["competencia_id"])
                        else:
                            comp_id = buscar_o_crear("competencias", "subarea_id", sub_id, "")
                        for texto in c.get("items", []):
                            orden = self._siguiente_orden("items", "competencia_id", comp_id)
                            self.conn.execute(
                                "INSERT INTO items(competencia_id, texto, orden) VALUES (?,?,?)",
                                (comp_id, texto, orden),
                            )
                            creados["items"] += 1
            self._tocar_aci(aci_id)
        return creados


def evaluacion_actual(item: dict, trimestre: int) -> str:
    """Evaluación vigente de un ítem: la del trimestre de la ACI o, si está
    vacía, la del último trimestre anterior evaluado."""
    for t in range(trimestre, 0, -1):
        v = item.get(f"eval_{t}t") or ""
        if v:
            return v
    return ""


def resumen_evaluacion(aci: dict) -> dict:
    cuenta = {k: 0 for k in ["", *ESCALA]}
    total = 0
    for a in aci.get("areas", []):
        for s in a["subareas"]:
            for c in s["competencias"]:
                for it in c["items"]:
                    total += 1
                    cuenta[evaluacion_actual(it, aci["trimestre"])] += 1
    return {
        "total": total,
        "conseguidos": cuenta["C"],
        "pendientes": total - cuenta["C"],
        "por_valor": {("sin evaluar" if k == "" else k): v for k, v in cuenta.items()},
    }
