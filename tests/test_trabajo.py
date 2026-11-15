import datetime as dt
import sqlite3

from mundoptal import db, trabajo
from mundoptal.servidor import crear_app
from mundoptal.store import Store


def _cliente(tmp_path):
    app = crear_app(tmp_path / "t.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra Prueba", "especialidad": "PT/AL"}).get_json()["id"]
    return c, {"X-Usuario": str(uid)}


def test_tareas_crear_marcar_y_borrar(tmp_path):
    c, h = _cliente(tmp_path)
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba"}, headers=h).get_json()["id"]
    t1 = c.post("/api/tareas", json={"texto": "Preparar pictogramas de rutinas", "categoria": "material"}, headers=h).get_json()["id"]
    t2 = c.post("/api/tareas", json={"texto": "Pasar prueba de lenguaje", "categoria": "prueba", "alumno_id": al,
                                     "fecha_limite": "2026-11-20"}, headers=h).get_json()["id"]
    assert c.post("/api/tareas", json={"texto": "  "}, headers=h).status_code == 400
    assert c.post("/api/tareas", json={"texto": "x", "categoria": "inventada"}, headers=h).status_code == 400
    lista = c.get("/api/tareas", headers=h).get_json()
    assert [t["id"] for t in lista] == [t2, t1]  # primero la que tiene fecha límite
    assert lista[0]["alumno"] == "Alumna Prueba"

    assert c.patch(f"/api/tareas/{t1}", json={"hecha": True}, headers=h).status_code == 200
    hecha = next(t for t in c.get("/api/tareas", headers=h).get_json() if t["id"] == t1)
    assert hecha["hecha"] == 1 and hecha["hecha_en"]
    c.patch(f"/api/tareas/{t1}", json={"hecha": False}, headers=h)
    assert next(t for t in c.get("/api/tareas", headers=h).get_json() if t["id"] == t1)["hecha_en"] is None

    c.patch(f"/api/tareas/{t1}", json={"hecha": True}, headers=h)
    assert c.post("/api/tareas/borrar-hechas", headers=h).get_json()["borradas"] == 1
    assert [t["id"] for t in c.get("/api/tareas", headers=h).get_json()] == [t2]
    # Cada perfil ve solo sus tareas
    otro = c.post("/api/usuarios", json={"nombre": "Otra", "especialidad": "PT"}).get_json()["id"]
    assert c.get("/api/tareas", headers={"X-Usuario": str(otro)}).get_json() == []


def test_citas_en_el_calendario_mensual_y_ficha(tmp_path):
    c, h = _cliente(tmp_path)
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba"}, headers=h).get_json()["id"]
    cid = c.post("/api/citas", json={"fecha": "2026-11-18", "hora_inicio": "16:00", "hora_fin": "16:30",
                                     "tipo": "tutoria_familia", "alumno_id": al, "con_quien": "Familia"}, headers=h).get_json()["id"]
    c.post("/api/citas", json={"fecha": "2026-12-02", "hora_inicio": "13:00", "tipo": "reunion_terapeutas",
                               "con_quien": "Logopeda del centro externo"}, headers=h)
    assert c.post("/api/citas", json={"fecha": "2026-13-01"}, headers=h).status_code == 400
    assert c.post("/api/citas", json={"fecha": "2026-11-18", "hora_inicio": "25:00"}, headers=h).status_code == 400

    nov = c.get("/api/citas?mes=2026-11", headers=h).get_json()
    # El calendario va de lunes a domingo: noviembre 2026 empieza en domingo
    assert nov["desde"] == "2026-10-26" and nov["hasta"] == "2026-12-06"
    assert [x["id"] for x in nov["citas"]][0] == cid and len(nov["citas"]) == 2
    assert nov["citas"][0]["alumno"] == "Alumna Prueba"
    assert c.patch(f"/api/citas/{cid}", json={"lugar": "Aula PT", "hora_inicio": "17:00"}, headers=h).status_code == 200
    ficha = c.get(f"/api/alumnos/{al}", headers=h).get_json()
    assert ficha["citas"][0]["lugar"] == "Aula PT" and ficha["citas"][0]["hora_inicio"] == "17:00"
    assert c.delete(f"/api/citas/{cid}", headers=h).status_code == 200
    assert len(c.get("/api/citas?mes=2026-11", headers=h).get_json()["citas"]) == 1


def test_avisos_de_hoy_y_tareas_vencidas(tmp_path):
    s = Store(tmp_path / "a.db")
    uid = s.crear_usuario("Maestra Prueba", "AL")
    hoy = dt.date(2026, 11, 16)
    trabajo.crear_cita(s, uid, {"fecha": "2026-11-16", "hora_inicio": "09:00", "tipo": "tutoria_familia"})
    trabajo.crear_cita(s, uid, {"fecha": "2026-11-17", "tipo": "reunion_terapeutas"})
    trabajo.crear_cita(s, uid, {"fecha": "2026-11-19", "tipo": "otra"})
    trabajo.crear_tarea(s, uid, {"texto": "Enviar correo", "categoria": "correos", "fecha_limite": "2026-11-10"})
    trabajo.crear_tarea(s, uid, {"texto": "Material", "fecha_limite": "2026-11-30"})
    av = trabajo.avisos(s, uid, hoy)
    assert [x["fecha"] for x in av["citas"]] == ["2026-11-16", "2026-11-17"]
    assert [t["texto"] for t in av["tareas_vencidas"]] == ["Enviar correo"]


def test_migracion_desde_esquema_7(tmp_path):
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO meta VALUES ('schema_version', '7');
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY, nombre TEXT, especialidad TEXT, creado TEXT);
        INSERT INTO usuarios(id, nombre, especialidad) VALUES (1, 'Maestra Prueba', 'PT/AL');
    """)
    con.commit()
    con.close()
    conn = db.connect(ruta)
    tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"tareas", "citas"} <= tablas
    assert conn.execute("SELECT nombre FROM usuarios WHERE id = 1").fetchone()[0] == "Maestra Prueba"
    assert conn.execute("SELECT valor FROM meta WHERE clave = 'schema_version'").fetchone()[0] == str(db.SCHEMA_VERSION)


def test_rango_mes():
    assert trabajo.rango_mes("2026-02") == ("2026-01-26", "2026-03-01")
    assert trabajo.rango_mes("2026-12") == ("2026-11-30", "2027-01-03")
