"""Importar el horario semanal de un maestro desde una hoja de cálculo.

Formato esperado (el habitual en el colegio, exportado de Google Sheets o Excel):

            | LUNES   | MARTES        | MIÉRCOLES    | JUEVES | VIERNES
 9:00-10:00 | LUIS    | MARIO         | LUIS/ SOFÍA  | ...    | ...
 11.00-11.30| PATIO   | PATIO         | ...
 15:20-16:10| RAÚL Y SOFÍA   | LEO/MARIO?  | TIEMPO DE TRABAJO | ...

* La primera columna lleva la franja horaria («9:00-10:00» o «11.00-11.30»).
* Cada celda puede tener uno o varios alumnos separados por «/», «,» o «y».
  Un «?» marca la sesión como pendiente de confirmar.
* Celdas como PATIO, COMEDOR, TIEMPO DE TRABAJO o DEPARTAMENTO DE ORIENTACIÓN
  se guardan como «otra tarea» (no se planifican ítems en ellas).
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
    "evaluacion", "preparacion", "biblioteca",
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


def importar_horario(store: Store, plan, usuario_id: int, franjas: list[dict],
                     reemplazar: bool = False) -> dict:
    """Guarda las franjas en el horario del usuario creando los alumnos que falten.
    Con `reemplazar` se borra antes su horario actual (y las sesiones asociadas)."""
    res = {"franjas": 0, "alumnos_nuevos": [], "omitidas": []}
    if reemplazar:
        with store.tx() as c:
            c.execute("DELETE FROM franjas WHERE usuario_id = ?", (usuario_id,))
    for f in franjas:
        ids = []
        for nombre in f["alumnos"]:
            al = store.buscar_alumno(nombre, usuario_id)
            if al:
                ids.append(al["id"])
            else:
                ids.append(store.crear_alumno(nombre, usuario_id=usuario_id))
                res["alumnos_nuevos"].append(nombre)
        try:
            plan.guardar_franja({**f, "alumnos": ids}, usuario_id=usuario_id)
            res["franjas"] += 1
        except StoreError as e:
            res["omitidas"].append(f"{f['inicio']}-{f['fin']} ({e})")
    res["alumnos_nuevos"] = sorted(set(res["alumnos_nuevos"]))
    return res
