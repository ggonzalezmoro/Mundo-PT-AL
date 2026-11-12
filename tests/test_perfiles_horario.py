import io
import sqlite3

import pytest
from openpyxl import Workbook

from mundoptal import horario
from mundoptal.planificador import Planificador
from mundoptal.servidor import crear_app
from mundoptal.store import Store, StoreError

# Tabla con el mismo formato que el horario del colegio (nombres inventados)
TABLA = [
    ["HORARIO PRUEBA PT/AL", "", "", "", "", ""],
    ["", "LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES"],
    ["9:00-10:00", "ANA", "LUIS", "ANA/ PEPE", "ANA/PEPE", "MARIO"],
    ["10:00-11:00", "MARIO", "MARIO", "LEO/MARIO?", "MARIO", "LUIS"],
    ["11.00-11.30", "PATIO", "PATIO", "PATIO", "PATIO", "PATIO"],
    ["11:30-12:15", "PEPE", "TIEMPO DE TRABAJO", "MARIO", "LUIS", "DEPARTAMENTO ORIENTACIÓN"],
    ["", "COMEDOR", "COMEDOR", "COMEDOR", "COMEDOR", "COMEDOR"],
    ["15:20-16:10", "RAÚL Y SOFÍA", "LEO/MARIO?", "TIEMPO DE TRABAJO", "RAÚL Y SOFÍA", "RAÚL"],
]


def test_analizar_tabla():
    franjas = horario.analizar_tabla(TABLA)
    lunes_9 = next(f for f in franjas if f["dia"] == 0 and f["inicio"] == "09:00")
    assert lunes_9 == {"dia": 0, "inicio": "09:00", "fin": "10:00", "tipo": "sesion", "etiqueta": "", "alumnos": ["Ana"]}
    mie_9 = next(f for f in franjas if f["dia"] == 2 and f["inicio"] == "09:00")
    assert mie_9["alumnos"] == ["Ana", "Pepe"]
    dudosa = next(f for f in franjas if f["dia"] == 2 and f["inicio"] == "10:00")
    assert dudosa["alumnos"] == ["Leo", "Mario"] and dudosa["etiqueta"] == "Pendiente de confirmar"
    patio = next(f for f in franjas if f["dia"] == 0 and f["inicio"] == "11:00")
    assert patio["tipo"] == "otro" and patio["fin"] == "11:30"
    assert next(f for f in franjas if f["dia"] == 0 and f["inicio"] == "15:20")["alumnos"] == ["Raúl", "Sofía"]
    assert all(f["inicio"] != "" for f in franjas)  # la fila de COMEDOR sin hora se ignora
    assert len(franjas) == 25


def test_leer_xlsx_con_celdas_combinadas():
    wb = Workbook()
    ws = wb.active
    for fila in TABLA:
        ws.append(fila)
    ws["C5"] = ws["D5"] = ws["E5"] = ws["F5"] = None
    ws.merge_cells("B5:F5")  # PATIO combinado
    buf = io.BytesIO()
    wb.save(buf)
    filas = horario.leer_tabla("horario.xlsx", buf.getvalue())
    assert filas[4][1:6] == ["PATIO"] * 5
    csv_bytes = "\n".join(";".join(f) for f in TABLA).encode("utf-8")
    assert horario.leer_tabla("h.csv", csv_bytes)[2][3] == "ANA/ PEPE"


def test_importar_horario_crea_alumnos_y_reutiliza(tmp_path):
    s = Store(tmp_path / "h.db")
    plan = Planificador(s)
    uid = s.crear_usuario("Profe", "PT/AL")
    ana = s.crear_alumno("Ana", usuario_id=uid)
    r = horario.importar_horario(s, plan, uid, horario.analizar_tabla(TABLA))
    assert r["franjas"] == 25 and r["omitidas"] == []
    assert "Ana" not in r["alumnos_nuevos"] and "Mario" in r["alumnos_nuevos"]
    assert s.buscar_alumno("ana", uid)["id"] == ana
    # Repetir sin reemplazar: todo se solapa y se omite
    assert horario.importar_horario(s, plan, uid, horario.analizar_tabla(TABLA))["franjas"] == 0
    assert horario.importar_horario(s, plan, uid, horario.analizar_tabla(TABLA), reemplazar=True)["franjas"] == 25


def test_perfiles_separan_datos(tmp_path):
    app = crear_app(tmp_path / "p.db")
    c = app.test_client()
    # Sin perfiles todo funciona como antes
    c.post("/api/alumnos", json={"nombre": "Previo"})
    f1 = c.post("/api/usuarios", json={"nombre": "Fátima", "especialidad": "PT/AL"}).get_json()["id"]
    assert c.post("/api/usuarios", json={"nombre": "X", "especialidad": "ZZ"}).status_code == 400
    # El primer perfil hereda los datos anteriores
    assert [a["nombre"] for a in c.get("/api/alumnos").get_json()] == ["Previo"]
    f2 = c.post("/api/usuarios", json={"nombre": "Otra", "especialidad": "AL"}).get_json()["id"]
    assert c.get("/api/alumnos").status_code == 400  # con dos perfiles hay que elegir
    h1, h2 = {"X-Usuario": str(f1)}, {"X-Usuario": str(f2)}
    c.post("/api/alumnos", json={"nombre": "De Otra"}, headers=h2)
    assert [a["nombre"] for a in c.get("/api/alumnos", headers=h1).get_json()] == ["Previo"]
    assert [a["nombre"] for a in c.get("/api/alumnos", headers=h2).get_json()] == ["De Otra"]
    # Cada perfil puede tener su franja a la misma hora
    datos = {"dia": 0, "inicio": "09:00", "fin": "10:00"}
    assert c.post("/api/franjas", json=datos, headers=h1).status_code == 200
    assert c.post("/api/franjas", json=datos, headers=h2).status_code == 200
    assert len(c.get("/api/franjas", headers=h1).get_json()) == 1
    # Importar horario por la API
    csv_bytes = "\n".join(",".join(f) for f in TABLA).encode("utf-8")
    r = c.post("/api/horario/importar", headers=h2, content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(csv_bytes), "horario.csv"), "reemplazar": "1"}).get_json()
    assert r["franjas"] == 25
    assert len(c.get("/api/franjas", headers=h1).get_json()) == 1
    assert c.patch(f"/api/usuarios/{f1}", json={"especialidad": "AL"}).status_code == 200


def test_migracion_desde_v1(tmp_path):
    ruta = tmp_path / "v1.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE alumnos (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, curso TEXT DEFAULT '',
            observaciones TEXT DEFAULT '', activo INTEGER NOT NULL DEFAULT 1, creado TEXT);
        INSERT INTO alumnos(nombre) VALUES ('Antiguo');
        CREATE TABLE franjas (id INTEGER PRIMARY KEY, dia INTEGER NOT NULL, inicio TEXT NOT NULL, fin TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'sesion', etiqueta TEXT DEFAULT '', especialidad TEXT NOT NULL DEFAULT 'PT/AL',
            items_por_sesion INTEGER NOT NULL DEFAULT 3);
    """)
    con.close()
    s = Store(ruta)
    uid = s.crear_usuario("Fátima")
    assert s.listar_alumnos(uid)[0]["nombre"] == "Antiguo"
    assert s.q1("SELECT valor FROM meta WHERE clave = 'schema_version'")["valor"] == "3"


def test_horario_sin_dias():
    with pytest.raises(StoreError):
        horario.analizar_tabla([["a", "b"], ["9:00-10:00", "x"]])
