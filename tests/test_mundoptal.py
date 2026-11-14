import datetime as dt
import io
from pathlib import Path

import pytest
from docx import Document

from mundoptal import dictado
from mundoptal.planificador import Planificador, lunes_de
from mundoptal.servidor import crear_app
from mundoptal.store import Store, StoreError
from mundoptal.word import exportar_aci, importar_aci

# ACIs reales (solo existen en el entorno de desarrollo; no se suben al repositorio por privacidad)
EJEMPLOS = [Path("/mnt/project-files/aci-ejemplo-1/ACI_ejemplo1_1T.docx"),
            Path("/mnt/project-files/aci-ejemplo-2/ACI_ejemplo2_1T.docx")]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


@pytest.fixture
def cliente(tmp_path):
    app = crear_app(tmp_path / "api.db")
    return app.test_client()


# ---------------------------------------------------------------- dictado
def test_dictado_jerarquia_completa():
    texto = ("Área comunicación y representación de la realidad. Subárea área preverbal. "
             "Competencia desarrollar la atención. Ítem mantiene la mirada en el objeto. "
             "Ítem señala el objeto que se le pide entre varias alternativas. "
             "Subárea área fonético-fonológica. Competencia desarrollar la capacidad articulatoria. "
             "Ítem articula las vocales")
    r = dictado.analizar(texto)
    assert r["totales"] == {"areas": 1, "subareas": 2, "competencias": 2, "items": 3}
    a = r["areas"][0]
    assert a["nombre"] == "Comunicación y representación de la realidad"
    assert a["subareas"][0]["nombre"] == "Área preverbal"
    assert a["subareas"][0]["competencias"][0]["nombre"] == "Desarrollar la atención"
    assert a["subareas"][0]["competencias"][0]["items"] == [
        "Mantiene la mirada en el objeto.", "Señala el objeto que se le pide entre varias alternativas."]
    assert a["subareas"][1]["competencias"][0]["items"] == ["Articula las vocales."]


def test_dictado_sin_puntuacion_como_vosk():
    # Vosk no pone signos: se separa con las palabras clave y con «punto»
    texto = ("nueva área el camino de las letras competencia las vocales ítem asocia cada vocal "
             "con su sonido punto empareja letras ítem discrimina el área del cuerpo")
    r = dictado.analizar(texto)
    a = r["areas"][0]
    assert a["nombre"] == "El camino de las letras"
    comp = a["subareas"][0]
    assert comp["nombre"] == ""  # sin subárea
    assert comp["competencias"][0]["nombre"] == "Las vocales"
    # «el área» no abre un área nueva (va precedida de artículo)
    assert comp["competencias"][0]["items"] == [
        "Asocia cada vocal con su sonido.", "Empareja letras.", "Discrimina el área del cuerpo."]


def test_dictado_frases_tras_competencia_son_items():
    r = dictado.analizar("Competencias y saberes: Autonomía.\nSe ocupa de la higiene.\nAvisa para ir al baño.")
    c = r["areas"][0]["subareas"][0]["competencias"][0]
    assert c["nombre"] == "Autonomía"
    assert c["items"] == ["Se ocupa de la higiene.", "Avisa para ir al baño."]
    assert r["areas"][0]["nombre"] == ""


def test_dictado_vacio():
    assert dictado.analizar("")["areas"] == []


# ---------------------------------------------------------------- store
def _aci_con_items(store, n_items=4, nombre="Ana"):
    al = store.crear_alumno(nombre, "3 años")
    aci = store.crear_aci(al, {"trimestre": 1})
    arbol = dictado.analizar(
        "Área comunicación. Subárea preverbal. Competencia atención. "
        + " ".join(f"Ítem objetivo {i}." for i in range(n_items))
        + " Competencia imitación. Ítem imita sonidos. Ítem imita gestos.")
    store.fusionar_dictado(aci, arbol["areas"])
    return al, aci


def test_fusion_reutiliza_nombres(store):
    al, aci = _aci_con_items(store)
    r = store.fusionar_dictado(aci, dictado.analizar(
        "Área COMUNICACIÓN. Subárea Preverbal. Competencia Atención. Ítem uno más.")["areas"])
    assert r == {"areas": 0, "subareas": 0, "competencias": 0, "items": 1}
    datos = store.obtener_aci(aci)
    assert len(datos["areas"]) == 1
    assert len(datos["areas"][0]["subareas"][0]["competencias"][0]["items"]) == 5
    assert len(datos["adaptaciones"]) == 5


