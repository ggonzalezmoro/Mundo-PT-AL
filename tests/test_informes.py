import io

from docx import Document

from mundoptal import informes
from mundoptal.servidor import crear_app
from mundoptal.store import Store


def _aci_con_items(c, alumno_id, h):
    aci = c.post(f"/api/alumnos/{alumno_id}/acis", json={"trimestre": 1, "curso_escolar": "2026/27"}, headers=h).get_json()["id"]
    area = c.post(f"/api/areas/{aci}/hijos", json={"nombre": "Comunicación y representación"}, headers=h).get_json()["id"]
    sub = c.post(f"/api/subareas/{area}/hijos", json={"nombre": ""}, headers=h).get_json()["id"]
    comp = c.post(f"/api/competencias/{sub}/hijos", json={"nombre": "Atención"}, headers=h).get_json()["id"]
    for texto, ev in (("Mantiene la mirada en el objeto", "C"), ("Señala lo que quiere", "ED"),
                      ("Nombra colores básicos", "NI"), ("Sin evaluar", "")):
        c.post(f"/api/items/{comp}/hijos", json={"texto": texto, "eval_1t": ev}, headers=h)
    return aci


def test_informe_completo(tmp_path):
    app = crear_app(tmp_path / "i.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Fátima", "especialidad": "PT/AL"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    al = c.post("/api/alumnos", json={"nombre": "Ana López", "curso": "5 años"}, headers=h).get_json()["id"]
    aci = _aci_con_items(c, al, h)

    inf_id = c.post(f"/api/alumnos/{al}/informes", json={"trimestre": 1, "curso_escolar": "2026/27"}, headers=h).get_json()["id"]
    # Crear dos veces el mismo trimestre devuelve el mismo informe
    assert c.post(f"/api/alumnos/{al}/informes", json={"trimestre": 1, "curso_escolar": "2026/27"}, headers=h).get_json()["id"] == inf_id
    inf = c.get(f"/api/informes/{inf_id}", headers=h).get_json()
    assert inf["maestra"] == "Fátima" and inf["curso"] == "5 años"
    texto = inf["areas"][0]["texto"]
    assert inf["areas"][0]["area"] == "Comunicación y representación"
    assert texto.startswith("En el área de comunicación y representación, Ana ha conseguido y tiene dominado lo siguiente: mantiene la mirada en el objeto.")
    assert "todavía le queda bastante por trabajar: señala lo que quiere." in texto
    assert "Todavía no ha iniciado lo siguiente, por lo que es recomendable seguir trabajándolo: nombra colores básicos." in texto
    assert inf["despedida"] == "¡Os deseamos unas felices fiestas de Navidad!"
    assert "Ana" in inf["frases"]["social"][0]
    assert "sin evaluar" not in texto.lower()

    assert any("Infantil" in f for f in inf["frases"]["cierre"])
    assert "Lectoescritura" in inf["frases_ambitos"]
    assert "¡Os deseamos un muy feliz verano y un merecido descanso!" in inf["frases"]["despedida"]

    assert c.patch(f"/api/informes/{inf_id}", json={"social": "Juega con sus compañeros.", "actitud_al": "Viene contenta.",
                                                    "estrategias": "Le ayuda el temporizador."}, headers=h).status_code == 200
    assert c.patch(f"/api/informe_areas/{inf['areas'][0]['id']}", json={"texto": "Texto propio."}, headers=h).status_code == 200
    extra = c.post(f"/api/informes/{inf_id}/areas", json={"area": "Autonomía"}, headers=h).get_json()["id"]
    c.patch(f"/api/informe_areas/{extra}", json={"texto": "Se pone el abrigo sola."}, headers=h)

    r = c.get(f"/api/informes/{inf_id}/word", headers=h)
    assert r.status_code == 200
    doc = Document(io.BytesIO(r.data))
    todo = "\n".join(p.text for p in doc.paragraphs) + "\n".join(cell.text for t in doc.tables for row in t.rows for cell in row.cells)
    for esperado in ("OBSERVACIONES Y COMENTARIOS:", "NOMBRE: Ana López", "Juega con sus compañeros.", "Viene contenta.",
                     "Texto propio.", "Se pone el abrigo sola.", "felices fiestas de Navidad",
                     "PROF. AUDICIÓN Y LENGUAJE/PEDAGOGÍA TERAPÉUTICA", "Fátima"):
        assert esperado in todo, esperado
    assert "Autonomía" not in todo  # el título del área no sale: es prosa seguida
    textos = [p.text for p in doc.paragraphs]
    assert textos.index("Juega con sus compañeros.") < textos.index("Viene contenta.") < textos.index("Texto propio.")
    assert textos.index("Se pone el abrigo sola.") < textos.index("Le ayuda el temporizador.")

    # La ACI del mismo trimestre incluye el informe en «Observaciones y comentarios»
    aci_doc = Document(io.BytesIO(c.get(f"/api/acis/{aci}/word", headers=h).data))
    aci_txt = [p.text for p in aci_doc.paragraphs]
    assert "Juega con sus compañeros." in aci_txt and "¡Os deseamos unas felices fiestas de Navidad!" in aci_txt

    # Rehacer borrador sustituye las áreas
    assert c.post(f"/api/informes/{inf_id}/rehacer", headers=h).status_code == 200
    areas = c.get(f"/api/informes/{inf_id}", headers=h).get_json()["areas"]
    assert len(areas) == 1 and "mantiene la mirada" in areas[0]["texto"]

    resumen = c.get("/api/informes", headers=h).get_json()
    assert resumen["alumnos"][0]["informes"][0]["id"] == inf_id
    assert c.get(f"/api/alumnos/{al}", headers=h).get_json()["informes"][0]["trimestre"] == 1
    # Borrar el alumno borra sus informes
    c.delete(f"/api/alumnos/{al}", headers=h)
    assert c.get(f"/api/informes/{inf_id}", headers=h).status_code == 404


def test_sin_aci_y_fechas(tmp_path):
    s = Store(tmp_path / "x.db")
    al = s.crear_alumno("Leo")
    inf = informes.obtener(s, informes.crear(s, al, 2, "2026/27"))
    assert inf["areas"] == [] and inf["trimestre"] == 2
    from datetime import date
    assert informes.trimestre_actual(date(2026, 11, 12)) == 1
    assert informes.trimestre_actual(date(2027, 2, 1)) == 2
    assert informes.trimestre_actual(date(2027, 5, 1)) == 3
    assert informes.curso_escolar_actual(date(2026, 11, 12)) == "2026/27"
    assert informes.curso_escolar_actual(date(2027, 5, 1)) == "2026/27"


def test_migracion_anade_estrategias_a_informes(tmp_path):
    import sqlite3
    from mundoptal import db
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO meta VALUES ('schema_version', '4');
        CREATE TABLE informes(id INTEGER PRIMARY KEY, alumno_id INTEGER, social TEXT DEFAULT '');
        INSERT INTO informes(id, alumno_id, social) VALUES (1, 1, 'Texto previo');
    """)
    con.commit(); con.close()
    conn = db.connect(ruta)
    fila = conn.execute("SELECT social, estrategias FROM informes WHERE id = 1").fetchone()
    assert fila["social"] == "Texto previo" and fila["estrategias"] == ""


def test_borrador_desde_notas_de_la_agenda(tmp_path):
    app = crear_app(tmp_path / "n.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra", "especialidad": "AL"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba", "curso": "4 años"}, headers=h).get_json()["id"]
    _aci_con_items(c, al, h)
    c.post("/api/franjas", json={"dia": 0, "inicio": "09:00", "fin": "09:30", "alumnos": [al]}, headers=h)
    r = c.post("/api/planificar", json={"desde": "2026-10-05", "hasta": "2026-10-16"}, headers=h).get_json()
    assert r["sesiones"] == 2
    ses = c.get("/api/agenda?desde=2026-10-05&hasta=2026-10-16", headers=h).get_json()["sesiones"]
    c.patch(f"/api/sesiones/{ses[0]['id']}", json={"notas": "hoy vino contenta, se distrae x el ruido"}, headers=h)
    c.patch(f"/api/sesiones/{ses[1]['id']}", json={"notas": "mejor con el temporizador q la semana pasada"}, headers=h)
    item = ses[0]["items"][0]
    c.patch(f"/api/sesiones/{ses[0]['id']}/items/{item['id']}", json={"trabajado": True}, headers=h)

    inf = c.post(f"/api/alumnos/{al}/informes", json={"trimestre": 1, "curso_escolar": "2026/27"}, headers=h).get_json()["id"]
    d = c.get(f"/api/informes/{inf}/notas", headers=h).get_json()
    assert d["sesiones"] == 2 and len(d["notas"]) == 2
    assert d["items"] == [item["texto"]]
    b = d["borrador"]
    assert "trimestre, vino contenta, se distrae por el ruido." in b and "hoy" not in b.lower()
    assert "Mejor con el temporizador que la semana pasada." in b
    assert "hemos trabajado especialmente" in b
    # Otro trimestre no ve esas notas
    inf2 = c.post(f"/api/alumnos/{al}/informes", json={"trimestre": 2, "curso_escolar": "2026/27"}, headers=h).get_json()["id"]
    assert c.get(f"/api/informes/{inf2}/notas", headers=h).get_json()["notas"] == []


def test_pulir_nota():
    assert informes.pulir_nota("  he trabajado la atencion  , tb pinchitos ") == "Hemos trabajado la atencion, también pinchitos."
    assert informes.pulir_nota("") == ""
    assert informes.rango_trimestre(3, "2025/26") == ("2026-04-01", "2026-07-31")


def test_solo_lo_conseguido_se_redacta_como_logro():
    items = [{"texto": t, "eval_1t": e, "eval_2t": "", "eval_3t": ""}
             for t, e in [("Responde a su nombre", "ED+"), ("Muestra atención conjunta", "I")]]
    texto = informes.borrador_area({"nombre": "Lenguaje", "subareas": [{"competencias": [{"items": items}]}]}, 1, "Ana")
    assert "conseguido" not in texto.replace("muy cerca de conseguir", "")
    assert "muy cerca de conseguir lo siguiente, aunque todavía necesita generalizarlo a todos los contextos: responde a su nombre" in texto
    assert "que por ahora aparece solo de forma puntual: muestra atención conjunta" in texto


def test_registro_de_asistencia(tmp_path):
    app = crear_app(tmp_path / "a.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra", "especialidad": "PT"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba"}, headers=h).get_json()["id"]
    _aci_con_items(c, al, h)
    c.post("/api/franjas", json={"dia": 0, "inicio": "09:00", "fin": "09:30", "alumnos": [al]}, headers=h)
    c.post("/api/planificar", json={"desde": "2026-10-05", "hasta": "2026-10-23"}, headers=h)
    ses = c.get("/api/agenda?desde=2026-10-05&hasta=2026-10-23", headers=h).get_json()["sesiones"]
    assert len(ses) == 3
    c.patch(f"/api/sesiones/{ses[0]['id']}", json={"estado": "realizada"}, headers=h)
    c.patch(f"/api/sesiones/{ses[1]['id']}", json={"falta": True, "motivo": "Enfermedad"}, headers=h)
    c.patch(f"/api/sesiones/{ses[2]['id']}", json={"estado": "cancelada"}, headers=h)
    agenda = c.get("/api/agenda?desde=2026-10-05&hasta=2026-10-23", headers=h).get_json()["sesiones"]
    assert agenda[1]["estado"] == "cancelada" and agenda[1]["falta"] == 1 and agenda[1]["motivo"] == "Enfermedad"
    d = c.get(f"/api/alumnos/{al}/asistencia?trimestre=1&curso_escolar=2026/27", headers=h).get_json()
    assert d["realizadas"] == 1 and d["canceladas"] == 1
    assert d["faltas"] == [{"fecha": "2026-10-12", "motivo": "Enfermedad"}]
    # «Deshacer» quita la falta
    c.patch(f"/api/sesiones/{ses[1]['id']}", json={"estado": "planificada"}, headers=h)
    assert c.get(f"/api/alumnos/{al}/asistencia?trimestre=1&curso_escolar=2026/27", headers=h).get_json()["faltas"] == []
