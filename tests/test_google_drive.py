"""Material en Google Drive: inicio de sesión, subida convertida y alternativa sin conexión.
Nunca se llama a Google (HTTP falso), ni se abre el navegador, ni se usa el
Administrador de credenciales real (keyring en memoria)."""
import base64
import json
import urllib.parse

import keyring
import pytest

from mundoptal import google_drive
from mundoptal.servidor import crear_app
from tests.test_material import KeyringMemoria

CLIENTE = json.dumps({"installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-prueba"}})


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    anterior = keyring.get_keyring()
    keyring.set_keyring(KeyringMemoria())
    monkeypatch.setenv("MUNDOPTAL_DOCUMENTOS", str(tmp_path / "Documentos"))
    monkeypatch.delenv("MUNDOPTAL_GOOGLE_CLIENTE", raising=False)
    google_drive._TOKENS.clear()
    google_drive._PENDIENTES.clear()
    yield
    keyring.set_keyring(anterior)


class GoogleFalso:
    def __init__(self):
        self.llamadas = []
        self.carpetas = {}
        self.sin_red = False

    def __call__(self, metodo, url, datos=None, cabeceras=None, timeout=30):
        if self.sin_red:
            raise google_drive.ErrorDrive("No hay conexión con Google.")
        self.llamadas.append((metodo, url, datos, cabeceras or {}))
        if url == google_drive.URL_TOKEN:
            f = dict(urllib.parse.parse_qsl(datos.decode()))
            if f["grant_type"] == "authorization_code":
                assert f["code"] == "codigo-ok" and f["code_verifier"] and f["client_secret"] == "GOCSPX-prueba"
                carga = base64.urlsafe_b64encode(json.dumps({"email": "maestra@colegio.es"}).encode()).decode().rstrip("=")
                return {"access_token": "acc-1", "expires_in": 3600, "refresh_token": "ref-1", "id_token": f"x.{carga}.y"}
            assert f["refresh_token"] == "ref-1"
            return {"access_token": "acc-2", "expires_in": 3600}
        if url == google_drive.URL_REVOCAR:
            return {}
        assert cabeceras["Authorization"].startswith("Bearer acc-")
        if url.startswith(google_drive.URL_SUBIDA):
            assert b"application/vnd.google-apps." in datos and b"PK" in datos  # metadatos + .docx/.pptx (zip)
            n = len(self.llamadas)
            return {"id": f"doc{n}", "webViewLink": f"https://docs.google.com/document/d/doc{n}/edit"}
        if metodo == "POST":
            meta = json.loads(datos)
            assert meta == {"name": "material mundo pt/al", "mimeType": google_drive.MIME_CARPETA}
            cid = f"carpeta{len(self.carpetas) + 1}"
            self.carpetas[cid] = False
            return {"id": cid}
        cid = url.split("/files/")[1].split("?")[0]
        if cid not in self.carpetas:
            raise google_drive.ErrorHTTP(404, {"error": {"message": "File not found"}})
        return {"id": cid, "trashed": self.carpetas[cid]}


@pytest.fixture
def google(monkeypatch):
    falso = GoogleFalso()
    monkeypatch.setattr(google_drive, "_http", falso)
    return falso


def _app(tmp_path):
    app = crear_app(tmp_path / "m.db")
    abiertas = []
    app.extensions["abrir_web"] = abiertas.append
    app.extensions["sin_abrir"] = True
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra Prueba", "especialidad": "PT/AL"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    c.post("/api/material/ajustes", json={"pictos": False}, headers=h)
    return app, c, h, abiertas


def _crear(c, h, formato="docx"):
    p = c.post("/api/material/propuesta", json={"modo": "plantilla", "tipo": "numeros", "contenido": "1-3", "num": 2}, headers=h).get_json()
    return c.post("/api/material/crear", json={"spec": p["spec"], "formato": formato, "abrir": True}, headers=h).get_json()


def _conectar(c, h, abiertas):
    url = c.post("/api/google/conectar", headers=h).get_json()["url"]
    assert abiertas[-1] == url
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert q["scope"] == google_drive.ALCANCES and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"].startswith("http://127.0.0.1:")
    r = c.get(f"/?state={q['state']}&code=codigo-ok")
    assert "Conectado" in r.get_data(as_text=True)
    return q


def test_cliente_oauth_valida_y_no_va_a_la_base_de_datos(tmp_path):
    app, c, h, _ = _app(tmp_path)
    assert c.get("/api/google/estado", headers=h).get_json()["configurado"] is False
    assert c.post("/api/google/cliente", json={"texto": "{}"}, headers=h).status_code == 400
    assert c.post("/api/google/conectar", headers=h).status_code == 400
    assert c.post("/api/google/cliente", json={"texto": CLIENTE}, headers=h).status_code == 200
    e = c.get("/api/google/estado", headers=h).get_json()
    assert e["configurado"] and e["cliente_propio"] and not e["conectado"] and e["abrir_con"] == "drive"
    app.extensions["store"].conn.execute("PRAGMA wal_checkpoint(FULL)")
    for f in tmp_path.glob("m.db*"):
        assert b"GOCSPX" not in f.read_bytes()
    c.delete("/api/google/cliente", headers=h)
    assert c.get("/api/google/estado", headers=h).get_json()["configurado"] is False


