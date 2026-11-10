"""Horario del maestro y planificación automática de sesiones.

Cada franja del horario de tipo «sesión» tiene uno o varios alumnos. Al
planificar un rango de fechas, para cada alumno y franja se crea una sesión y
se le asignan los ítems pendientes (no «C») de su ACI vigente:

  1. Primero los ítems que menos veces se han programado (rotación).
  2. Después los que hace más tiempo que no se trabajan.
  3. Después los de menor nivel de logro (NI antes que I, ED, ED+).
  4. Se procura repartir entre competencias distintas en la misma sesión.

Si la franja es de AL o de PT, solo se eligen ítems de áreas marcadas con esa
especialidad (o sin especialidad marcada).
"""
from __future__ import annotations

import datetime as dt

from .config import ESCALA
from .store import Store, StoreError, evaluacion_actual

RANGO_LOGRO = {"": 0, "NI": 0, "I": 1, "ED": 2, "ED+": 3, "C": 4}


def _fecha(s: str | dt.date) -> dt.date:
    if isinstance(s, dt.date):
        return s
    return dt.date.fromisoformat(s)


def lunes_de(fecha: str | dt.date) -> dt.date:
    d = _fecha(fecha)
    return d - dt.timedelta(days=d.weekday())


class Planificador:
    def __init__(self, store: Store):
        self.s = store

    # ------------------------------------------------------------ horario
    def listar_franjas(self, usuario_id: int | None = None) -> list[dict]:
        if usuario_id is None:
            franjas = self.s.q("SELECT * FROM franjas ORDER BY dia, inicio, id")
        else:
            franjas = self.s.q("SELECT * FROM franjas WHERE usuario_id = ? ORDER BY dia, inicio, id", (usuario_id,))
        rel = self.s.q(
            """SELECT fa.franja_id, al.id, al.nombre FROM franja_alumnos fa
               JOIN alumnos al ON al.id = fa.alumno_id ORDER BY al.nombre"""
        )
        por_franja: dict[int, list] = {}
        for r in rel:
            por_franja.setdefault(r["franja_id"], []).append({"id": r["id"], "nombre": r["nombre"]})
        for f in franjas:
            f["alumnos"] = por_franja.get(f["id"], [])
        return franjas

    def guardar_franja(self, datos: dict, franja_id: int | None = None, usuario_id: int | None = None) -> int:
        dia = int(datos.get("dia", -1))
        inicio, fin = str(datos.get("inicio", "")), str(datos.get("fin", ""))
        if not 0 <= dia <= 4:
            raise StoreError("Día no válido")
        for h in (inicio, fin):
            try:
                dt.time.fromisoformat(h)
            except ValueError:
                raise StoreError(f"Hora no válida: {h!r} (formato HH:MM)") from None
        if fin <= inicio:
            raise StoreError("La hora de fin debe ser posterior a la de inicio")
        tipo = datos.get("tipo", "sesion")
        especialidad = datos.get("especialidad", "PT/AL")
        n_items = max(1, min(10, int(datos.get("items_por_sesion", 3) or 3)))
        alumnos = [int(a) for a in datos.get("alumnos", [])]
        if tipo not in ("sesion", "otro"):
            raise StoreError("Tipo de franja no válido")
        if especialidad not in ("PT", "AL", "PT/AL"):
            raise StoreError("Especialidad no válida")
        valores = (dia, inicio, fin, tipo, datos.get("etiqueta", ""), especialidad, n_items)
        with self.s.tx() as c:
            # Solapes con otras franjas del mismo día
            solape = c.execute(
                """SELECT id FROM franjas WHERE dia = ? AND inicio < ? AND fin > ? AND id IS NOT ?
                   AND usuario_id IS ?""",
                (dia, fin, inicio, franja_id, usuario_id),
            ).fetchone()
            if solape:
                raise StoreError("La franja se solapa con otra del mismo día")
            if franja_id:
                c.execute(
                    """UPDATE franjas SET dia=?, inicio=?, fin=?, tipo=?, etiqueta=?, especialidad=?,
                       items_por_sesion=? WHERE id=?""", (*valores, franja_id))
                c.execute("DELETE FROM franja_alumnos WHERE franja_id = ?", (franja_id,))
            else:
                franja_id = c.execute(
                    """INSERT INTO franjas(dia, inicio, fin, tipo, etiqueta, especialidad, items_por_sesion, usuario_id)
                       VALUES (?,?,?,?,?,?,?,?)""", (*valores, usuario_id)).lastrowid
            for a in alumnos:
                c.execute("INSERT OR IGNORE INTO franja_alumnos VALUES (?, ?)", (franja_id, a))
        return franja_id

    def borrar_franja(self, franja_id: int) -> None:
        with self.s.tx() as c:
            c.execute("DELETE FROM franjas WHERE id = ?", (franja_id,))

    # ------------------------------------------------------------ ítems pendientes
    def items_pendientes(self, alumno_id: int, especialidad: str = "PT/AL") -> list[dict]:
        aci_id = self.s.aci_vigente(alumno_id)
        if not aci_id:
            return []
        aci = self.s.q1("SELECT trimestre FROM acis WHERE id = ?", (aci_id,))
        filtro = ""
        params: list = [aci_id]
        if especialidad in ("PT", "AL"):
            filtro = "AND a.especialidad IN ('', ?)"
            params.append(especialidad)
        filas = self.s.q(
            f"""SELECT i.*, c.nombre AS competencia, c.id AS comp_id, s.nombre AS subarea,
                       a.nombre AS area, a.especialidad,
                       (SELECT COUNT(*) FROM sesion_items si JOIN sesiones se ON se.id = si.sesion_id
                         WHERE si.item_id = i.id AND se.estado != 'cancelada') AS veces,
                       (SELECT MAX(se.fecha) FROM sesion_items si JOIN sesiones se ON se.id = si.sesion_id
                         WHERE si.item_id = i.id AND se.estado != 'cancelada') AS ultima
                FROM items i JOIN competencias c ON c.id = i.competencia_id
                JOIN subareas s ON s.id = c.subarea_id JOIN areas a ON a.id = s.area_id
                WHERE a.aci_id = ? {filtro}
                ORDER BY a.orden, s.orden, c.orden, i.orden""",
            params,
        )
        pendientes = []
        for pos, f in enumerate(filas):
            f["evaluacion"] = evaluacion_actual(f, aci["trimestre"])
            f["posicion"] = pos
            if f["evaluacion"] != "C" and f["texto"].strip():
                pendientes.append(f)
        return pendientes

    @staticmethod
    def elegir(pendientes: list[dict], n: int) -> list[dict]:
        orden = sorted(
            pendientes,
            key=lambda f: (f["veces"], f["ultima"] or "", RANGO_LOGRO.get(f["evaluacion"], 0), f["posicion"]),
        )
        elegidos: list[dict] = []
        comps_usadas: set[int] = set()
        # Primera pasada: una por competencia
        for f in orden:
            if len(elegidos) >= n:
                break
            if f["comp_id"] not in comps_usadas:
                elegidos.append(f)
                comps_usadas.add(f["comp_id"])
        for f in orden:
            if len(elegidos) >= n:
                break
            if f not in elegidos:
                elegidos.append(f)
        return elegidos

    # ------------------------------------------------------------ planificación
    def planificar(self, desde: str, hasta: str, replanificar: bool = False,
                   usuario_id: int | None = None) -> dict:
        """Crea sesiones entre dos fechas (incluidas) y les asigna ítems pendientes.
        Las sesiones ya realizadas o canceladas no se tocan. Las planificadas
        solo se rehacen si `replanificar` es True."""
        d0, d1 = _fecha(desde), _fecha(hasta)
        if d1 < d0:
            raise StoreError("La fecha final es anterior a la inicial")
        if (d1 - d0).days > 120:
            raise StoreError("Planifica como máximo 4 meses de una vez")
        franjas = [f for f in self.listar_franjas(usuario_id) if f["tipo"] == "sesion"]
        res = {"sesiones": 0, "items": 0, "sin_pendientes": []}
        d = d0
        while d <= d1:
            if d.weekday() < 5:
                for f in franjas:
                    if f["dia"] != d.weekday():
                        continue
                    for al in f["alumnos"]:
                        self._planificar_sesion(f, al, d.isoformat(), replanificar, res)
            d += dt.timedelta(days=1)
        res["sin_pendientes"] = sorted(set(res["sin_pendientes"]))
        return res

    def _planificar_sesion(self, franja: dict, alumno: dict, fecha: str, replanificar: bool, res: dict):
        existente = self.s.q1(
            "SELECT * FROM sesiones WHERE franja_id = ? AND alumno_id = ? AND fecha = ?",
            (franja["id"], alumno["id"], fecha),
        )
        if existente:
            if existente["estado"] != "planificada" or not replanificar:
                return
            with self.s.tx() as c:
                c.execute("DELETE FROM sesion_items WHERE sesion_id = ?", (existente["id"],))
        pendientes = self.items_pendientes(alumno["id"], franja["especialidad"])
        elegidos = self.elegir(pendientes, franja["items_por_sesion"])
        if not elegidos:
            res["sin_pendientes"].append(alumno["nombre"])
        with self.s.tx() as c:
            if existente:
                sesion_id = existente["id"]
            else:
                sesion_id = c.execute(
                    "INSERT INTO sesiones(franja_id, alumno_id, fecha) VALUES (?,?,?)",
                    (franja["id"], alumno["id"], fecha),
                ).lastrowid
                res["sesiones"] += 1
            for it in elegidos:
                c.execute("INSERT OR IGNORE INTO sesion_items(sesion_id, item_id) VALUES (?, ?)",
                          (sesion_id, it["id"]))
                res["items"] += 1

    # ------------------------------------------------------------ agenda
    def agenda(self, desde: str, hasta: str, usuario_id: int | None = None) -> list[dict]:
        filtro, params = "", [desde, hasta]
        if usuario_id is not None:
            filtro = "AND f.usuario_id = ?"
            params.append(usuario_id)
        sesiones = self.s.q(
            f"""SELECT se.*, f.inicio, f.fin, f.etiqueta, f.especialidad, f.dia,
                      al.nombre AS alumno, (SELECT MAX(id) FROM acis WHERE alumno_id = al.id) AS aci_id
               FROM sesiones se JOIN franjas f ON f.id = se.franja_id
               JOIN alumnos al ON al.id = se.alumno_id
               WHERE se.fecha BETWEEN ? AND ? {filtro} ORDER BY se.fecha, f.inicio, al.nombre""",
            params,
        )
        if not sesiones:
            return []
        ids = [s["id"] for s in sesiones]
        marcas = ",".join("?" * len(ids))
        items = self.s.q(
            f"""SELECT si.sesion_id, si.trabajado, i.id, i.texto, i.eval_1t, i.eval_2t, i.eval_3t,
                       c.nombre AS competencia, s.nombre AS subarea, a.nombre AS area, acis.trimestre
                FROM sesion_items si JOIN items i ON i.id = si.item_id
                JOIN competencias c ON c.id = i.competencia_id JOIN subareas s ON s.id = c.subarea_id
                JOIN areas a ON a.id = s.area_id JOIN acis ON acis.id = a.aci_id
                WHERE si.sesion_id IN ({marcas})
                ORDER BY a.orden, s.orden, c.orden, i.orden""",
            ids,
        )
        por_sesion: dict[int, list] = {}
        for it in items:
            it["evaluacion"] = evaluacion_actual(it, it["trimestre"])
            por_sesion.setdefault(it["sesion_id"], []).append(it)
        for s in sesiones:
            s["items"] = por_sesion.get(s["id"], [])
        return sesiones

    def actualizar_sesion(self, sesion_id: int, datos: dict) -> None:
        with self.s.tx() as c:
            if "estado" in datos:
                if datos["estado"] not in ("planificada", "realizada", "cancelada"):
                    raise StoreError("Estado no válido")
                c.execute("UPDATE sesiones SET estado = ? WHERE id = ?", (datos["estado"], sesion_id))
            if "notas" in datos:
                c.execute("UPDATE sesiones SET notas = ? WHERE id = ?", (datos["notas"], sesion_id))

    def marcar_item(self, sesion_id: int, item_id: int, trabajado: bool | None = None,
                    evaluacion: str | None = None) -> None:
        with self.s.tx() as c:
            if trabajado is not None:
                c.execute("UPDATE sesion_items SET trabajado = ? WHERE sesion_id = ? AND item_id = ?",
                          (int(bool(trabajado)), sesion_id, item_id))
            if evaluacion is not None:
                if evaluacion not in ("", *ESCALA):
                    raise StoreError("Evaluación no válida")
                tri = c.execute(
                    """SELECT acis.trimestre FROM items i JOIN competencias c ON c.id = i.competencia_id
                       JOIN subareas s ON s.id = c.subarea_id JOIN areas a ON a.id = s.area_id
                       JOIN acis ON acis.id = a.aci_id WHERE i.id = ?""", (item_id,)).fetchone()
                if tri:
                    c.execute(f"UPDATE items SET eval_{tri[0]}t = ? WHERE id = ?", (evaluacion, item_id))

    def quitar_item(self, sesion_id: int, item_id: int) -> None:
        with self.s.tx() as c:
            c.execute("DELETE FROM sesion_items WHERE sesion_id = ? AND item_id = ?", (sesion_id, item_id))

    def borrar_sesion(self, sesion_id: int) -> None:
        with self.s.tx() as c:
            c.execute("DELETE FROM sesiones WHERE id = ?", (sesion_id,))
