"""Alumnos en valoración (sin ACI), informe de observación y actualización del horario
sin perder la historia de las sesiones. Todos los nombres son inventados."""
import datetime as dt
import io

from docx import Document

from mundoptal import horario, observacion
from mundoptal.planificador import Planificador, lunes_de
from mundoptal.servidor import crear_app
from mundoptal.store import Store

CABECERA = ["", "LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES"]
VIEJO = [
    ["HORARIO PRUEBA PT/AL", "", "", "", "", ""], CABECERA,
    ["9:00-10:00", "ANA", "LUIS", "ANA/ PEPE", "ANA/PEPE", "MARIO"],
    ["10:00-11:00", "MARIO", "MARIO", "LEO/MARIO.L", "MARIO", "LUIS"],
    ["11:30-12:15", "PEPE", "TIEMPO DE TRABAJO", "MARIO", "LUIS", "DEPARTAMENTO ORIENTACIÓN"],
]
NUEVO = [
    ["HORARIO PRUEBA PT/AL", "", "", "", "", ""], CABECERA,
    ["9:00-10:00", "ANA", "LUIS", "ANA/ PEPE", "ANA/PEPE", "MARIO"],
    ["10:00-11:00", "MARIO", "MARIO", "LEO/MARIO.L", "MARIO", "LUIS"],
    ["11:30-12:15", "PEPE", "PRUEBAS DE LENGUAJE", "MARIO", "NOA, SARA E IRENE", "DEPARTAMENTO ORIENTACIÓN"],
    ["12:15-13:00", "NOA, SARA E IRENE", "", "", "", ""],
]


def _franja(franjas, dia, inicio):
    return next(f for f in franjas if f["dia"] == dia and f["inicio"] == inicio)


def test_analizar_nuevo_formato():
    franjas = horario.analizar_tabla(NUEVO)
    assert _franja(franjas, 1, "11:30")["tipo"] == "otro"  # PRUEBAS DE LENGUAJE no es un alumno
    assert _franja(franjas, 3, "11:30")["alumnos"] == ["Noa", "Sara", "Irene"]
    assert _franja(franjas, 2, "10:00")["alumnos"] == ["Leo", "Mario.l"]


def test_candidatos_por_nombre_e_inicial():
    alumnos = [{"id": 1, "nombre": "Mario Pérez", "activo": 1}, {"id": 2, "nombre": "Mario López", "activo": 1},
               {"id": 3, "nombre": "Ana", "activo": 1}]
    assert [a["id"] for a in horario.candidatos("MARIO.L", alumnos)] == [2]
    assert {a["id"] for a in horario.candidatos("Mario", alumnos)} == {1, 2}
    assert [a["id"] for a in horario.candidatos("ANA", alumnos)] == [3]
    assert horario.candidatos("Irene", alumnos) == []


def _preparar(tmp_path):
    s = Store(tmp_path / "o.db")
    plan = Planificador(s)
    uid = s.crear_usuario("Profe", "PT/AL")
    for n in ("Ana", "Luis", "Pepe", "Leo", "Mario Pérez", "Mario López"):
        s.crear_alumno(n, usuario_id=uid)
    return s, plan, uid


