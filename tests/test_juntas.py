"""Juntas de evaluación: notas por alumno que se redactan para el informe del trimestre.
Todos los nombres son inventados."""
from mundoptal import informes, juntas
from mundoptal.servidor import crear_app
from mundoptal.store import Store

NOTAS = """- La tutora dice que está muy contento y participa más en la asamblea
- le cuesta esperar su turno, rabietas cuando pierde
- en las sesiones atiende mejor y termina las tareas con apoyo
- ya consigue contar hasta 10!!
- habla más, hace frases de 3 palabras
- reconoce las vocales y escribe su nombre con modelo
- los pictogramas le ayudan mucho a anticipar
- recomendar a la familia que lean cuentos juntos
- Orientación: van a pasarle pruebas de lenguaje"""


def _preparar(tmp_path):
    s = Store(tmp_path / "j.db")
    uid = s.crear_usuario("Profe", "PT/AL")
    a = s.crear_alumno("Teo Prueba", usuario_id=uid)
    o = s.crear_alumno("Nora", usuario_id=uid)
    s.actualizar("alumnos", o, {"seguimiento": "observacion"})
    return s, uid, a, o


def test_junta_por_trimestre_y_notas(tmp_path):
    s, uid, a, o = _preparar(tmp_path)
    j = juntas.obtener(s, uid, 1, "2026/27")
    assert j["trimestre"] == 1 and {x["nombre"] for x in j["alumnos"]} == {"Nora", "Teo Prueba"}
    assert juntas.obtener(s, uid, 1, "2026/27")["id"] == j["id"]  # no se duplica
    assert juntas.obtener(s, uid, 2, "2026/27")["id"] != j["id"]
    juntas.guardar_notas(s, j["id"], a, "hola")
    juntas.guardar_notas(s, j["id"], a, NOTAS)
    teo = next(x for x in juntas.obtener(s, uid, 1, "2026/27")["alumnos"] if x["alumno_id"] == a)
    assert teo["notas"] == NOTAS and teo["informe"] is None


def test_frases_profesionales_y_nunca_conseguido():
    fs = juntas.frases("- la tutora comenta q está mto contento\n- ya consigue contar hasta 10!!\n- lo domina")
    assert fs[0]["fuente"] == "aula" and fs[0]["texto"].startswith("Está") and "contento" in fs[0]["texto"]
    textos = " ".join(f["texto"] for f in fs).lower()
    assert "consigue" not in textos and "domina" not in textos and "!" not in textos
    assert "está empezando a contar hasta 10" in textos


def test_borrador_reparte_por_apartados(tmp_path):
    s, uid, a, o = _preparar(tmp_path)
    j = juntas.obtener(s, uid, 1, "2026/27")
    juntas.guardar_notas(s, j["id"], a, NOTAS)
    b = juntas.borrador(s, j["id"], a, "PT/AL")
    ap = {x["clave"]: x["texto"] for x in b["apartados"]}
    assert b["tipo"] == "informe"
    assert ap["social"].startswith("Durante este trimestre, en el aula Teo")
    assert "momentos de desregulación emocional" in ap["social"] and "rabieta" not in ap["social"]
    assert "actitud_pt" in ap and "estrategias" in ap
    assert ap["orientaciones"].startswith("Os animamos a que lean cuentos")
    assert any(k.startswith("area:Lógico") for k in ap)
    assert "Departamento de Orientación" in " ".join(ap.values())
    assert "conseguido" not in " ".join(ap.values()).lower()


def test_pasar_al_informe_crea_y_no_duplica(tmp_path):
    s, uid, a, o = _preparar(tmp_path)
    j = juntas.obtener(s, uid, 1, "2026/27")
    juntas.guardar_notas(s, j["id"], a, NOTAS)
    b = juntas.borrador(s, j["id"], a, "PT/AL")
    r = juntas.pasar_al_informe(s, j["id"], a, b["apartados"], maestra="Profe")
    inf = informes.obtener(s, r["id"])
    assert r["tipo"] == "informe" and inf["trimestre"] == 1 and inf["curso_escolar"] == "2026/27"
    social = inf["social"]
    assert social.startswith("Durante este trimestre")
    s.actualizar("informes", r["id"], {"social": "Texto propio.\n" + social})
    juntas.pasar_al_informe(s, j["id"], a, b["apartados"])
    inf = informes.obtener(s, r["id"])
    assert inf["social"].count("Durante este trimestre") == 1 and inf["social"].startswith("Texto propio.")
    assert len([x for x in inf["areas"] if x["area"] == "Lógico-matemática"]) == 1
    assert next(x for x in juntas.obtener(s, uid, 1, "2026/27")["alumnos"] if x["alumno_id"] == a)["pasado"]


def test_alumno_en_valoracion_va_al_informe_de_observacion(tmp_path):
    s, uid, a, o = _preparar(tmp_path)
    j = juntas.obtener(s, uid, 1, "2026/27")
    juntas.guardar_notas(s, j["id"], o, NOTAS)
    b = juntas.borrador(s, j["id"], o)
    claves = {x["clave"] for x in b["apartados"]}
    assert b["tipo"] == "observacion" and "motivo" in claves and "estrategias" in claves
    r = juntas.pasar_al_informe(s, j["id"], o, b["apartados"])
    assert r["tipo"] == "observacion"
    aps = {x["clave"]: x["texto"] for x in s.q("SELECT clave, texto FROM observacion_apartados WHERE informe_id = ?",
                                               (r["id"],))}
    assert "pictogramas" in aps["estrategias"]


def test_api_juntas(tmp_path):
    app = crear_app(tmp_path / "api.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Profe", "especialidad": "PT"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    al = c.post("/api/alumnos", json={"nombre": "Teo"}, headers=h).get_json()["id"]
    j = c.get("/api/juntas?trimestre=1&curso_escolar=2026/27", headers=h).get_json()
    assert j["trimestre"] == 1 and j["alumnos"][0]["alumno_id"] == al
    assert c.patch(f"/api/juntas/{j['id']}", json={"fecha": "2026-11-25"}, headers=h).status_code == 200
    assert c.put(f"/api/juntas/{j['id']}/alumnos/{al}", json={"notas": NOTAS}, headers=h).status_code == 200
    b = c.get(f"/api/juntas/{j['id']}/alumnos/{al}/borrador", headers=h).get_json()
    assert any(x["clave"] == "actitud_pt" for x in b["apartados"])
    r = c.post(f"/api/juntas/{j['id']}/alumnos/{al}/informe", json={"apartados": b["apartados"]}, headers=h).get_json()
    assert r["tipo"] == "informe"
    inf = c.get(f"/api/informes/{r['id']}", headers=h).get_json()
    assert inf["maestra"] == "Profe" and inf["social"]
    vacio = c.post(f"/api/juntas/{j['id']}/alumnos/{al}/informe", json={"apartados": []}, headers=h)
    assert vacio.status_code == 400
    j2 = c.get("/api/juntas?trimestre=1&curso_escolar=2026/27", headers=h).get_json()
    assert j2["fecha"] == "2026-11-25" and j2["alumnos"][0]["informe"]["id"] == r["id"]
