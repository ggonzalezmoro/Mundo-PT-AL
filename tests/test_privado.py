"""Expediente privado: cifrado, contraseña, código de recuperación y que nada sale por otras vías.
Todos los nombres y textos son inventados."""
import io
import sqlite3

import pytest

from mundoptal import privado
from mundoptal.servidor import crear_app
from mundoptal.store import Store

PDF = b"%PDF-1.4\n% informe inventado de neurologia\n%%EOF"
SECRETO = "TEA grado 1 con TDAH combinado"


@pytest.fixture(autouse=True)
def kdf_rapido(monkeypatch):
    # scrypt de verdad tarda ~0,3 s por intento: en las pruebas se usa uno barato
    monkeypatch.setattr(privado, "KDF", {"n": 2 ** 10, "r": 8, "p": 1})


def test_cifrado_y_contrasena(tmp_path):
    exp = privado.Expediente(tmp_path / "p.mpx")
    assert not exp.configurado()
    with pytest.raises(privado.ErrorPrivado):
        exp.configurar("corta")
    codigo = exp.configurar("una contraseña larga")
    assert exp.abierto() and len(codigo) == 29
    exp.guardar_ficha(7, {"diagnostico": SECRETO, "pautas": "Anticipar cambios con pictogramas", "otro": "x"})
    did = exp.anadir_documento(7, "Neuro marzo.pdf", "application/pdf", PDF,
                               {"tipo": "neurologia", "profesional": "Dra. Inventada", "fecha": "2026-03-10"})
    exp.cerrar()
    # En el archivo no aparece nada legible
    crudo = (tmp_path / "p.mpx").read_bytes()
    for texto in (SECRETO.encode(), b"Inventada", b"Neuro marzo", b"informe inventado", b"neurologia"):
        assert texto not in crudo
    with pytest.raises(privado.Bloqueado):
        exp.ficha(7)
    with pytest.raises(privado.ErrorPrivado):
        exp.abrir("otra contraseña")
    exp.abrir("una contraseña larga")
    assert exp.ficha(7)["diagnostico"] == SECRETO and "otro" not in exp.ficha(7)
    meta, datos = exp.leer_documento(did)
    assert datos == PDF and meta["titulo"] == "Neuro marzo" and meta["tipo_texto"] == "Neurología" and meta["mostrable"]
    assert exp.resumen() == {7: 1}


def test_codigo_de_recuperacion_y_cambio(tmp_path):
    exp = privado.Expediente(tmp_path / "p.mpx")
    codigo = exp.configurar("primera contraseña")
    exp.guardar_ficha(1, {"diagnostico": SECRETO})
    exp.cerrar()
    # Contraseña olvidada: con el código (da igual guiones o minúsculas) se pone otra
    exp.cambiar_contrasena("segunda contraseña", codigo=codigo.lower().replace("-", " "))
    exp.cerrar()
    with pytest.raises(privado.ErrorPrivado):
        exp.abrir("primera contraseña")
    exp.abrir("segunda contraseña")
    assert exp.ficha(1)["diagnostico"] == SECRETO
    nuevo = exp.nuevo_codigo_recuperacion("segunda contraseña")
    exp.cerrar()
    with pytest.raises(privado.ErrorPrivado):
        exp.abrir(codigo=codigo)
    exp.abrir(codigo=nuevo)