def test_proponer_alumnos_y_valoracion(tmp_path):
    s, plan, uid = _preparar(tmp_path)
    perez = s.buscar_alumno("Mario Pérez", uid)["id"]
    lopez = s.buscar_alumno("Mario López", uid)["id"]
    horario.importar_horario(s, plan, uid, horario.analizar_tabla(VIEJO),
                             asignacion={"Mario": perez, "Mario.l": lopez})
    franjas = horario.analizar_tabla(NUEVO)
    prop = {p["texto"]: p for p in horario.proponer_alumnos(s, plan, uid, franjas)}
    # «Mario» encaja con dos alumnos: se propone el que más sesiones tenía, avisando
    assert prop["Mario"]["alumno_id"] == perez and prop["Mario"]["dudoso"]
    assert prop["Mario.l"]["alumno_id"] == lopez and not prop["Mario.l"]["dudoso"]
    assert prop["Irene"]["alumno_id"] is None
    cambios = horario.resumen_cambios(plan, uid, franjas, list(prop.values()))
    assert cambios["nuevas"] == 1 and cambios["cambiadas"] == 2 and cambios["retiradas"] == 0

    r = horario.importar_horario(s, plan, uid, franjas, reemplazar=True,
                                 en_valoracion=["Noa", "Sara", "Irene"])
    assert r["alumnos_nuevos"] == ["Irene", "Noa", "Sara"] and r["omitidas"] == []
    nuevos = [s.buscar_alumno(n, uid) for n in ("Noa", "Sara", "Irene")]
    assert all(a["seguimiento"] == "observacion" for a in nuevos)
    # No se duplican alumnos: Mario sigue siendo Mario Pérez
    assert len(s.listar_alumnos(uid)) == 9
    lunes_10 = _franja(plan.listar_franjas(uid), 0, "10:00")
    assert [a["id"] for a in lunes_10["alumnos"]] == [perez]
    # Al crear una ACI deja de estar en valoración
    s.crear_aci(nuevos[0]["id"])
    assert s.obtener_alumno(nuevos[0]["id"])["seguimiento"] == "aci"


def test_actualizar_horario_conserva_notas_pasadas(tmp_path):
    s, plan, uid = _preparar(tmp_path)
    horario.importar_horario(s, plan, uid, horario.analizar_tabla(VIEJO))
    # Sesiones de la semana pasada con notas en el martes 11:30 (TIEMPO DE TRABAJO no tiene sesiones)
    lunes = lunes_de(dt.date.today()) - dt.timedelta(days=7)
    plan.planificar(lunes.isoformat(), (lunes + dt.timedelta(days=4)).isoformat(), usuario_id=uid)
    franja_lunes = _franja(plan.listar_franjas(uid), 0, "11:30")  # PEPE
    ses = s.q1("SELECT id FROM sesiones WHERE franja_id = ?", (franja_lunes["id"],))
    plan.actualizar_sesion(ses["id"], {"notas": "Hoy ha estado muy atento"})
    # Horario nuevo: el lunes 11:30 desaparece y en su lugar hay otra franja 11:00-12:00
    tabla = [fila[:] for fila in VIEJO]
    tabla[4][1] = ""
    tabla.append(["11:00-12:00", "LEO", "", "", "", ""])
    r = horario.importar_horario(s, plan, uid, horario.analizar_tabla(tabla), reemplazar=True)
    assert r["retiradas"] == 1 and r["omitidas"] == []
    assert s.q1("SELECT notas FROM sesiones WHERE id = ?", (ses["id"],))["notas"] == "Hoy ha estado muy atento"
    assert s.q1("SELECT archivada FROM franjas WHERE id = ?", (franja_lunes["id"],))["archivada"] == 1
    actuales = plan.listar_franjas(uid)
    assert all(f["id"] != franja_lunes["id"] for f in actuales)
    assert _franja(actuales, 0, "11:00")["alumnos"][0]["nombre"] == "Leo"
    # Una franja sin historia se borra del todo
    jueves = _franja(actuales, 3, "11:30")
    s.conn.execute("DELETE FROM sesiones WHERE franja_id = ?", (jueves["id"],))
    assert plan.borrar_franja(jueves["id"]) == "borrada"


