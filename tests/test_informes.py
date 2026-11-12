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
    assert texto.startswith("En el área de comunicación y representación, Ana ha conseguido lo siguiente: mantiene la mirada en el objeto.")
    assert "Actualmente se encuentra avanzando en: señala lo que quiere." in texto
    assert "Es recomendable seguir trabajando: nombra colores básicos." in texto
    assert inf["despedida"] == "¡Os deseamos unas felices fiestas de Navidad!"
    assert "Ana" in inf["frases"]["social"][0]
    assert "sin evaluar" not in texto.lower()

    assert c.patch(f"/api/informes/{inf_id}", json={"social": "Juega con sus compañeros.", "actitud_al": "Viene contenta."}, headers=h).status_code == 200
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
