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


def test_datos_por_dia_y_por_semana(tmp_path):
    c, h = _cliente(tmp_path)
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba"}, headers=h).get_json()["id"]
    for fecha, hora in (("2026-11-16", "16:00"), ("2026-11-16", "09:30"), ("2026-11-18", ""), ("2026-11-23", "10:00")):
        c.post("/api/citas", json={"fecha": fecha, "hora_inicio": hora, "tipo": "otra"}, headers=h)
    # Día: solo ese día, ordenado por hora (las citas sin hora, al principio)
    dia = c.get("/api/citas?desde=2026-11-16&hasta=2026-11-16", headers=h).get_json()["citas"]
    assert [x["hora_inicio"] for x in dia] == ["09:30", "16:00"]
    # Semana de lunes a domingo
    semana = c.get("/api/citas?desde=2026-11-16&hasta=2026-11-22", headers=h).get_json()["citas"]
    assert [x["fecha"] for x in semana] == ["2026-11-16", "2026-11-16", "2026-11-18"]
    # La agenda de sesiones también se pide por un solo día
    c.post("/api/franjas", json={"dia": 0, "inicio": "09:00", "fin": "09:30", "alumnos": [al]}, headers=h)
    c.post("/api/franjas", json={"dia": 2, "inicio": "11:00", "fin": "11:30", "alumnos": [al]}, headers=h)
    c.post("/api/planificar", json={"desde": "2026-11-16", "hasta": "2026-11-20"}, headers=h)
    ag = c.get("/api/agenda?desde=2026-11-18&hasta=2026-11-18", headers=h).get_json()["sesiones"]
    assert [(s["fecha"], s["inicio"]) for s in ag] == [("2026-11-18", "11:00")]


def test_rango_mes():
    assert trabajo.rango_mes("2026-02") == ("2026-01-26", "2026-03-01")
    assert trabajo.rango_mes("2026-12") == ("2026-11-30", "2027-01-03")


def test_reunion_con_notas_y_lineas_a_tareas(tmp_path):
    c, h = _cliente(tmp_path)
    al = c.post("/api/alumnos", json={"nombre": "Alumno Prueba"}, headers=h).get_json()["id"]
    rid = c.post("/api/citas", json={"fecha": "2026-11-17", "hora_inicio": "13:00", "tipo": "reunion_orientacion",
                                     "alumno_id": al, "con_quien": "Orientadora"}, headers=h).get_json()["id"]
    otra = c.post("/api/citas", json={"fecha": "2026-11-18", "tipo": "tutoria_familia"}, headers=h).get_json()["id"]
    c.post("/api/citas", json={"fecha": "2026-11-19", "tipo": "reunion_profesores"}, headers=h)
    notas = "Revisar el ACI\n- Pedir informe a la logopeda\n2. Preparar pictogramas"
    assert c.patch(f"/api/citas/{rid}", json={"notas": notas}, headers=h).status_code == 200
    # Cada línea pasa a tarea sin la viñeta, con el alumno y la categoría de la reunión
    t1 = c.post(f"/api/reuniones/{rid}/tareas", json={"texto": "- Pedir informe a la logopeda"}, headers=h).get_json()["id"]
    c.post(f"/api/reuniones/{rid}/tareas", json={"texto": "2. Preparar pictogramas", "fecha_limite": "2026-11-20"}, headers=h)
    c.post(f"/api/reuniones/{otra}/tareas", json={"texto": "☐ Enviar correo a la familia"}, headers=h)
    assert c.post(f"/api/reuniones/{rid}/tareas", json={"texto": " - "}, headers=h).status_code == 400
    r = c.get(f"/api/reuniones/{rid}", headers=h).get_json()
    assert r["notas"] == notas and r["alumno"] == "Alumno Prueba"
    assert [t["texto"] for t in r["tareas"]] == ["Pedir informe a la logopeda", "Preparar pictogramas"]
    assert {t["categoria"] for t in r["tareas"]} == {"reunion"} and {t["alumno_id"] for t in r["tareas"]} == {al}
    tareas = c.get("/api/tareas", headers=h).get_json()
    fam = next(t for t in tareas if t["cita_id"] == otra)
    assert fam["texto"] == "Enviar correo a la familia" and fam["categoria"] == "tutoria" and fam["cita_tipo"] == "tutoria_familia"
    # Lista de reuniones (más recientes primero), con recuento y filtros
    lista = c.get("/api/reuniones", headers=h).get_json()
    assert [x["fecha"] for x in lista] == ["2026-11-19", "2026-11-18", "2026-11-17"]
    assert next(x for x in lista if x["id"] == rid)["tareas_pendientes"] == 2
    c.patch(f"/api/tareas/{t1}", json={"hecha": True}, headers=h)
    orient = c.get("/api/reuniones?tipo=reunion_orientacion", headers=h).get_json()
    assert [(x["id"], x["tareas_total"], x["tareas_pendientes"]) for x in orient] == [(rid, 2, 1)]
    assert [x["id"] for x in c.get(f"/api/reuniones?alumno_id={al}", headers=h).get_json()] == [rid]
    # Otro perfil no ve la reunión ni puede colgarle tareas
    otro = {"X-Usuario": str(c.post("/api/usuarios", json={"nombre": "Otra"}).get_json()["id"])}
    assert c.get(f"/api/reuniones/{rid}", headers=otro).status_code == 400
    assert c.post(f"/api/reuniones/{rid}/tareas", json={"texto": "x"}, headers=otro).status_code == 400
    # Al borrar la reunión, sus tareas siguen pendientes
    c.delete(f"/api/citas/{rid}", headers=h)
    assert len(c.get("/api/tareas", headers=h).get_json()) == 3


def test_migracion_tareas_cita_id(tmp_path):
    ruta = tmp_path / "v12.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE tareas (id INTEGER PRIMARY KEY, usuario_id INTEGER, texto TEXT NOT NULL DEFAULT '',
            categoria TEXT NOT NULL DEFAULT 'otros', alumno_id INTEGER, fecha_limite TEXT, hecha INTEGER NOT NULL DEFAULT 0,
            hecha_en TEXT, orden INTEGER NOT NULL DEFAULT 0, creada TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO tareas(texto) VALUES ('Tarea antigua');
    """)
    con.close()
    conn = db.connect(ruta)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tareas)")}
    assert "cita_id" in cols
    assert conn.execute("SELECT texto, cita_id FROM tareas").fetchone()[:] == ("Tarea antigua", None)


def test_limpiar_linea():
    assert trabajo.limpiar_linea("  - Llamar a la familia ") == "Llamar a la familia"
    assert trabajo.limpiar_linea("• Revisar ACI") == "Revisar ACI"
    assert trabajo.limpiar_linea("[ ] Pedir cita") == "Pedir cita"
    assert trabajo.limpiar_linea("12) Preparar") == "Preparar"
    assert trabajo.limpiar_linea("2026 objetivos") == "2026 objetivos"
