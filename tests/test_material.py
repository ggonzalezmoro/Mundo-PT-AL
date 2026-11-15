"""Crear material: plantillas, maquetación en Word/PowerPoint y Claude con un cliente falso.
Nunca se llama a la API real, ni a Internet (pictogramas desactivados), ni al
Administrador de credenciales real (keyring en memoria)."""
import io
from types import SimpleNamespace

import keyring
import pytest
from docx import Document
from keyring.backend import KeyringBackend
from pptx import Presentation

from mundoptal import ia_material, maqueta, material
from mundoptal.servidor import crear_app


class KeyringMemoria(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.datos = {}

    def get_password(self, servicio, usuario):
        return self.datos.get((servicio, usuario))

    def set_password(self, servicio, usuario, clave):
        self.datos[(servicio, usuario)] = clave

    def delete_password(self, servicio, usuario):
        self.datos.pop((servicio, usuario), None)


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    anterior = keyring.get_keyring()
    keyring.set_keyring(KeyringMemoria())
    monkeypatch.setenv("MUNDOPTAL_DOCUMENTOS", str(tmp_path / "Documentos"))
    yield
    keyring.set_keyring(anterior)


def _paginas_docx(datos: bytes) -> int:
    doc = Document(io.BytesIO(datos))
    saltos = sum(1 for br in doc.element.body.iter() if br.tag.endswith("}br") and br.get(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type") == "page")
    return saltos + 1


def _sin_red():
    return maqueta.Recursos(carpeta_pictos=None, cabecera="Maestra Prueba", alumno="Alumna Prueba")


@pytest.mark.parametrize("tipo,contenido", [
    ("letras", "vocales"), ("letras", "M P"), ("silabas", "M P L"), ("numeros", "1-5"), ("emparejar", "A E I"),
    ("emparejar", "1 2 3"), ("emparejar", "perro gato vaca"), ("espaciales", ""), ("emociones", ""),
    ("vocabulario", "comida"), ("vocabulario", "pelota coche muñeca"), ("rutinas", ""), ("rutinas", "vestirse"),
    ("praxias", ""), ("praxias", "soplar beso"), ("fonologia", ""), ("fonologia", "rimas"), ("auditiva", ""),
    ("auditiva", "transporte"), ("cuento", "El perro come. La niña juega con la pelota en el parque grande.")])
def test_cada_plantilla_genera_word_y_powerpoint_validos(tipo, contenido):
    spec = material.plantilla(tipo, contenido, "4", None, semilla=3)
    assert spec.paginas and all(p.enunciado for p in spec.paginas)
    docx = maqueta.a_word(spec, _sin_red())
    assert _paginas_docx(docx) == len(spec.paginas)
    assert "Maestra Prueba · PT/AL" in "\n".join(p.text for t in Document(io.BytesIO(docx)).sections[0].header.tables
                                                for c in t._cells for p in c.paragraphs)
    pptx = Presentation(io.BytesIO(maqueta.a_powerpoint(spec, _sin_red())))
    assert len(pptx.slides) == len(spec.paginas)


def test_numero_de_fichas_pedido():
    for num in (1, 5, 13):
        spec = material.plantilla("letras", "vocales", "3", num)
        assert len(spec.paginas) == num
        assert _paginas_docx(maqueta.a_word(spec, _sin_red())) == num
    # Con pocas fichas salen todas las vocales antes de repetir actividad
    assert [p.destacado for p in material.plantilla("letras", "vocales", "4", 5).paginas] == ["A a", "E e", "I i", "O o", "U u"]


def test_plantillas_nuevas_contenido():
    vestirse = material.plantilla("rutinas", "vestirse", "4")
    assert [p.actividad for p in vestirse.paginas] == ["cuento", "secuencia"]
    assert vestirse.paginas[1].elementos[0].texto == "Me pongo la camiseta"  # la secuencia se guarda en orden; se desordena al maquetar
    praxias = material.plantilla("praxias", "soplar beso", "4")
    assert {e.texto for e in praxias.paginas[0].elementos} == {"SOPLA", "MANDA UN BESO"}
    fono = material.plantilla("fonologia", "", "3")
    palmadas = [e for p in fono.paginas if p.actividad == "cuento" for e in p.elementos]
    assert palmadas and all("○" in e.texto for e in palmadas)
    assert all(len(e.pictograma) and e.pictograma not in ("mariposa", "elefante", "pelota", "zapato") for e in palmadas)  # 3 años: ≤2 sílabas
    rimas = [p for p in fono.paginas if p.actividad == "pregunta"]
    assert rimas and all(sum(e.correcto for e in p.elementos) == 1 for p in rimas)
    auditiva = material.plantilla("auditiva", "animales", "4")
    assert auditiva.paginas[0].elementos[0].texto == "PERRO · GUAU"
    frases = material.frases_con_pictos("El perro come una manzana. ¡La niña juega!")
    assert [[e.pictograma for e in f] for f in frases] == [["", "perro", "come", "", "manzana"], ["", "niña", "juega"]]


def test_linea_de_comandos_crea_material_desde_json(tmp_path):
    spec = material.plantilla("emociones", "", "4", 2)
    origen = tmp_path / "material.json"
    origen.write_text(spec.model_dump_json(), encoding="utf-8")
    assert material.main(["--spec", str(origen), "--formato", "pptx", "--sin-pictos", "--cabecera", "Maestra Prueba"]) == 0
    assert len(Presentation(str(tmp_path / "material.pptx")).slides) == 2
    salida = tmp_path / "otra" / "fichas.docx"
    assert material.main(["--spec", str(origen), "--salida", str(salida), "--sin-pictos"]) == 0
    assert _paginas_docx(salida.read_bytes()) == 2


def test_sugerencias_segun_la_aci():
    pendientes = [{"texto": "Reconoce las vocales", "competencia": "Lectoescritura"},
                  {"texto": "Cuenta hasta 5", "competencia": "Lógico-matemática"},
                  {"texto": "Identifica emociones básicas", "competencia": ""}]
    tipos = [s["tipo"] for s in material.sugerencias(pendientes)]
    assert tipos[:3] == ["letras", "numeros", "emociones"]


def test_anonimizar_nombres_de_alumnos():
    texto, quitados = ia_material.anonimizar(
        "Fichas de vocales para Bartolomé, que también trabaja con bartolome ejemplo y con Ximena Prueba",
        ["Bartolomé Ejemplo", "Ximena Prueba"])
    assert "Bartolom" not in texto and "bartolom" not in texto and "Ximena" not in texto and "Prueba" not in texto
    assert texto == "Fichas de vocales para el alumno, que también trabaja con el alumno y con el alumno"
    assert set(quitados) >= {"Bartolomé", "Ximena Prueba"}
    # Palabras normales que contienen un nombre no se tocan
    assert ia_material.anonimizar("Trabajar la Ximenadita", ["Ximena Prueba"])[0] == "Trabajar la Ximenadita"


def _spec_ejemplo():
    E = material.el
    return material.MaterialSpec(titulo="Vocales con animales", objetivo="Reconocer las vocales",
                                 instrucciones_maestra="Úsalo en sesiones cortas.",
                                 paginas=[material.pag("letra", "Esta es la A", "A a", [E("abeja", "abeja")]),
                                          material.pag("unir", "Une cada animal con su vocal",
                                                       elementos=[E("oso", "oso", pareja="O"), E("abeja", "abeja", pareja="A")]),
                                          material.pag("secuencia", "Ordena los pasos",
                                                       elementos=[E("Abro el grifo", "grifo"), E("Me lavo", "lavar"), E("Me seco", "toalla")])])


class ClienteFalso:
    """Imita client.beta.messages.parse y guarda lo que se le envía."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.llamadas.append(kw)
        stop, spec = self.respuestas.pop(0)
        return SimpleNamespace(stop_reason=stop, parsed_output=spec)


def test_claude_con_cliente_falso_se_maqueta_y_no_envia_nombres():
    falso = ClienteFalso([("end_turn", _spec_ejemplo())])
    r = ia_material.generar("Material de vocales para Alumna Prueba con animales", "4", "pptx", 3,
                            objetivos=["Reconoce las vocales", "Alumna Prueba señala la A"],
                            nombres_alumnos=["Alumna Prueba"], cliente=falso)
    llamada = falso.llamadas[0]
    enviado = llamada["messages"][0]["content"]
    assert "Alumna" not in enviado and "Prueba" not in enviado and "el alumno" in enviado
    assert llamada["model"] == "claude-opus-5-5" and llamada["output_format"] is material.MaterialSpec
    assert llamada["output_config"] == {"effort": "medium"} and llamada["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in llamada["betas"]
    assert r["anonimizados"] == ["Alumna Prueba"]
    spec = r["spec"]
    assert len(Presentation(io.BytesIO(maqueta.a_powerpoint(spec, _sin_red()))).slides) == 3
    assert _paginas_docx(maqueta.a_word(spec, _sin_red())) == 3


def test_claude_rechazo_y_reintento_con_menos_paginas():
    with pytest.raises(ia_material.ErrorIA, match="no ha podido"):
        ia_material.generar("algo", cliente=ClienteFalso([("refusal", None)]))
    falso = ClienteFalso([("max_tokens", None), ("end_turn", _spec_ejemplo())])
    ia_material.generar("vocales", num=10, cliente=falso)
    assert "exactamente 10" in falso.llamadas[0]["messages"][0]["content"]
    assert "exactamente 5" in falso.llamadas[1]["messages"][0]["content"]


def _cliente_app(tmp_path):
    app = crear_app(tmp_path / "m.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra Prueba", "especialidad": "PT/AL"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    c.post("/api/material/ajustes", json={"pictos": False}, headers=h)  # sin Internet en las pruebas
    return app, c, h


def test_la_clave_no_se_guarda_en_la_base_de_datos(tmp_path):
    app, c, h = _cliente_app(tmp_path)
    clave = "sk-ant-api03-" + "x" * 40
    assert c.post("/api/material/clave", json={"clave": "no-vale"}, headers=h).status_code == 400
    assert c.post("/api/material/clave", json={"clave": clave}, headers=h).status_code == 200
    assert c.get("/api/material/info", headers=h).get_json()["clave"] is True
    assert ia_material.leer_clave() == clave  # está en el almacén de credenciales
    app.extensions["store"].conn.execute("PRAGMA wal_checkpoint(FULL)")
    for f in tmp_path.glob("m.db*"):
        assert clave.encode() not in f.read_bytes()
    c.delete("/api/material/clave", headers=h)
    assert c.get("/api/material/info", headers=h).get_json()["clave"] is False


def test_sin_clave_se_usan_las_plantillas_y_se_guarda_el_material(tmp_path):
    app, c, h = _cliente_app(tmp_path)
    r = c.post("/api/material/propuesta", json={"modo": "ia", "peticion": "vocales"}, headers=h)
    assert r.status_code == 400 and "clave" in r.get_json()["error"]
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba"}, headers=h).get_json()["id"]
    p = c.post("/api/material/propuesta", json={"modo": "plantilla", "tipo": "numeros", "contenido": "1-3", "num": 4,
                                                "nivel": "3"}, headers=h).get_json()
    assert len(p["spec"]["paginas"]) == 4
    for formato in ("docx", "pptx"):
        r = c.post("/api/material/crear", json={"spec": p["spec"], "formato": formato, "alumno_id": al, "tipo": "numeros"},
                   headers=h).get_json()
        assert r["nombre"].endswith("." + formato) and (tmp_path / "Documentos" / "Material" / r["nombre"]).exists()
    lista = c.get("/api/materiales", headers=h).get_json()
    assert len(lista) == 2 and lista[0]["existe"] and lista[1]["alumno"] == "Alumna Prueba"
    assert c.get(f"/api/materiales/{lista[0]['id']}/archivo", headers=h).status_code == 200
    assert c.delete(f"/api/materiales/{lista[0]['id']}", headers=h).status_code == 200
    assert len(c.get("/api/materiales", headers=h).get_json()) == 1


def test_logo_y_cabecera_por_perfil(tmp_path):
    app, c, h = _cliente_app(tmp_path)
    assert c.get("/api/material/info", headers=h).get_json()["cabecera"] == "Maestra Prueba"
    c.post("/api/material/ajustes", json={"cabecera": "Seño Prueba"}, headers=h)
    info = c.get("/api/material/info", headers=h).get_json()
    assert info["cabecera"] == "Seño Prueba" and info["logo_propio"] is False
    png = (maqueta.static_dir() / "logo.png").read_bytes()
    r = c.post("/api/material/logo", data={"archivo": (io.BytesIO(png), "logo.png")}, headers=h,
               content_type="multipart/form-data")
    assert r.status_code == 200 and c.get("/api/material/info", headers=h).get_json()["logo_propio"] is True
    assert c.post("/api/material/logo", data={"archivo": (io.BytesIO(b"hola"), "x.txt")}, headers=h,
                  content_type="multipart/form-data").status_code == 400
    c.delete("/api/material/logo", headers=h)
    assert c.get("/api/material/info", headers=h).get_json()["logo_propio"] is False
