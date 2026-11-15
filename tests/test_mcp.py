"""Servidor MCP para Claude Desktop y alta en claude_desktop_config.json.

Datos sintéticos (nunca alumnos reales), sin Internet (pictogramas desactivados), sin el
Administrador de credenciales real y sin tocar el claude_desktop_config.json real: todo
va a carpetas temporales. Las pruebas del protocolo MCP (cliente de prueba de `mcp`) se
saltan si el paquete `mcp` no está instalado en el entorno."""
import asyncio
import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from docx import Document
from pptx import Presentation

from mundoptal import claude_desktop, dictado, mcp_server
from mundoptal.material import plantilla
from mundoptal.servidor import crear_app

NOMBRES = ["Zacarías Pruebatest", "Wenceslao Ficticio"]  # inventados, para comprobar que nunca salen


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNDOPTAL_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("MUNDOPTAL_DOCUMENTOS", str(tmp_path / "Documentos"))
    monkeypatch.setenv("MUNDOPTAL_CLAUDE_CONFIG", str(tmp_path / "Claude" / "claude_desktop_config.json"))


@pytest.fixture
def datos(tmp_path):
    """Base de datos con un perfil, dos alumnos con ACI y pictogramas desactivados (sin red)."""
    ruta = tmp_path / "datos" / "mundo_ptal.db"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    app = crear_app(ruta)
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra Prueba", "especialidad": "PT/AL"}).get_json()["id"]
    h = {"X-Usuario": str(uid)}
    c.post("/api/material/ajustes", json={"pictos": False}, headers=h)
    store = app.extensions["store"]
    for n in NOMBRES:
        al = store.crear_alumno(n, "4 años", usuario_id=uid)
        aci = store.crear_aci(al, {"trimestre": 1})
        arbol = dictado.analizar(f"Área comunicación. Competencia atención. Ítem {n.split()[0]} mira a los ojos. "
                                 "Ítem nombra colores. Ítem señala animales.")
        store.fusionar_dictado(aci, arbol["areas"])
    store.conn.execute("PRAGMA wal_checkpoint(FULL)")
    return {"ruta": ruta, "app": app, "c": c, "h": h, "uid": uid}


def _spec():
    return plantilla("letras", "vocales", "4", 3).model_dump()


# ------------------------------------------------------------------ herramientas (sin el SDK de MCP)
def test_plantillas_y_esquema(datos):
    h = mcp_server.Herramientas(datos["ruta"])
    p = h.listar_plantillas()
    assert "rodear" in p["actividades"] and any(x["tipo"] == "letras" for x in p["plantillas"])
    esquema = h.esquema_material()
    assert esquema["title"] == "MaterialSpec" and "paginas" in esquema["properties"]


@pytest.mark.parametrize("formato", ["docx", "pptx"])
def test_crear_material_valido_y_registrado(datos, formato):
    h = mcp_server.Herramientas(datos["ruta"])
    r = h.crear_material(_spec(), formato, "Vocales para 4 años")
    ruta = Path(r["ruta"])
    assert ruta.exists() and ruta.suffix == "." + formato and "Vocales_para_4_a" in ruta.name
    assert ruta.parent == Path(os.environ["MUNDOPTAL_DOCUMENTOS"]) / "Material"
    if formato == "docx":
        assert len(Document(io.BytesIO(ruta.read_bytes())).paragraphs) > 3
    else:
        assert len(Presentation(io.BytesIO(ruta.read_bytes())).slides) == 3
    assert r["resumen"]["paginas"] == 3
    mats = datos["c"].get("/api/materiales", headers=datos["h"]).get_json()
    assert mats[0]["ruta"] == str(ruta) and mats[0]["origen"] == "claude_desktop" and mats[0]["usuario_id"] == datos["uid"]
    assert h.listar_materiales(5)[0]["archivo"] == ruta.name


def test_crear_desde_plantilla_y_errores(datos):
    h = mcp_server.Herramientas(datos["ruta"])
    r = h.crear_desde_plantilla("numeros", {"contenido": "1-3", "nivel": "3"}, "pptx")
    assert Path(r["ruta"]).exists()
    with pytest.raises(mcp_server.ErrorMCP):
        h.crear_desde_plantilla("no_existe", {})
    with pytest.raises(mcp_server.ErrorMCP):
        h.crear_material({"titulo": "x"}, "docx")
    with pytest.raises(mcp_server.ErrorMCP):
        h.crear_material(_spec(), "pdf")
    with pytest.raises(mcp_server.ErrorMCP):
        mcp_server.Herramientas(datos["ruta"].parent / "no_hay.db").listar_materiales()


def test_alumnos_desactivado_por_defecto_y_sin_nombres(datos):
    h = mcp_server.Herramientas(datos["ruta"])
    with pytest.raises(mcp_server.ErrorMCP, match="activado"):
        h.listar_alumnos()
    with pytest.raises(mcp_server.ErrorMCP):
        h.objetivos_alumno("Alumno 1")
    assert datos["c"].get("/api/claude-desktop", headers=datos["h"]).get_json()["alumnos"] is False
    datos["c"].post("/api/claude-desktop/ajustes", json={"alumnos": True}, headers=datos["h"])
    lista = h.listar_alumnos()
    assert lista == [{"alumno": "Alumno 1", "objetivos_pendientes": 3}, {"alumno": "Alumno 2", "objetivos_pendientes": 3}]
    obj = h.objetivos_alumno("Alumno 2")
    assert obj["alumno"] == "Alumno 2" and "nombra colores" in " ".join(obj["objetivos"]).lower()
    assert h.objetivos_alumno(1)["alumno"] == "Alumno 1"
    todo = json.dumps([lista, obj, h.objetivos_alumno("1"), h.listar_materiales()], ensure_ascii=False)
    for n in NOMBRES:
        for parte in n.split():
            assert parte not in todo
    with pytest.raises(mcp_server.ErrorMCP):
        h.objetivos_alumno("Alumno 9")


