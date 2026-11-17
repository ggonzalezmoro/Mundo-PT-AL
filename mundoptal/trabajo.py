"""Trabajo personal de la maestra de PT/AL, fuera de las sesiones con alumnos:
lista de tareas pendientes (material, pruebas de lenguaje, correos…), agenda
mensual de citas y reuniones (familias, Orientación, profesores, terapeutas)
con sus notas, de las que cada línea se puede pasar a tarea pendiente.

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
    "reunion": "Reuniones",
    "otros": "Otros",
}
TIPOS_CITA = {
    "tutoria_familia": "Tutoría con la familia",
    "reunion_orientacion": "Reunión con Orientación",
    "reunion_profesores": "Reunión con profesores",
    "reunion_terapeutas": "Reunión con terapeutas",
    "otra": "Otra cita",
}
# Categoría que toman las tareas que salen de cada tipo de reunión
CATEGORIA_DE_CITA = {"tutoria_familia": "tutoria"}
RX_VINETA = re.compile(r"^\s*(?:[-*•·▪◦→>]+|\d{1,2}[.)]|\[\s?[xX]?\s?\]|☐|☑)\s*")
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
    for k in ("alumno_id", "cita_id"):
        if k in d:
            d[k] = int(d[k]) if d[k] not in (None, "", 0, "0") else None
    for k in ("con_quien", "lugar", "notas"):
        if k in d:
            d[k] = str(d[k] or "").strip()
    return d


# ------------------------------------------------------------------ tareas
SQL_TAREAS = """SELECT t.*, al.nombre AS alumno, ci.fecha AS cita_fecha, ci.tipo AS cita_tipo
    FROM tareas t LEFT JOIN alumnos al ON al.id = t.alumno_id LEFT JOIN citas ci ON ci.id = t.cita_id"""


def listar_tareas(store: Store, usuario_id: int | None) -> list[dict]:
    return store.q(
        f"""{SQL_TAREAS} WHERE t.usuario_id IS ?
            ORDER BY t.hecha, t.fecha_limite IS NULL, t.fecha_limite, t.orden, t.id""", (usuario_id,))


def limpiar_linea(texto: str) -> str:
    """Quita viñetas, números y casillas del principio de una línea de notas."""
    return RX_VINETA.sub("", str(texto or ""), count=1).strip()


def crear_tarea(store: Store, usuario_id: int | None, datos: dict) -> int:
    datos = {k: v for k, v in (datos or {}).items() if k in ("texto", "categoria", "alumno_id", "fecha_limite", "cita_id")}
    cita = None
    if datos.get("cita_id"):
        cita = store.q("SELECT * FROM citas WHERE id = ? AND usuario_id IS ?", (datos["cita_id"], usuario_id))
        if not cita:
            raise StoreError("La reunión no existe")
        cita = cita[0]
        datos["texto"] = limpiar_linea(datos.get("texto"))
        # Lo que no se diga hereda de la reunión: el alumno y la categoría
        if not datos.get("alumno_id"):
            datos["alumno_id"] = cita["alumno_id"]
        datos.setdefault("categoria", CATEGORIA_DE_CITA.get(cita["tipo"], "reunion"))
    d = validar("tareas", {"categoria": "otros", **datos})
    if "texto" not in d:
        raise StoreError("Escribe la tarea")
    with store.tx() as c:
        return c.execute(
            "INSERT INTO tareas(usuario_id, texto, categoria, alumno_id, fecha_limite, cita_id) VALUES (?, ?, ?, ?, ?, ?)",
            (usuario_id, d["texto"], d["categoria"], d.get("alumno_id"), d.get("fecha_limite"), d.get("cita_id"))).lastrowid


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


# ------------------------------------------------------------------ reuniones
def listar_reuniones(store: Store, usuario_id: int | None, tipo: str = "", alumno_id: int | None = None) -> list[dict]:
    """Todas las citas y reuniones (más recientes primero) con el recuento de sus tareas."""
    filtro, params = "", [usuario_id]
    if tipo:
        if tipo not in TIPOS_CITA:
            raise StoreError("Tipo de reunión no válido")
        filtro, params = filtro + " AND ci.tipo = ?", params + [tipo]
    if alumno_id:
        filtro, params = filtro + " AND ci.alumno_id = ?", params + [alumno_id]
    return store.q(
        f"""SELECT ci.*, al.nombre AS alumno,
                   (SELECT COUNT(*) FROM tareas t WHERE t.cita_id = ci.id) AS tareas_total,
                   (SELECT COUNT(*) FROM tareas t WHERE t.cita_id = ci.id AND t.hecha = 0) AS tareas_pendientes
            FROM citas ci LEFT JOIN alumnos al ON al.id = ci.alumno_id
            WHERE ci.usuario_id IS ?{filtro}
            ORDER BY ci.fecha DESC, ci.hora_inicio DESC, ci.id DESC""", params)


def obtener_reunion(store: Store, usuario_id: int | None, cita_id: int) -> dict:
    r = store.q("""SELECT ci.*, al.nombre AS alumno FROM citas ci LEFT JOIN alumnos al ON al.id = ci.alumno_id
                   WHERE ci.id = ? AND ci.usuario_id IS ?""", (cita_id, usuario_id))
    if not r:
        raise StoreError("La reunión no existe")
    r = r[0]
    r["tareas"] = store.q(f"{SQL_TAREAS} WHERE t.cita_id = ? ORDER BY t.hecha, t.id", (cita_id,))
    return r


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
