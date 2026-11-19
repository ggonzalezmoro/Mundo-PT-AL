"""Importar el horario semanal de un maestro desde una hoja de cálculo.

Formato esperado (el habitual en el colegio, exportado de Google Sheets o Excel):

            | LUNES   | MARTES        | MIÉRCOLES    | JUEVES | VIERNES
 9:00-10:00 | LUIS    | MARIO         | LUIS/ SOFÍA  | ...    | ...
 11.00-11.30| PATIO   | PATIO         | ...
 15:20-16:10| RAÚL Y SOFÍA   | LEO/MARIO?  | TIEMPO DE TRABAJO | ...

* La primera columna lleva la franja horaria («9:00-10:00» o «11.00-11.30»).
* Cada celda puede tener uno o varios alumnos separados por «/», «,» o «y».
  Un «?» marca la sesión como pendiente de confirmar.
* Celdas como PATIO, COMEDOR, TIEMPO DE TRABAJO, DEPARTAMENTO DE ORIENTACIÓN o
  PRUEBAS DE LENGUAJE se guardan como «otra tarea» (no se planifican ítems en ellas).
* «MARIO.L» se entiende como un alumno llamado Mario cuyo apellido empieza por L.

Al actualizar el horario (`reemplazar`), las franjas que siguen igual conservan su
historia, y las que desaparecen se archivan si tienen sesiones pasadas: las notas,
la asistencia y las observaciones de la agenda nunca se pierden.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from .store import Store, StoreError, normalizar

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4}

PALABRAS_NO_ALUMNO = (
    "patio", "recreo", "comedor", "tiempo de trabajo", "departamento", "orientacion",
    "reunion", "coordinacion", "guardia", "exclusiva", "claustro", "tutoria", "libre",
    "evaluacion", "preparacion", "biblioteca", "prueba", "valoracion",
)

_HORA = re.compile(r"(\d{1,2})[:.,h](\d{2})\s*[-–a]\s*(\d{1,2})[:.,h](\d{2})")


def leer_tabla(nombre: str, datos: bytes) -> list[list[str]]:
    """Devuelve las filas de un .xlsx o .csv como listas de texto.
    En Excel, las celdas combinadas se rellenan con su valor."""
    ext = Path(nombre or "").suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(datos), data_only=True)
        ws = wb.worksheets[0]
        valores = {}
        for rango in ws.merged_cells.ranges:
            v = ws.cell(rango.min_row, rango.min_col).value
            for r in range(rango.min_row, rango.max_row + 1):
                for c in range(rango.min_col, rango.max_col + 1):
                    valores[(r, c)] = v
        filas = []
        for r in range(1, ws.max_row + 1):
            fila = []
            for c in range(1, ws.max_column + 1):
                v = valores.get((r, c), ws.cell(r, c).value)
                fila.append("" if v is None else str(v).strip())
            filas.append(fila)
        return filas
    if ext in (".csv", ".txt", ""):
        texto = datos.decode("utf-8-sig", errors="replace")
        dialecto = csv.Sniffer().sniff(texto[:2000], delimiters=",;\t") if texto.strip() else csv.excel
        return [[c.strip() for c in fila] for fila in csv.reader(io.StringIO(texto), dialecto)]
    raise StoreError("Formato no admitido: usa un archivo .xlsx o .csv")


def _nombre_propio(texto: str) -> str:
    palabras = texto.strip().split()
    return " ".join(p[:1].upper() + p[1:].lower() for p in palabras)


def _hora(h: str, m: str) -> str:
    return f"{int(h):02d}:{m}"


def analizar_tabla(filas: list[list[str]]) -> list[dict]:
    """Convierte la tabla en franjas: {dia, inicio, fin, tipo, etiqueta, alumnos}."""
    cab_idx, columnas = None, {}
    for i, fila in enumerate(filas):
        cols = {j: DIAS[normalizar(c)] for j, c in enumerate(fila) if normalizar(c) in DIAS}
        if len(cols) >= 3:
            cab_idx, columnas = i, cols
            break
    if cab_idx is None:
        raise StoreError("No encuentro la fila con los días (LUNES, MARTES, …) en el horario")

    franjas: list[dict] = []
    for fila in filas[cab_idx + 1:]:
        m = next((_HORA.search(c) for c in fila if _HORA.search(c or "")), None)
        if not m:
            continue  # filas sin hora (p. ej. COMEDOR sin franja indicada)
        inicio, fin = _hora(m.group(1), m.group(2)), _hora(m.group(3), m.group(4))
        if fin <= inicio:
            continue
        for j, dia in columnas.items():
            celda = (fila[j] if j < len(fila) else "").strip()
            if not celda:
                continue
            n = normalizar(celda)
            if any(p in n for p in PALABRAS_NO_ALUMNO):
                franjas.append({"dia": dia, "inicio": inicio, "fin": fin, "tipo": "otro",
                                "etiqueta": celda[:1].upper() + celda[1:].lower(), "alumnos": []})
                continue
            dudosa = "?" in celda
            partes = re.split(r"\s*/\s*|\s*,\s*|\s+y\s+|\s+e\s+", celda.replace("?", ""), flags=re.I)
            alumnos = [_nombre_propio(p) for p in partes if p.strip()]
            franjas.append({
                "dia": dia, "inicio": inicio, "fin": fin, "tipo": "sesion",
                "etiqueta": "Pendiente de confirmar" if dudosa else "",
                "alumnos": alumnos,
            })
    if not franjas:
        raise StoreError("No he encontrado franjas con horas (formato 9:00-10:00) en el horario")
    return franjas


# ----------------------------------------------------------------------- alumnos de la hoja
def nombres_del_horario(franjas: list[dict]) -> list[str]:
    """Nombres distintos que aparecen en las sesiones, en orden de aparición."""
    vistos: dict[str, str] = {}
    for f in franjas:
        for n in f["alumnos"]:
            vistos.setdefault(normalizar(n), n)
    return list(vistos.values())


def _palabras(texto: str) -> list[str]:
    return [p for p in re.split(r"[.\s]+", normalizar(texto)) if p]


def candidatos(nombre: str, alumnos: list[dict]) -> list[dict]:
    """Alumnos del perfil que pueden ser el «nombre» escrito en el horario.
    Admite el nombre completo, solo el nombre de pila («MARIO» → Mario P. G.)
    y la inicial del apellido («MARIO.L» → Mario L…)."""
    partes = _palabras(nombre)
    if not partes:
        return []
    exactos = [a for a in alumnos if _palabras(a["nombre"]) == partes]
    if exactos:
        return exactos
    res = []
    for a in alumnos:
        pa = _palabras(a["nombre"])
        if pa[:len(partes)] == partes:
            res.append(a)
        elif len(partes) >= 2 and len(partes[-1]) <= 2 and pa[:len(partes) - 1] == partes[:-1] \
                and any(w.startswith(partes[-1]) for w in pa[len(partes) - 1:]):
            res.append(a)
    return res


def proponer_alumnos(store: Store, plan, usuario_id: int, franjas: list[dict]) -> list[dict]:
    """Para cada nombre del horario propone el alumno de la app (o crear uno nuevo).
    Si hay varios posibles, se elige el que más sesiones tiene en el horario actual."""
    alumnos = store.listar_alumnos(usuario_id, incluir_inactivos=True)
    usos: dict[int, int] = {}
    for f in plan.listar_franjas(usuario_id):
        for a in f["alumnos"]:
            usos[a["id"]] = usos.get(a["id"], 0) + 1
    propuestas = []
    for nombre in nombres_del_horario(franjas):
        cands = candidatos(nombre, alumnos)
        cands.sort(key=lambda a: (-usos.get(a["id"], 0), not a["activo"], a["nombre"]))
        propuestas.append({
            "texto": nombre,
            "alumno_id": cands[0]["id"] if cands else None,
            "candidatos": [{"id": a["id"], "nombre": a["nombre"]} for a in cands],
            "dudoso": len(cands) > 1,
            "sesiones": sum(1 for f in franjas if nombre in f["alumnos"]),
        })
    return propuestas


def _clave(f: dict) -> tuple:
    return (int(f["dia"]), f["inicio"], f["fin"])


def resumen_cambios(plan, usuario_id: int, franjas: list[dict], propuestas: list[dict]) -> dict:
    """Qué pasará al actualizar el horario: franjas nuevas, cambiadas, iguales y retiradas."""
    ids = {p["texto"]: p["alumno_id"] for p in propuestas}
    actuales = {_clave(f): f for f in plan.listar_franjas(usuario_id)}
    nuevas = cambiadas = iguales = 0
    for f in franjas:
        vieja = actuales.get(_clave(f))
        if not vieja:
            nuevas += 1
            continue
        mismos = sorted(a["id"] for a in vieja["alumnos"]) == sorted(ids.get(n) or -1 for n in f["alumnos"])
        if mismos and vieja["tipo"] == f["tipo"] and (f["tipo"] == "sesion" or vieja["etiqueta"] == f["etiqueta"]):
            iguales += 1
        else:
            cambiadas += 1
    claves = {_clave(f) for f in franjas}
    return {"nuevas": nuevas, "cambiadas": cambiadas, "iguales": iguales,
            "retiradas": sum(1 for k in actuales if k not in claves)}


def importar_horario(store: Store, plan, usuario_id: int, franjas: list[dict],
                     reemplazar: bool = False, asignacion: dict | None = None,
                     en_valoracion: list[str] | tuple = ()) -> dict:
    """Guarda las franjas en el horario del usuario creando los alumnos que falten.

    * `asignacion`: {nombre del horario: id de alumno | "nuevo"}; lo que falte se decide solo.
    * `en_valoracion`: nombres que, si se crean, son alumnos en valoración (sin ACI).
    * Con `reemplazar` se actualiza el horario actual: las franjas a la misma hora se
      modifican (conservando sus sesiones), las que no están en el archivo se retiran
      (se archivan si tienen sesiones pasadas) y se añaden las nuevas."""
    res = {"franjas": 0, "nuevas": 0, "actualizadas": 0, "retiradas": 0, "alumnos_nuevos": [], "omitidas": []}
    asignacion = {normalizar(k): v for k, v in (asignacion or {}).items()}
    valoracion = {normalizar(n) for n in en_valoracion}
    propios = {a["id"] for a in store.listar_alumnos(usuario_id, incluir_inactivos=True)}
    auto = {normalizar(p["texto"]): p["alumno_id"] for p in proponer_alumnos(store, plan, usuario_id, franjas)}
    resueltos: dict[str, int] = {}

    def alumno_de(nombre: str) -> int:
        k = normalizar(nombre)
        if k in resueltos:
            return resueltos[k]
        elegido = asignacion.get(k, auto.get(k))
        if elegido not in (None, "", "nuevo"):
            elegido = int(elegido)
            if elegido not in propios:
                raise StoreError(f"El alumno elegido para «{nombre}» no es de tu perfil")
        else:
            elegido = store.crear_alumno(nombre, usuario_id=usuario_id,
                                         seguimiento="observacion" if k in valoracion else "aci")
            propios.add(elegido)
            res["alumnos_nuevos"].append(nombre)
        resueltos[k] = elegido
        return elegido

    con_ids = [{**f, "alumnos": list(dict.fromkeys(alumno_de(n) for n in f["alumnos"]))} for f in franjas]

    pendientes = con_ids
    if reemplazar:
        actuales = {_clave(f): f for f in plan.listar_franjas(usuario_id)}
        claves = {_clave(f) for f in con_ids}
        for k, vieja in actuales.items():
            if k not in claves:
                plan.borrar_franja(vieja["id"])
                res["retiradas"] += 1
        pendientes = []
        for f in con_ids:
            vieja = actuales.get(_clave(f))
            if not vieja:
                pendientes.append(f)
                continue
            etiqueta = f["etiqueta"]
            if not etiqueta and f["tipo"] == vieja["tipo"] and vieja["etiqueta"] != "Pendiente de confirmar":
                etiqueta = vieja["etiqueta"]  # se respeta la descripción que puso la maestra
            datos = {**f, "etiqueta": etiqueta, "especialidad": vieja["especialidad"],
                     "items_por_sesion": vieja["items_por_sesion"]}
            try:
                plan.guardar_franja(datos, vieja["id"], usuario_id=usuario_id)
                plan.quitar_alumnos_futuros(vieja["id"], f["alumnos"])
                res["franjas"] += 1
                res["actualizadas"] += 1
            except StoreError as e:
                res["omitidas"].append(f"{f['inicio']}-{f['fin']} ({e})")
    for f in pendientes:
        try:
            plan.guardar_franja(f, usuario_id=usuario_id)
            res["franjas"] += 1
            res["nuevas"] += 1
        except StoreError as e:
            res["omitidas"].append(f"{f['inicio']}-{f['fin']} ({e})")
    res["alumnos_nuevos"] = sorted(set(res["alumnos_nuevos"]))
    return res
