import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import pytest

from mundoptal import actualizador
from mundoptal.servidor import crear_app


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def falso_github(datos=None, codigo=None):
    def abrir(url, timeout=10):
        if codigo:
            raise urllib.error.HTTPError(url, codigo, "x", {}, None)
        return Respuesta(json.dumps(datos).encode())
    return abrir


def test_versiones():
    assert actualizador.es_mas_nueva("v0.4.0", "0.3.0")
    assert actualizador.es_mas_nueva("v0.10.0", "0.9.9")
    assert not actualizador.es_mas_nueva("v0.3.0", "0.3.0")
    assert not actualizador.es_mas_nueva("v0.2.9", "0.3.0")


def test_comprobar(monkeypatch):
    monkeypatch.setattr(actualizador, "APP_VERSION", "0.3.0")
    zip_url = "https://github.com/x/y/releases/download/v0.4.0/MundoPTAL-windows.zip"
    r = actualizador.comprobar(falso_github({
        "tag_name": "v0.4.0", "body": "Novedades", "published_at": "2026-11-12T10:00:00Z",
        "assets": [{"name": "otro.txt", "browser_download_url": "https://github.com/a"},
                   {"name": "MundoPTAL-windows.zip", "browser_download_url": zip_url}]}))
    assert r["hay_nueva"] and r["ultima"] == "0.4.0" and r["url"] == zip_url and r["fecha"] == "2026-11-12"
    # Sin el .zip todavía (la versión se está construyendo) no se ofrece
    assert not actualizador.comprobar(falso_github({"tag_name": "v0.4.0", "assets": []}))["hay_nueva"]
    with pytest.raises(actualizador.ErrorActualizacion, match="ninguna versión"):
        actualizador.comprobar(falso_github(codigo=404))


def test_guion_reemplazo():
    g = actualizador.guion_reemplazo(1234, Path("C:/t/nuevo/MundoPTAL"), Path("C:/Programa"), Path("C:/t"))
    assert 'PID eq 1234' in g and "robocopy" in g and "/MIR" not in g and "MundoPTAL.exe" in g


def test_instalar_solo_en_windows():
    with pytest.raises(actualizador.ErrorActualizacion):
        actualizador.instalar("https://github.com/x.zip")


def test_exportar_e_importar_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNDOPTAL_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    origen = crear_app(tmp_path / "a.db").test_client()
    origen.post("/api/usuarios", json={"nombre": "Profe", "especialidad": "PT/AL"})
    origen.post("/api/alumnos", json={"nombre": "Ana"})
    r = origen.get("/api/datos/exportar")
    assert r.status_code == 200 and r.data[:15] == b"SQLite format 3"
    guardado = origen.get("/api/datos/exportar?guardar=1").get_json()["ruta"]
    assert Path(guardado).exists() and "Mundo PT-AL" in guardado

    destino = crear_app(tmp_path / "b.db").test_client()
    destino.post("/api/alumnos", json={"nombre": "Se perderá"})
    malo = destino.post("/api/datos/importar", content_type="multipart/form-data",
                        data={"archivo": (io.BytesIO(b"no es una base de datos"), "x.db")})
    assert malo.status_code == 400
    ok = destino.post("/api/datos/importar", content_type="multipart/form-data",
                      data={"archivo": (io.BytesIO(r.data), "datos.db")}).get_json()
    assert ok["usuarios"] == 1 and ok["alumnos"] == 1 and Path(ok["copia_previa"]).exists()
    assert [a["nombre"] for a in destino.get("/api/alumnos").get_json()] == ["Ana"]


def test_importar_datos_de_version_antigua(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNDOPTAL_DATA_DIR", str(tmp_path / "datos"))
    viejo = tmp_path / "v1.db"
    con = sqlite3.connect(viejo)
    con.executescript("""
        CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE alumnos (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, curso TEXT DEFAULT '',
            observaciones TEXT DEFAULT '', activo INTEGER NOT NULL DEFAULT 1, creado TEXT);
        INSERT INTO alumnos(nombre) VALUES ('Antiguo');
    """)
    con.close()
    c = crear_app(tmp_path / "b.db").test_client()
    r = c.post("/api/datos/importar", content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(viejo.read_bytes()), "v1.db")})
    assert r.status_code == 200, r.get_json()
    assert [a["nombre"] for a in c.get("/api/alumnos").get_json()] == ["Antiguo"]
    assert c.get("/api/informes").status_code == 200  # las tablas nuevas existen


def test_guion_aparta_bloqueados_sin_cerrar_procesos():
    g = actualizador.guion_reemplazo(1234, Path("C:/t/nuevo/MundoPTAL"), Path("C:/Programa"), Path("C:/t"))
    # primero espera a la app, luego aparta lo que está en uso y después copia;
    # si la copia falla, restaura los archivos apartados
    assert g.index("PID eq 1234") < g.index("-Modo apartar") < g.index("robocopy") < g.index("-Modo restaurar")
    assert "\r\r\n" not in g
    ps = actualizador.guion_apartar(Path("C:/t/nuevo/MundoPTAL"), Path("C:/Mi carpeta/O'Neil/MundoPTAL"), "1")
    assert "O''Neil" in ps and "Rename-Item" in ps
    # no se cierra ningún proceso: el servidor de Claude Desktop (--mcp) sigue funcionando
    for orden in ("Stop-Process", "taskkill", "kill"):
        assert orden not in ps and orden not in g


def test_limpiar_restos(tmp_path):
    (tmp_path / "_internal").mkdir()
    (tmp_path / "MundoPTAL.exe").write_text("nuevo")
    (tmp_path / "MundoPTAL.exe.viejo-20261123").write_text("viejo")
    (tmp_path / "_internal" / "python312.dll.viejo-20261123").write_text("viejo")
    assert actualizador.limpiar_restos(tmp_path) == 2
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["MundoPTAL.exe"]


@pytest.mark.skipif(sys.platform != "win32", reason="solo en Windows")
def test_apartar_en_uso_y_restaurar_en_windows(tmp_path):
    """Con un programa de verdad en marcha: se aparta sin cerrarlo y se puede restaurar."""
    origen, destino = tmp_path / "nuevo", tmp_path / "programa"
    origen.mkdir(), destino.mkdir()
    ping = Path(os.environ["WINDIR"]) / "System32" / "PING.EXE"
    shutil.copy(ping, destino / "MundoPTAL.exe")
    shutil.copy(ping, origen / "MundoPTAL.exe")
    (destino / "libre.txt").write_text("viejo")
    (origen / "libre.txt").write_text("nuevo")
    guion = tmp_path / "apartar.ps1"
    guion.write_text(actualizador.guion_apartar(origen, destino, "1"), encoding="utf-8-sig", newline="")

    def ejecutar(modo):
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(guion),
                        "-Modo", modo], check=True, capture_output=True, timeout=60)

    en_uso = subprocess.Popen([str(destino / "MundoPTAL.exe"), "-n", "30", "127.0.0.1"],
                              stdout=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        ejecutar("apartar")
        assert (destino / "MundoPTAL.exe.viejo-1").exists() and not (destino / "MundoPTAL.exe").exists()
        assert (destino / "libre.txt").exists()  # lo que no está en uso no se toca
        assert en_uso.poll() is None  # sigue funcionando
        ejecutar("restaurar")  # p. ej. si robocopy hubiera fallado
        assert (destino / "MundoPTAL.exe").exists() and not (destino / "MundoPTAL.exe.viejo-1").exists()
    finally:
        en_uso.kill()
        en_uso.wait()