def test_bd_en_solo_lectura_y_perfil(datos):
    h = mcp_server.Herramientas(datos["ruta"])
    with h._leer() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM alumnos")
        assert h.perfil(conn) == datos["uid"]
    otro = datos["c"].post("/api/usuarios", json={"nombre": "Otra Maestra", "especialidad": "AL"}).get_json()["id"]
    datos["c"].get("/api/alumnos", headers={"X-Usuario": str(otro)})  # la app recuerda el último perfil usado
    with h._leer() as conn:
        assert h.perfil(conn) == otro
    with mcp_server.Herramientas(datos["ruta"], "maestra prueba")._leer() as conn:
        assert mcp_server.Herramientas(datos["ruta"], "maestra prueba").perfil(conn) == datos["uid"]
    with pytest.raises(mcp_server.ErrorMCP):
        with h._leer() as conn:
            mcp_server.Herramientas(datos["ruta"], "Nadie").perfil(conn)


# ------------------------------------------------------------------ claude_desktop_config.json
def test_config_fusiona_sin_perder_entradas_y_hace_copia(tmp_path):
    ruta = tmp_path / "Claude" / "claude_desktop_config.json"
    ruta.parent.mkdir()
    original = {"mcpServers": {"otro": {"command": "npx", "args": ["algo"]}, "mundo-ptal": {"command": "viejo.exe"}},
                "globalShortcut": "Ctrl+Space", "preferencias": {"tema": "oscuro"}}
    ruta.write_text(json.dumps(original), encoding="utf-8")
    r = claude_desktop.configurar(ruta)
    nuevo = json.loads(ruta.read_text(encoding="utf-8"))
    assert nuevo["mcpServers"]["otro"] == original["mcpServers"]["otro"]
    assert nuevo["globalShortcut"] == "Ctrl+Space" and nuevo["preferencias"] == {"tema": "oscuro"}
    assert nuevo["mcpServers"]["mundo-ptal"] == claude_desktop.entrada()
    assert json.loads(Path(r["copia"]).read_text(encoding="utf-8")) == original  # copia previa intacta
    assert claude_desktop.estado(ruta)["al_dia"]
    # Sin archivo previo: se crea, sin copia
    vacio = tmp_path / "nuevo" / "claude_desktop_config.json"
    assert claude_desktop.configurar(vacio)["copia"] == "" and "mundo-ptal" in json.loads(vacio.read_text(encoding="utf-8"))["mcpServers"]


def test_config_con_error_no_se_toca(tmp_path):
    from mundoptal.store import StoreError
    ruta = tmp_path / "claude_desktop_config.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    with pytest.raises(StoreError):
        claude_desktop.configurar(ruta)
    assert ruta.read_text(encoding="utf-8") == "{ esto no es json"


def test_config_por_la_api_va_a_la_ruta_temporal(datos, tmp_path):
    e = datos["c"].get("/api/claude-desktop", headers=datos["h"]).get_json()
    assert e["ruta"] == str(tmp_path / "Claude" / "claude_desktop_config.json") and not e["configurado"]
    assert json.loads(e["fragmento"])["mcpServers"]["mundo-ptal"]["args"][-1] in ("--mcp", "mundoptal.mcp_server")
    datos["c"].post("/api/claude-desktop/configurar", headers=datos["h"])
    assert datos["c"].get("/api/claude-desktop", headers=datos["h"]).get_json()["al_dia"]


def test_modo_mcp_no_abre_ventana(monkeypatch):
    from mundoptal import __main__ as principal
    llamado = {}
    monkeypatch.setattr(mcp_server, "main", lambda argv: llamado.setdefault("argv", argv) and 0)
    monkeypatch.setitem(sys.modules, "webview", None)  # si se intentara importar la ventana, fallaría
    principal.main(["--mcp", "--perfil", "2"])
    assert llamado["argv"] == ["--perfil", "2"]


# ------------------------------------------------------------------ protocolo MCP (requiere el paquete mcp)
def test_servidor_mcp_en_proceso(datos):
    pytest.importorskip("mcp")
    from mcp.shared.memory import create_connected_server_and_client_session

    servidor = mcp_server.crear_servidor(mcp_server.Herramientas(datos["ruta"]))

    async def probar():
        async with create_connected_server_and_client_session(servidor._mcp_server) as cliente:
            nombres = {t.name for t in (await cliente.list_tools()).tools}
            assert nombres == {"listar_plantillas", "esquema_material", "crear_material", "crear_desde_plantilla",
                               "listar_alumnos", "objetivos_alumno", "listar_materiales"}
            r = await cliente.call_tool("crear_material", {"spec": _spec(), "formato": "docx", "titulo_archivo": "Prueba MCP"})
            assert not r.isError
            datos_r = json.loads(r.content[0].text)
            assert Path(datos_r["ruta"]).exists()
            r = await cliente.call_tool("listar_alumnos", {})
            assert r.isError and "activado" in r.content[0].text
    asyncio.run(probar())


def test_arranque_por_stdio(datos):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    entorno = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
    params = StdioServerParameters(command=sys.executable, args=["-m", "mundoptal.mcp_server"], env=entorno)

    async def probar():
        async with stdio_client(params) as (leer, escribir):
            async with ClientSession(leer, escribir) as s:
                ini = await s.initialize()
                assert ini.serverInfo.name == "mundo-ptal" and "PT/AL" in (ini.instructions or "")
                assert len((await s.list_tools()).tools) == 7
    asyncio.run(asyncio.wait_for(probar(), 60))