def test_informe_de_observacion(tmp_path):
    s, plan, uid = _preparar(tmp_path)
    horario.importar_horario(s, plan, uid, horario.analizar_tabla(NUEVO), en_valoracion=["Noa", "Sara", "Irene"])
    noa = s.buscar_alumno("Noa", uid)["id"]
    lunes = lunes_de(dt.date.today()) - dt.timedelta(days=7)
    res = plan.planificar(lunes.isoformat(), (lunes + dt.timedelta(days=4)).isoformat(), usuario_id=uid)
    assert "Noa" not in res["sin_pendientes"]  # sin ACI no se avisa de «sin ítems»
    ses = s.q("SELECT id FROM sesiones WHERE alumno_id = ? ORDER BY fecha", (noa,))
    assert len(ses) == 2
    plan.actualizar_sesion(ses[0]["id"], {"notas": "se distrae mucho, hay q repetirle la orden"})
    plan.actualizar_sesion(ses[1]["id"], {"notas": "hace frases cortas. Juega con los compañeros"})

    inf_id = observacion.crear(s, noa, maestra="Profe")
    inf = observacion.obtener(s, inf_id)
    assert [a["clave"] for a in inf["apartados"]][:3] == ["motivo", "contexto", "conducta"]
    contexto = next(a for a in inf["apartados"] if a["clave"] == "contexto")["texto"]
    assert "2 sesiones semanales" in contexto and "lunes de 12:15 a 13:00" in contexto and "pequeño grupo" in contexto
    assert inf["desde"] == lunes.isoformat()
    n = observacion.notas(s, inf_id)
    assert [x["apartado"] for x in n["notas"]] == ["atencion", "expresion", "relacion"]
    assert n["notas"][0]["texto"].startswith("Se distrae mucho")
    s.actualizar("observacion_apartados", inf["apartados"][2]["id"], {"texto": "Viene con agrado.\nParticipa."})
    doc = Document(io.BytesIO(observacion.exportar_word(s, observacion.obtener(s, inf_id))))
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "INFORME DE OBSERVACIÓN" in texto and "COMPORTAMIENTO Y ACTITUD EN LAS SESIONES" in texto
    assert "Participa." in texto and "QUÉ LE AYUDA" not in texto  # los apartados vacíos no salen


def test_api_observacion_y_vista_previa(tmp_path):
    app = crear_app(tmp_path / "a.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Profe", "especialidad": "PT/AL"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    al = c.post("/api/alumnos", json={"nombre": "Noa", "seguimiento": "observacion"}, headers=h).get_json()["id"]
    assert c.get(f"/api/alumnos/{al}", headers=h).get_json()["seguimiento"] == "observacion"
    assert c.patch(f"/api/alumnos/{al}", json={"seguimiento": "otro"}, headers=h).status_code == 400
    oid = c.post(f"/api/alumnos/{al}/observaciones", json={}, headers=h).get_json()["id"]
    o = c.get(f"/api/observaciones/{oid}", headers=h).get_json()
    assert o["maestra"] == "Profe" and len(o["apartados"]) == len(observacion.APARTADOS)
    assert c.post(f"/api/observaciones/{oid}/apartados", json={"titulo": "Juego"}, headers=h).status_code == 200
    assert c.get(f"/api/observaciones/{oid}/notas", headers=h).get_json()["notas"] == []
    assert c.get(f"/api/observaciones/{oid}/word", headers=h).status_code == 200
    assert c.get(f"/api/alumnos/{al}", headers=h).get_json()["observaciones_informes"][0]["id"] == oid
    resumen = c.get("/api/informes", headers=h).get_json()["alumnos"]
    assert resumen[0]["observaciones"][0]["id"] == oid

    csv_bytes = "\n".join(",".join(f) for f in VIEJO).encode("utf-8")
    p = c.post("/api/horario/analizar", headers=h, content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(csv_bytes), "h.csv")}).get_json()
    assert len(p["franjas"]) == 15 and {n["texto"] for n in p["nombres"]} >= {"Ana", "Mario.l"}
    r = c.post("/api/horario/importar", headers=h, content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(csv_bytes), "h.csv"), "reemplazar": "1",
                     "asignacion": '{"Ana": "nuevo"}', "en_valoracion": '["Ana"]'}).get_json()
    assert r["franjas"] == 15 and "Ana" in r["alumnos_nuevos"]
    alumnos = {a["nombre"]: a for a in c.get("/api/alumnos", headers=h).get_json()}
    assert alumnos["Ana"]["seguimiento"] == "observacion" and alumnos["Luis"]["seguimiento"] == "aci"
    assert c.delete(f"/api/informes_observacion/{oid}", headers=h).status_code == 200