def test_fusion_con_contexto(store):
    al, aci = _aci_con_items(store)
    comp = store.obtener_aci(aci)["areas"][0]["subareas"][0]["competencias"][1]
    store.fusionar_dictado(aci, dictado.analizar("Imita palmadas.")["areas"],
                           {"competencia_id": comp["id"]})
    comp2 = store.obtener_aci(aci)["areas"][0]["subareas"][0]["competencias"][1]
    assert [i["texto"] for i in comp2["items"]][-1] == "Imita palmadas."


def test_evaluacion_invalida(store):
    _, aci = _aci_con_items(store)
    item = store.obtener_aci(aci)["areas"][0]["subareas"][0]["competencias"][0]["items"][0]
    with pytest.raises(StoreError):
        store.actualizar("items", item["id"], {"eval_1t": "XX"})
    store.actualizar("items", item["id"], {"eval_1t": "ED+"})
    assert store.obtener_aci(aci)["resumen"]["por_valor"]["ED+"] == 1


def test_mover_y_duplicar(store):
    _, aci = _aci_con_items(store)
    comps = store.obtener_aci(aci)["areas"][0]["subareas"][0]["competencias"]
    store.mover("competencias", comps[1]["id"], -1)
    comps2 = store.obtener_aci(aci)["areas"][0]["subareas"][0]["competencias"]
    assert comps2[0]["nombre"] == "Imitación"
    nuevo = store.duplicar_aci(aci)
    d = store.obtener_aci(nuevo)
    assert d["trimestre"] == 2 and d["resumen"]["total"] == 6


# ---------------------------------------------------------------- planificador
def test_planificacion_rota_items_y_salta_conseguidos(store):
    plan = Planificador(store)
    al, aci = _aci_con_items(store, n_items=4)
    items = [i for c in store.obtener_aci(aci)["areas"][0]["subareas"][0]["competencias"] for i in c["items"]]
    store.actualizar("items", items[0]["id"], {"eval_1t": "C"})
    plan.guardar_franja({"dia": 0, "inicio": "09:00", "fin": "09:45", "items_por_sesion": 2, "alumnos": [al]})
    plan.guardar_franja({"dia": 2, "inicio": "10:00", "fin": "10:45", "items_por_sesion": 2, "alumnos": [al]})
    lunes = lunes_de(dt.date(2026, 11, 9))
    r = plan.planificar(lunes.isoformat(), (lunes + dt.timedelta(days=13)).isoformat())
    assert r["sesiones"] == 4 and r["items"] == 8
    ag = plan.agenda(lunes.isoformat(), (lunes + dt.timedelta(days=13)).isoformat())
    usados = [it["id"] for s in ag for it in s["items"]]
    assert items[0]["id"] not in usados             # conseguido: nunca se planifica
    assert len(set(usados[:4])) == 4                # las 2 primeras sesiones no repiten ítems
    assert len({it["competencia"] for it in ag[0]["items"]}) == 2  # reparte competencias
    # Repetir la planificación no duplica sesiones
    assert plan.planificar(lunes.isoformat(), (lunes + dt.timedelta(days=13)).isoformat())["sesiones"] == 0


def test_evaluar_desde_agenda_y_especialidad(store):
    plan = Planificador(store)
    al, aci = _aci_con_items(store, n_items=1)
    area = store.obtener_aci(aci)["areas"][0]
    store.actualizar("areas", area["id"], {"especialidad": "AL"})
    plan.guardar_franja({"dia": 0, "inicio": "09:00", "fin": "09:30", "especialidad": "PT", "alumnos": [al]})
    r = plan.planificar("2026-11-09", "2026-11-09")
    assert r["items"] == 0 and r["sin_pendientes"] == ["Ana"]
    f2 = plan.guardar_franja({"dia": 1, "inicio": "09:00", "fin": "09:30", "especialidad": "AL", "items_por_sesion": 1, "alumnos": [al]})
    plan.planificar("2026-11-10", "2026-11-10")
    s = plan.agenda("2026-11-10", "2026-11-10")[0]
    plan.marcar_item(s["id"], s["items"][0]["id"], trabajado=True, evaluacion="C")
    assert plan.agenda("2026-11-10", "2026-11-10")[0]["items"][0]["evaluacion"] == "C"
    assert f2


def test_franjas_solapadas(store):
    plan = Planificador(store)
    plan.guardar_franja({"dia": 0, "inicio": "09:00", "fin": "10:00"})
    with pytest.raises(StoreError):
        plan.guardar_franja({"dia": 0, "inicio": "09:30", "fin": "10:30"})
    with pytest.raises(StoreError):
        plan.guardar_franja({"dia": 1, "inicio": "10:00", "fin": "09:00"})


