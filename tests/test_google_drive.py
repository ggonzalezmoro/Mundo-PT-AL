"""Material en Google Drive sin API (Drive para ordenadores o arrastrar) y petición a Claude Desktop.
Nunca se abre el navegador, el Explorador ni Claude Desktop, ni se usa Internet."""
import urllib.parse

import keyring
import pytest

from mundoptal import claude_desktop, google_drive
from mundoptal.servidor import crear_app
from tests.test_material import KeyringMemoria


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    anterior = keyring.get_keyring()
    keyring.set_keyring(KeyringMemoria())
    monkeypatch.setenv("MUNDOPTAL_DOCUMENTOS", str(tmp_path / "Documentos"))
    monkeypatch.setenv("MUNDOPTAL_MI_UNIDAD", "")
    monkeypatch.setenv("MUNDOPTAL_CLAUDE_CONFIG", str(tmp_path / "claude" / "claude_desktop_config.json"))
    yield
    keyring.set_keyring(anterior)


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


def test_sin_drive_para_ordenadores_se_abre_drive_para_arrastrarlo(tmp_path):
    _, c, h, abiertas = _app(tmp_path)
    r = _crear(c, h)
    assert r["manual"] is True and abiertas == [google_drive.URL_MI_UNIDAD]
    # Con el enlace de la carpeta guardado, se abre esa carpeta
    url = "https://drive.google.com/drive/folders/abc123"
    assert c.post("/api/google/ajustes", json={"carpeta_url": "https://ejemplo.com/x"}, headers=h).status_code == 400
    c.post("/api/google/ajustes", json={"carpeta_url": url}, headers=h)
    c.post(f"/api/materiales/{r['id']}/abrir", headers=h)
    assert abiertas[-1] == url
    # Con «Word o PowerPoint» se abre en local y no se abre el navegador
    c.post("/api/google/ajustes", json={"abrir_con": "local"}, headers=h)
    r = _crear(c, h)
    assert "manual" not in r and r["abierto"] is False and len(abiertas) == 2
    # «☁ Drive» fuerza Google aunque el ajuste sea local
    assert c.post(f"/api/materiales/{r['id']}/drive", headers=h).get_json()["manual"] is True


def test_con_drive_para_ordenadores_se_copia_a_la_carpeta_existente(tmp_path, monkeypatch):
    unidad = tmp_path / "G" / "Mi unidad"
    existente = unidad / "cuenta personal" / "Material Mundo PT_AL"
    existente.mkdir(parents=True)
    monkeypatch.setenv("MUNDOPTAL_MI_UNIDAD", str(unidad))
    _, c, h, abiertas = _app(tmp_path)
    e = c.get("/api/google/estado", headers=h).get_json()
    assert e["mi_unidad"] == str(unidad) and e["abrir_con"] == "drive"
    r = _crear(c, h, "pptx")
    assert r["sincronizado"] and (existente / r["nombre"]).exists()
    assert abiertas[-1].startswith("https://drive.google.com/drive/search?q=")
    assert urllib.parse.unquote(abiertas[-1].split("q=")[1]) == r["nombre"].rsplit(".", 1)[0]


def test_se_crea_la_carpeta_si_no_existe(tmp_path):
    unidad = tmp_path / "Mi unidad"
    unidad.mkdir()
    destino = google_drive.copiar_a_drive(_archivo(tmp_path), unidad)
    assert destino.parent == unidad / google_drive.NOMBRE_CARPETA and destino.exists()


def _archivo(tmp_path):
    f = tmp_path / "ficha.docx"
    f.write_bytes(b"PK prueba")
    return f


def test_mi_unidad_manual(tmp_path):
    _, c, h, _ = _app(tmp_path)
    assert c.post("/api/google/ajustes", json={"mi_unidad": str(tmp_path / "no-existe")}, headers=h).status_code == 400
    otra = tmp_path / "Drive" / "Mi unidad"
    otra.mkdir(parents=True)
    c.post("/api/google/ajustes", json={"mi_unidad": str(otra)}, headers=h)
    assert c.get("/api/google/estado", headers=h).get_json()["mi_unidad"] == str(otra)


def test_peticion_a_claude_desktop_sin_nombres(tmp_path):
    app, c, h, _ = _app(tmp_path)
    al = c.post("/api/alumnos", json={"nombre": "Alumna Prueba"}, headers=h).get_json()["id"]
    assert c.post("/api/material/claude-desktop", json={"peticion": " "}, headers=h).status_code == 400
    r = c.post("/api/material/claude-desktop", json={"peticion": "Fichas del fonema /r/ para Alumna", "alumno_id": al,
                                                     "nivel": "5", "formato": "pptx", "num": 6}, headers=h).get_json()
    assert "Alumna" not in r["texto"] and "el alumno" in r["texto"] and r["anonimizados"]
    assert "5 años" in r["texto"] and "PowerPoint" in r["texto"] and "6" in r["texto"] and "crear_material" in r["texto"]
    assert r["abierto"] is False and r["ultimo_id"] == 0
    url = claude_desktop.url_nuevo_chat(r["texto"])
    assert url.startswith("claude://claude.ai/new?q=") and urllib.parse.unquote(url.split("q=", 1)[1]) == r["texto"]
    assert c.get("/api/material/info", headers=h).get_json()["claude_desktop"] is False
    claude_desktop.configurar()
    assert c.get("/api/material/info", headers=h).get_json()["claude_desktop"] is True


def test_chrome_o_navegador_predeterminado(tmp_path, monkeypatch):
    exe = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432"):
        monkeypatch.delenv(var, raising=False)
    assert google_drive.chrome() == exe
    lanzados = []
    monkeypatch.setattr(google_drive.subprocess, "Popen", lambda args, **k: lanzados.append(args))
    assert google_drive.abrir_navegador("https://drive.google.com/") == "chrome" and lanzados[0][1] == "https://drive.google.com/"


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