def test_se_cierra_solo(tmp_path, monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(privado.time, "monotonic", lambda: reloj[0])
    exp = privado.Expediente(tmp_path / "p.mpx")
    exp.configurar("una contraseña larga")
    exp.ficha(1)
    reloj[0] += privado.MINUTOS_CIERRE * 60 - 5
    exp.ficha(1)  # el uso renueva el plazo
    reloj[0] += privado.MINUTOS_CIERRE * 60 - 5
    assert exp.abierto()
    reloj[0] += 10
    assert not exp.abierto()


def test_no_se_pueden_cambiar_datos_de_sitio(tmp_path):
    """Cada bloque cifrado va ligado a su alumno: copiar el de otro en la BD no se puede leer."""
    exp = privado.Expediente(tmp_path / "p.mpx")
    exp.configurar("una contraseña larga")
    exp.guardar_ficha(1, {"diagnostico": SECRETO})
    c = sqlite3.connect(str(tmp_path / "p.mpx"))
    c.execute("INSERT INTO fichas(alumno_id, datos) SELECT 2, datos FROM fichas WHERE alumno_id = 1")
    c.commit()
    c.close()
    with pytest.raises(Exception):
        exp.ficha(2)


# ------------------------------------------------------------------ API
def _app(tmp_path, monkeypatch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MUNDOPTAL_DOCUMENTOS", str(tmp_path / "docs"))
    s = Store(tmp_path / "m.db")
    uid = s.crear_usuario("Profe", "PT/AL")
    a = s.crear_alumno("Teo Prueba", usuario_id=uid)
    app = crear_app(tmp_path / "m.db")
    app.extensions["sin_abrir"] = True
    cli = app.test_client()
    cli.environ_base["HTTP_X_USUARIO"] = str(uid)
    return app, cli, uid, a


def test_api_completa(tmp_path, monkeypatch):
    app, cli, uid, a = _app(tmp_path, monkeypatch)
    assert cli.get("/api/privado/estado").json["configurado"] is False
    r = cli.post("/api/privado/configurar", json={"contrasena": "una contraseña larga"}).json
    t = {"X-Privado": r["testigo"]}
    # Sin el testigo de la ventana no se puede leer, aunque esté abierto
    assert cli.get(f"/api/privado/alumnos/{a}").status_code == 423
    assert cli.get(f"/api/privado/alumnos/{a}", headers={"X-Privado": "otro"}).status_code == 423
    assert cli.put(f"/api/privado/alumnos/{a}/ficha", json={"diagnostico": SECRETO}, headers=t).json["diagnostico"] == SECRETO
    r = cli.post(f"/api/privado/alumnos/{a}/documentos", headers=t, content_type="multipart/form-data",
                 data={"archivo": (io.BytesIO(PDF), "informe.pdf", "application/pdf"), "tipo": "psiquiatria",
                       "fecha": "2026-10-01", "profesional": "Gabinete Inventado"}).json
    did = r["ids"][0]
    datos = cli.get(f"/api/privado/alumnos/{a}", headers=t).json
    assert datos["documentos"][0]["profesional"] == "Gabinete Inventado" and datos["ficha"]["diagnostico"] == SECRETO
    ver = cli.get(f"/api/privado/documentos/{did}", headers=t)
    assert ver.data == PDF and ver.headers["Cache-Control"] == "no-store"
    assert cli.patch(f"/api/privado/documentos/{did}", json={"titulo": "Revisión"}, headers=t).json["titulo"] == "Revisión"
    fuera = cli.post(f"/api/privado/documentos/{did}/abrir", headers=t).json
    assert open(fuera["ruta"], "rb").read() == PDF
    assert cli.get("/api/privado/estado").json["documentos_por_alumno"] == {str(a): 1}

    # Nada de esto sale en la exportación normal de datos ni en la base de datos principal
    exportado = cli.get("/api/datos/exportar").data
    assert SECRETO.encode() not in exportado and b"Gabinete Inventado" not in exportado and PDF not in exportado
    assert SECRETO.encode() not in (tmp_path / "m.db").read_bytes()

    # Cerrar borra las copias temporales y exige otra vez la contraseña
    cli.post("/api/privado/cerrar")
    assert not (tmp_path / "privado" / "abiertos").exists()
    assert cli.get(f"/api/privado/alumnos/{a}", headers=t).status_code == 423
    assert cli.post("/api/privado/abrir", json={"contrasena": "mal"}).status_code == 400
    t = {"X-Privado": cli.post("/api/privado/abrir", json={"contrasena": "una contraseña larga"}).json["testigo"]}

    # Exportar el expediente (sigue cifrado) y llevarlo a «otro ordenador»
    mpx = cli.get("/api/privado/exportar", headers=t).data
    assert SECRETO.encode() not in mpx
    app2, cli2, _, a2 = _app(tmp_path / "otro", monkeypatch)
    assert cli2.post("/api/privado/importar", content_type="multipart/form-data",
                     data={"archivo": (io.BytesIO(mpx), "x.mpx"), "contrasena": "mal"}).status_code == 400
    r = cli2.post("/api/privado/importar", content_type="multipart/form-data",
                  data={"archivo": (io.BytesIO(mpx), "x.mpx"), "contrasena": "una contraseña larga"}).json
    assert cli2.get(f"/api/privado/alumnos/{a2}", headers={"X-Privado": r["testigo"]}).json["ficha"]["diagnostico"] == SECRETO

    # Borrar el documento y, al borrar al alumno, todo su expediente
    assert cli.delete(f"/api/privado/documentos/{did}", headers=t).json["ok"]
    cli.post(f"/api/privado/alumnos/{a}/documentos", headers=t, content_type="multipart/form-data",
             data={"archivo": (io.BytesIO(PDF), "otro.pdf", "application/pdf")})
    cli.delete(f"/api/alumnos/{a}")
    assert cli.get("/api/privado/estado").json["documentos_por_alumno"] == {}


def test_api_rechaza_otro_host_y_otro_perfil(tmp_path, monkeypatch):
    app, cli, uid, a = _app(tmp_path, monkeypatch)
    t = {"X-Privado": cli.post("/api/privado/configurar", json={"contrasena": "una contraseña larga"}).json["testigo"]}
    # Una web que llegue a la app con otro nombre (DNS rebinding) no pasa
    assert cli.get("/api/privado/estado", base_url="http://malo.example").status_code == 400
    # El alumno de otro perfil no se puede consultar desde este
    s = app.extensions["store"]
    otro = s.crear_usuario("Otra profe", "PT")
    b = s.crear_alumno("Ana Inventada", usuario_id=otro)
    assert cli.get(f"/api/privado/alumnos/{b}", headers=t).status_code == 400
    # Y cada perfil tiene su propio expediente y contraseña
    cli.environ_base["HTTP_X_USUARIO"] = str(otro)
    assert cli.get("/api/privado/estado").json["configurado"] is False


def test_rutas_genericas_y_mcp_no_llegan(tmp_path, monkeypatch):
    app, cli, uid, a = _app(tmp_path, monkeypatch)
    for tabla in ("fichas", "documentos", "clave"):
        assert cli.patch(f"/api/{tabla}/1", json={"x": 1}).status_code >= 400
    import mundoptal.mcp_server as m
    assert "privado" not in open(m.__file__, encoding="utf-8").read()
