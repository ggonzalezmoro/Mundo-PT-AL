"""Trabajo personal de la maestra de PT/AL, fuera de las sesiones con alumnos:
lista de tareas pendientes (material, pruebas de lenguaje, correos…) y agenda
mensual de citas (tutorías con familias y reuniones con terapeutas).

Todo es por perfil (usuario) y se guarda solo en este equipo."""
from __future__ import annotations

import datetime as dt
import re

from .store import Store, StoreError

CATEGORIAS = {
    "material": "Material",
    "prueba": "Prueba de lenguaje",
    "correos": "Correos",
    "tutoria": "Tutoría familia",
    "reunion": "Reunión terapeutas",
    "otros": "Otros",
}
TIPOS_CITA = {
    "tutoria_familia": "Tutoría con la familia",
    "reunion_terapeutas": "Reunión con terapeutas",
    "otra": "Otra cita",
}
RX_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RX_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _fecha(v, obligatoria=False) -> str | None:
    v = (v or "").strip() if isinstance(v, str) else v
    if not v:
        if obligatoria:
            raise StoreError("Falta la fecha")
        return None
    if not RX_FECHA.match(str(v)):
        raise StoreError(f"Fecha no válida: {v!r} (AAAA-MM-DD)")
    try:
        dt.date.fromisoformat(v)
    except ValueError:
        raise StoreError(f"Fecha no válida: {v!r}") from None
    return v


def _hora(v) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if not RX_HORA.match(v):
        raise StoreError(f"Hora no válida: {v!r} (HH:MM)")
    return v


def validar(tabla: str, d: dict) -> dict:
    """Comprueba y normaliza los campos de una tarea o una cita."""
    d = dict(d)
    if "texto" in d:
        d["texto"] = str(d["texto"] or "").strip()
        if not d["texto"]:
            raise StoreError("Escribe la tarea")
    if "categoria" in d and d["categoria"] not in CATEGORIAS:
        raise StoreError("Categoría no válida")
    if "tipo" in d and d["tipo"] not in TIPOS_CITA:
        raise StoreError("Tipo de cita no válido")
    if "fecha_limite" in d:
        d["fecha_limite"] = _fecha(d["fecha_limite"])
    if "fecha" in d:
        d["fecha"] = _fecha(d["fecha"], obligatoria=True)
    if "hora_inicio" in d:
        d["hora_inicio"] = _hora(d["hora_inicio"]) or ""
    if "hora_fin" in d:
        d["hora_fin"] = _hora(d["hora_fin"])
    if "hecha" in d:
        d["hecha"] = int(bool(d["hecha"]))
    if "alumno_id" in d:
        d["alumno_id"] = int(d["alumno_id"]) if d["alumno_id"] not in (None, "", 0, "0") else None
    for k in ("con_quien", "lugar", "notas"):
        if k in d:
            d[k] = str(d[k] or "").strip()
    return d


# ------------------------------------------------------------------ tareas
def listar_tareas(store: Store, usuario_id: int | None) -> list[dict]:
    return store.q(
        """SELECT t.*, al.nombre AS alumno FROM tareas t LEFT JOIN alumnos al ON al.id = t.alumno_id
           WHERE t.usuario_id IS ? ORDER BY t.hecha, t.fecha_limite IS NULL, t.fecha_limite, t.orden, t.id""",
        (usuario_id,))


def crear_tarea(store: Store, usuario_id: int | None, datos: dict) -> int:
    d = validar("tareas", {"categoria": "otros", **{k: v for k, v in (datos or {}).items()
                                                    if k in ("texto", "categoria", "alumno_id", "fecha_limite")}})
    if "texto" not in d:
        raise StoreError("Escribe la tarea")
    with store.tx() as c:
        return c.execute(
            "INSERT INTO tareas(usuario_id, texto, categoria, alumno_id, fecha_limite) VALUES (?, ?, ?, ?, ?)",
            (usuario_id, d["texto"], d["categoria"], d.get("alumno_id"), d.get("fecha_limite"))).lastrowid


def borrar_hechas(store: Store, usuario_id: int | None) -> int:
    with store.tx() as c:
        return c.execute("DELETE FROM tareas WHERE usuario_id IS ? AND hecha = 1", (usuario_id,)).rowcount


# ------------------------------------------------------------------ citas
def listar_citas(store: Store, usuario_id: int | None, desde: str, hasta: str,
                 alumno_id: int | None = None) -> list[dict]:
    desde, hasta = _fecha(desde, True), _fecha(hasta, True)
    filtro, params = "", [usuario_id, desde, hasta]
    if alumno_id:
        filtro, params = " AND ci.alumno_id = ?", params + [alumno_id]
    return store.q(
        f"""SELECT ci.*, al.nombre AS alumno FROM citas ci LEFT JOIN alumnos al ON al.id = ci.alumno_id
            WHERE ci.usuario_id IS ? AND ci.fecha BETWEEN ? AND ?{filtro}
            ORDER BY ci.fecha, ci.hora_inicio, ci.id""", params)


def citas_alumno(store: Store, alumno_id: int) -> list[dict]:
    return store.q("SELECT * FROM citas WHERE alumno_id = ? ORDER BY fecha DESC, hora_inicio DESC", (alumno_id,))


def crear_cita(store: Store, usuario_id: int | None, datos: dict) -> int:
    campos = ("fecha", "hora_inicio", "hora_fin", "tipo", "alumno_id", "con_quien", "lugar", "notas")
    d = validar("citas", {"tipo": "otra", "fecha": "", **{k: v for k, v in (datos or {}).items() if k in campos}})
    with store.tx() as c:
        return c.execute(
            """INSERT INTO citas(usuario_id, fecha, hora_inicio, hora_fin, tipo, alumno_id, con_quien, lugar, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario_id, d["fecha"], d.get("hora_inicio") or "", d.get("hora_fin"), d["tipo"], d.get("alumno_id"),
             d.get("con_quien", ""), d.get("lugar", ""), d.get("notas", ""))).lastrowid


def rango_mes(mes: str) -> tuple[str, str]:
    """«2026-11» → primer y último día visibles en un calendario de lunes a domingo."""
    try:
        a, m = (int(x) for x in mes.split("-")[:2])
        primero = dt.date(a, m, 1)
    except (ValueError, AttributeError):
        raise StoreError(f"Mes no válido: {mes!r} (AAAA-MM)") from None
    siguiente = dt.date(a + (m == 12), m % 12 + 1, 1)
    ini = primero - dt.timedelta(days=primero.weekday())
    fin = siguiente - dt.timedelta(days=1)
    fin += dt.timedelta(days=6 - fin.weekday())
    return ini.isoformat(), fin.isoformat()


def avisos(store: Store, usuario_id: int | None, hoy: dt.date | None = None) -> dict:
    """Citas de hoy y mañana, y tareas vencidas o que vencen hoy."""
    hoy = hoy or dt.date.today()
    manana = hoy + dt.timedelta(days=1)
    citas = listar_citas(store, usuario_id, hoy.isoformat(), manana.isoformat())
    vencidas = store.q(
        """SELECT t.*, al.nombre AS alumno FROM tareas t LEFT JOIN alumnos al ON al.id = t.alumno_id
           WHERE t.usuario_id IS ? AND t.hecha = 0 AND t.fecha_limite IS NOT NULL AND t.fecha_limite <= ?
           ORDER BY t.fecha_limite""", (usuario_id, hoy.isoformat()))
    return {"hoy": hoy.isoformat(), "manana": manana.isoformat(),
            "citas": [c for c in citas if not c["hecha"]], "tareas_vencidas": vencidas}