# ---------------------------------------------------------------- Word
def test_exportar_e_importar_ida_y_vuelta(store):
    _, aci = _aci_con_items(store)
    d = store.obtener_aci(aci)
    item = d["areas"][0]["subareas"][0]["competencias"][0]["items"][1]
    store.actualizar("items", item["id"], {"eval_1t": "ED", "destacado": 1, "nota": "señala 3 de 5"})
    store.actualizar("adaptaciones", d["adaptaciones"][2]["id"], {"tipo": "significativa", "nivel_curricular": "1º de infantil"})
    d = store.obtener_aci(aci)
    datos = exportar_aci(d)
    doc = Document(io.BytesIO(datos))
    assert "Ana" in "\n".join(p.text for p in doc.paragraphs)
    # Tabla del área: nº | ítem | observaciones | 1T | 2T | 3T
    tabla = doc.tables[1]
    cab = [c.text for c in next(r for r in tabla.rows if r.cells[0].text == "TRIMESTRES").cells]
    assert cab[2:] == ["OBSERVACIONES", "1T", "2T", "3T"]
    fila = next(r for r in tabla.rows if r.cells[1].text == item["texto"])
    assert [c.text for c in fila.cells[2:]] == ["señala 3 de 5", "ED", "", ""]
    vuelta = importar_aci(datos)
    assert vuelta["alumno_nombre"] == "Ana"
    assert vuelta["adaptaciones"][2]["tipo"] == "significativa"
    sub = vuelta["areas"][0]["subareas"][0]
    assert sub["nombre"] == "Preverbal"
    it = sub["competencias"][0]["items"][1]
    assert it["eval_1t"] == "ED" and it["destacado"] and it["nota"] == "señala 3 de 5"


@pytest.mark.parametrize("ruta", [p for p in EJEMPLOS if p.exists()])
def test_importar_aci_real(ruta):
    r = importar_aci(ruta)
    assert r["alumno_nombre"]
    assert len(r["adaptaciones"]) >= 3
    assert r["areas"] and r["areas"][0]["subareas"][0]["nombre"].lower().startswith("área preverbal")
    total = sum(len(c["items"]) for a in r["areas"] for s in a["subareas"] for c in s["competencias"])
    assert total > 20


# ---------------------------------------------------------------- API
def test_api_flujo_completo(cliente):
    al = cliente.post("/api/alumnos", json={"nombre": "Leo"}).get_json()["id"]
    aci = cliente.post(f"/api/alumnos/{al}/acis", json={}).get_json()["id"]
    r = cliente.post(f"/api/acis/{aci}/dictado", json={"texto": "Área lenguaje. Competencia léxico. Ítem nombra colores."})
    assert r.get_json()["items"] == 1
    datos = cliente.get(f"/api/acis/{aci}").get_json()
    item_id = datos["areas"][0]["subareas"][0]["competencias"][0]["items"][0]["id"]
    assert cliente.patch(f"/api/items/{item_id}", json={"eval_1t": "I"}).status_code == 200
    assert cliente.patch(f"/api/items/{item_id}", json={"eval_1t": "mal"}).status_code == 400
    assert cliente.patch("/api/franjas_falsas/1", json={}).status_code == 400
    f = cliente.post("/api/franjas", json={"dia": 0, "inicio": "09:00", "fin": "09:45", "alumnos": [al]}).get_json()["id"]
    assert f
    p = cliente.post("/api/planificar", json={"desde": "2026-11-09", "hasta": "2026-11-13"}).get_json()
    assert p["sesiones"] == 1 and p["items"] == 1
    ag = cliente.get("/api/agenda?desde=2026-11-09").get_json()
    assert ag["sesiones"][0]["alumno"] == "Leo"
    w = cliente.get(f"/api/acis/{aci}/word")
    assert w.status_code == 200 and w.data[:2] == b"PK"
    imp = cliente.post("/api/importar-word", data={"archivo": (io.BytesIO(w.data), "a.docx")},
                       content_type="multipart/form-data").get_json()
    assert imp["alumno_id"] == al  # reconoce al alumno por el nombre
    assert cliente.delete(f"/api/alumnos/{al}").status_code == 200
    assert cliente.get("/api/alumnos").get_json() == []
    assert cliente.get("/").status_code == 200
    assert cliente.get("/api/voz").get_json()["grabando"] is False
