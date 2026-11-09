"""API local (solo escucha en 127.0.0.1) que usa la interfaz de la aplicación."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import dictado
from .config import APP_NAME, APP_VERSION, COLEGIO, DIAS, ESCALA, ESCALA_TEXTO, data_dir, static_dir
from .planificador import Planificador, lunes_de
from .store import Store, StoreError
from .voz import Dictado
from .word import exportar_aci, importar_aci


def crear_app(db_path: str | Path) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
    store = Store(db_path)
    plan = Planificador(store)
    voz = Dictado()
    app.extensions["store"] = store

    def cuerpo() -> dict:
        return request.get_json(silent=True) or {}

    @app.errorhandler(StoreError)
    def _error_datos(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(RuntimeError)
    def _error_ejecucion(e):
        return jsonify(error=str(e)), 400

    # ------------------------------------------------------------ interfaz
    @app.get("/")
    def index():
        return send_from_directory(static_dir(), "index.html")

    @app.get("/static/<path:nombre>")
    def estaticos(nombre):
        return send_from_directory(static_dir(), nombre)

    @app.get("/api/info")
    def info():
        return jsonify(app=APP_NAME, version=APP_VERSION, colegio=COLEGIO, escala=ESCALA,
                       escala_texto=ESCALA_TEXTO, dias=DIAS, datos=str(Path(db_path).parent),
                       hoy=dt.date.today().isoformat())

    # ------------------------------------------------------------ alumnos
    @app.get("/api/alumnos")
    def alumnos():
        return jsonify(store.listar_alumnos(request.args.get("todos") == "1"))

    @app.post("/api/alumnos")
    def crear_alumno():
        d = cuerpo()
        return jsonify(id=store.crear_alumno(d.get("nombre", ""), d.get("curso", ""), d.get("observaciones", "")))

    @app.get("/api/alumnos/<int:id_>")
    def alumno(id_):
        al = store.obtener_alumno(id_)
        return (jsonify(al), 200) if al else (jsonify(error="No encontrado"), 404)

    # ------------------------------------------------------------ edición genérica
    @app.patch("/api/<tabla>/<int:id_>")
    def actualizar(tabla, id_):
        store.actualizar(tabla, id_, cuerpo())
        return jsonify(ok=True)

    @app.delete("/api/<tabla>/<int:id_>")
    def borrar(tabla, id_):
        store.borrar(tabla, id_)
        return jsonify(ok=True)

    @app.post("/api/<tabla>/<int:id_>/mover")
    def mover(tabla, id_):
        store.mover(tabla, id_, int(cuerpo().get("direccion", 1)))
        return jsonify(ok=True)

    @app.post("/api/<tabla>/<int:padre_id>/hijos")
    def crear_hijo(tabla, padre_id):
        return jsonify(id=store.crear_hijo(tabla, padre_id, cuerpo()))

    # ------------------------------------------------------------ ACIs
    @app.post("/api/alumnos/<int:alumno_id>/acis")
    def crear_aci(alumno_id):
        return jsonify(id=store.crear_aci(alumno_id, cuerpo()))

    @app.get("/api/acis/<int:aci_id>")
    def obtener_aci(aci_id):
        aci = store.obtener_aci(aci_id)
        return (jsonify(aci), 200) if aci else (jsonify(error="No encontrada"), 404)

    @app.post("/api/acis/<int:aci_id>/duplicar")
    def duplicar(aci_id):
        return jsonify(id=store.duplicar_aci(aci_id, bool(cuerpo().get("siguiente_trimestre", True))))

    @app.get("/api/acis/<int:aci_id>/word")
    def exportar(aci_id):
        aci = store.obtener_aci(aci_id)
        if not aci:
            return jsonify(error="No encontrada"), 404
        nombre = re.sub(r"[^\w\-]+", "_", f"ACI_{aci['alumno_nombre']}_{aci['trimestre']}T").strip("_")
        datos = exportar_aci(aci)
        if request.args.get("guardar") == "1":
            # Guardar directamente en Documentos (la ventana nativa no siempre permite descargas)
            destino = Path.home() / "Documents"
            if not destino.exists():
                destino = Path.home()
            destino = destino / "Mundo PT-AL"
            destino.mkdir(parents=True, exist_ok=True)
            ruta = destino / f"{nombre}.docx"
            ruta.write_bytes(datos)
            return jsonify(ruta=str(ruta))
        return Response(
            datos,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{nombre}.docx"'},
        )

    @app.post("/api/importar-word")
    def importar_word():
        f = request.files.get("archivo")
        if not f:
            raise StoreError("No se ha recibido ningún archivo")
        try:
            datos = importar_aci(f.read())
        except Exception as e:  # archivo dañado o con otro formato
            raise StoreError(f"No se pudo leer el documento: {e}") from None
        alumno_id = request.form.get("alumno_id", type=int)
        if not alumno_id:
            nombre = datos.get("alumno_nombre") or Path(f.filename or "Alumno").stem
            existente = next((a for a in store.listar_alumnos(True)
                              if a["nombre"].strip().lower() == nombre.strip().lower()), None)
            alumno_id = existente["id"] if existente else store.crear_alumno(nombre, datos.get("curso", ""))
        campos = {k: datos[k] for k in ("curso", "curso_escolar", "trimestre", "prof_area", "prof_ptal", "observaciones") if datos.get(k)}
        if datos.get("materia"):
            campos["materia"] = datos["materia"]
        aci_id = store.crear_aci(alumno_id, campos, con_adaptaciones=False)
        store.importar_arbol(aci_id, datos)
        return jsonify(id=aci_id, alumno_id=alumno_id)

    # ------------------------------------------------------------ dictado
    @app.post("/api/dictado/analizar")
    def analizar():
        return jsonify(dictado.analizar(cuerpo().get("texto", "")))

    @app.post("/api/acis/<int:aci_id>/dictado")
    def aplicar_dictado(aci_id):
        d = cuerpo()
        arbol = d.get("areas")
        if arbol is None:
            arbol = dictado.analizar(d.get("texto", ""))["areas"]
        return jsonify(store.fusionar_dictado(aci_id, arbol, d.get("contexto")))

    @app.get("/api/voz")
    def voz_estado():
        return jsonify(voz.estado())

    @app.post("/api/voz/iniciar")
    def voz_iniciar():
        return jsonify(voz.iniciar())

    @app.post("/api/voz/detener")
    def voz_detener():
        return jsonify(voz.detener())

    # ------------------------------------------------------------ horario y agenda
    @app.get("/api/franjas")
    def franjas():
        return jsonify(plan.listar_franjas())

    @app.post("/api/franjas")
    def crear_franja():
        return jsonify(id=plan.guardar_franja(cuerpo()))

    @app.put("/api/franjas/<int:id_>")
    def editar_franja(id_):
        return jsonify(id=plan.guardar_franja(cuerpo(), id_))

    @app.delete("/api/franjas/<int:id_>")
    def borrar_franja(id_):
        plan.borrar_franja(id_)
        return jsonify(ok=True)

    @app.post("/api/planificar")
    def planificar():
        d = cuerpo()
        desde = d.get("desde") or lunes_de(dt.date.today()).isoformat()
        hasta = d.get("hasta") or (dt.date.fromisoformat(desde) + dt.timedelta(days=4)).isoformat()
        return jsonify(plan.planificar(desde, hasta, bool(d.get("replanificar"))))

    @app.get("/api/agenda")
    def agenda():
        desde = request.args.get("desde") or lunes_de(dt.date.today()).isoformat()
        hasta = request.args.get("hasta") or (dt.date.fromisoformat(desde) + dt.timedelta(days=4)).isoformat()
        return jsonify(desde=desde, hasta=hasta, sesiones=plan.agenda(desde, hasta))

    @app.get("/api/alumnos/<int:alumno_id>/pendientes")
    def pendientes(alumno_id):
        return jsonify(plan.items_pendientes(alumno_id))

    @app.patch("/api/sesiones/<int:id_>")
    def editar_sesion(id_):
        plan.actualizar_sesion(id_, cuerpo())
        return jsonify(ok=True)

    @app.delete("/api/sesiones/<int:id_>")
    def borrar_sesion(id_):
        plan.borrar_sesion(id_)
        return jsonify(ok=True)

    @app.patch("/api/sesiones/<int:sesion_id>/items/<int:item_id>")
    def marcar_item(sesion_id, item_id):
        d = cuerpo()
        plan.marcar_item(sesion_id, item_id, d.get("trabajado"), d.get("evaluacion"))
        return jsonify(ok=True)

    @app.delete("/api/sesiones/<int:sesion_id>/items/<int:item_id>")
    def quitar_item(sesion_id, item_id):
        plan.quitar_item(sesion_id, item_id)
        return jsonify(ok=True)

    # ------------------------------------------------------------ copia de seguridad
    @app.post("/api/copia-seguridad")
    def copia():
        destino = data_dir() / "copias"
        destino.mkdir(exist_ok=True)
        ruta = destino / f"mundo_ptal_{dt.datetime.now():%Y%m%d_%H%M%S}.db"
        destino_db = sqlite3.connect(str(ruta))
        with store.lock:
            store.conn.backup(destino_db)
        destino_db.close()
        return jsonify(ruta=str(ruta))

    return app