def test_sin_conectar_se_abre_drive_para_subirlo_a_mano(tmp_path):
    _, c, h, abiertas = _app(tmp_path)
    r = _crear(c, h)
    assert r["manual"] is True and abiertas == [google_drive.URL_MI_UNIDAD]
    # Con «Word o PowerPoint» se abre en local (aquí no hay startfile) y no se abre el navegador
    c.post("/api/google/ajustes", json={"abrir_con": "local"}, headers=h)
    r = _crear(c, h)
    assert "manual" not in r and r["abierto"] is False and len(abiertas) == 1


def test_conectar_subir_convertido_y_reutilizar(tmp_path, google):
    app, c, h, abiertas = _app(tmp_path)
    c.post("/api/google/cliente", json={"texto": CLIENTE}, headers=h)
    _conectar(c, h, abiertas)
    e = c.get("/api/google/estado", headers=h).get_json()
    assert e["conectado"] and e["email"] == "maestra@colegio.es"
    assert google_drive._leer("google_token_1") == "ref-1"

    r = _crear(c, h, "docx")
    assert r["drive_url"].startswith("https://docs.google.com/") and abiertas[-1] == r["drive_url"]
    subida = [x for x in google.llamadas if x[1].startswith(google_drive.URL_SUBIDA)][-1]
    assert b'"parents": ["carpeta1"]' in subida[2] and b"vnd.google-apps.document" in subida[2]
    r2 = _crear(c, h, "pptx")
    subida = [x for x in google.llamadas if x[1].startswith(google_drive.URL_SUBIDA)][-1]
    assert b"vnd.google-apps.presentation" in subida[2] and b'"parents": ["carpeta1"]' in subida[2]
    assert len(google.carpetas) == 1  # la carpeta se crea una vez y se reutiliza

    # Abrir otra vez no vuelve a subir
    n = len(google.llamadas)
    a = c.post(f"/api/materiales/{r['id']}/abrir", headers=h).get_json()
    assert a["drive_url"] == r["drive_url"] and len(google.llamadas) == n and abiertas[-1] == r["drive_url"]
    lista = c.get("/api/materiales", headers=h).get_json()
    assert {m["drive_url"] for m in lista} == {r["drive_url"], r2["drive_url"]}

    # Si la carpeta va a la papelera, se crea otra
    google.carpetas["carpeta1"] = True
    _crear(c, h)
    assert "carpeta2" in google.carpetas
    assert app.extensions["store"].q1("SELECT valor FROM meta WHERE clave = 'drive.carpeta.1'")["valor"] == "carpeta2"


def test_sin_internet_se_avisa_y_el_archivo_queda(tmp_path, google):
    _, c, h, abiertas = _app(tmp_path)
    c.post("/api/google/cliente", json={"texto": CLIENTE}, headers=h)
    _conectar(c, h, abiertas)
    google_drive._TOKENS.clear()
    google.sin_red = True
    r = _crear(c, h)
    assert "conexión" in r["aviso"] and (tmp_path / "Documentos" / "Material" / r["nombre"]).exists()
    google.sin_red = False
    r2 = c.post(f"/api/materiales/{r['id']}/drive", headers=h).get_json()
    assert r2["drive_url"]


def test_estado_caducado_o_cancelado_y_desconectar(tmp_path, google):
    _, c, h, abiertas = _app(tmp_path)
    c.post("/api/google/cliente", json={"texto": CLIENTE}, headers=h)
    url = c.post("/api/google/conectar", headers=h).get_json()["url"]
    estado = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["state"]
    assert "cancelado" in c.get(f"/?state={estado}&error=access_denied").get_data(as_text=True)
    assert "<!doctype html>" in c.get(f"/?state={estado}&code=codigo-ok").get_data(as_text=True).lower()  # ya no vale: index normal
    assert not c.get("/api/google/estado", headers=h).get_json()["conectado"]
    _conectar(c, h, abiertas)
    c.post("/api/google/desconectar", headers=h)
    assert not c.get("/api/google/estado", headers=h).get_json()["conectado"]
    assert any(x[1] == google_drive.URL_REVOCAR for x in google.llamadas)


def test_migracion_anade_columnas_de_drive(tmp_path):
    import sqlite3

    from mundoptal import db
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript("""CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO meta VALUES ('schema_version', '11');
        CREATE TABLE materiales (id INTEGER PRIMARY KEY, usuario_id INTEGER, alumno_id INTEGER, titulo TEXT NOT NULL DEFAULT '',
          tipo TEXT NOT NULL DEFAULT '', origen TEXT NOT NULL DEFAULT 'plantilla', formato TEXT NOT NULL DEFAULT 'docx',
          paginas INTEGER NOT NULL DEFAULT 0, ruta TEXT NOT NULL DEFAULT '', creado TEXT);
        INSERT INTO materiales(titulo, ruta) VALUES ('Antiguo', 'x.docx');""")
    con.commit()
    con.close()
    conn = db.connect(ruta)
    fila = conn.execute("SELECT titulo, drive_id, drive_url FROM materiales").fetchone()
    assert tuple(fila) == ("Antiguo", "", "")
