"""API local (solo escucha en 127.0.0.1) que usa la interfaz de la aplicación."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import dictado, horario, informes
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

    def usuario_actual() -> int | None:
        """Perfil activo, enviado por la interfaz en la cabecera X-Usuario.
        Si todavía no hay perfiles, se trabaja sin filtrar (compatibilidad)."""
        valor = request.headers.get("X-Usuario", "")
        if valor.isdigit() and store.obtener_usuario(int(valor)):
            return int(valor)
        usuarios = store.listar_usuarios()
        if not usuarios:
            return None
        if len(usuarios) == 1:
            return usuarios[0]["id"]
        raise StoreError("Elige primero tu perfil")

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

    # ------------------------------------------------------------ perfiles
    @app.get("/api/usuarios")
    def usuarios():
        return jsonify(store.listar_usuarios())

    @app.post("/api/usuarios")
    def crear_usuario():
        d = cuerpo()
        return jsonify(id=store.crear_usuario(d.get("nombre", ""), d.get("especialidad", "PT/AL")))

    # ------------------------------------------------------------ alumnos
    @app.get("/api/alumnos")
    def alumnos():
        return jsonify(store.listar_alumnos(usuario_actual(), request.args.get("todos") == "1"))

    @app.post("/api/alumnos")
    def crear_alumno():
        d = cuerpo()
        return jsonify(id=store.crear_alumno(d.get("nombre", ""), d.get("curso", ""), d.get("observaciones", ""),
                                             usuario_actual()))

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
        # Si ya está redactado el informe para la familia de ese trimestre, va en «Observaciones y comentarios»
        fila = store.q1("""SELECT id FROM informes WHERE alumno_id = ? AND trimestre = ?
                           AND (curso_escolar = ? OR ? = '') ORDER BY id DESC LIMIT 1""",
                        (aci["alumno_id"], aci["trimestre"], aci["curso_escolar"], aci["curso_escolar"]))
        if fila:
            inf = informes.obtener(store, fila["id"])
            textos = informes.parrafos(inf)
            if textos:
                previas = [x.strip() for x in (aci.get("observaciones") or "").split("\n") if x.strip()]
                aci["observaciones_familia"] = previas + textos
                aci["despedida_familia"] = (inf.get("despedida") or "").strip()
        nombre = re.sub(r"[^\w\-]+", "_", f"ACI_{aci['alumno_nombre']}_{aci['trimestre']}T").strip("_")
        return enviar_docx(nombre, exportar_aci(aci))

    def enviar_docx(nombre, datos):
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

    # ------------------------------------------------------------ informes a familias
    @app.get("/api/informes")
    def informes_resumen():
        return jsonify(alumnos=informes.resumen_usuario(store, usuario_actual()),
                       trimestre=informes.trimestre_actual(), curso_escolar=informes.curso_escolar_actual())

    @app.get("/api/alumnos/<int:alumno_id>/informes")
    def informes_alumno(alumno_id):
        return jsonify(informes.listar(store, alumno_id))

    @app.post("/api/alumnos/<int:alumno_id>/informes")
    def crear_informe(alumno_id):
        datos = cuerpo()
        uid = usuario_actual()
        u = store.obtener_usuario(uid) if uid else None
        return jsonify(id=informes.crear(store, alumno_id, datos.get("trimestre"), datos.get("curso_escolar"),
                                         maestra=(u or {}).get("nombre", "")))

    @app.get("/api/informes/<int:informe_id>")
    def obtener_informe(informe_id):
        inf = informes.obtener(store, informe_id)
        return (jsonify(inf), 200) if inf else (jsonify(error="No encontrado"), 404)

    @app.post("/api/informes/<int:informe_id>/areas")
    def informe_area(informe_id):
        return jsonify(id=informes.anadir_area(store, informe_id, cuerpo().get("area", "")))

    @app.post("/api/informes/<int:informe_id>/rehacer")
    def informe_rehacer(informe_id):
        informes.rehacer_areas(store, informe_id)
        return jsonify(ok=True)

    @app.get("/api/informes/<int:informe_id>/word")
    def informe_word(informe_id):
        inf = informes.obtener(store, informe_id)
        if not inf:
            return jsonify(error="No encontrado"), 404
        return enviar_docx(informes.nombre_archivo(inf), informes.exportar_word(inf))

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
            uid = usuario_actual()
            nombre = datos.get("alumno_nombre") or Path(f.filename or "Alumno").stem
            existente = store.buscar_alumno(nombre, uid)
            alumno_id = existente["id"] if existente else store.crear_alumno(nombre, datos.get("curso", ""), usuario_id=uid)
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
        return jsonify(plan.listar_franjas(usuario_actual()))

    @app.post("/api/franjas")
    def crear_franja():
        return jsonify(id=plan.guardar_franja(cuerpo(), usuario_id=usuario_actual()))

    @app.put("/api/franjas/<int:id_>")
    def editar_franja(id_):
        return jsonify(id=plan.guardar_franja(cuerpo(), id_, usuario_id=usuario_actual()))

    @app.post("/api/horario/importar")
    def importar_horario():
        f = request.files.get("archivo")
        if not f:
            raise StoreError("No se ha recibido ningún archivo")
        uid = usuario_actual()
        if uid is None:
            raise StoreError("Crea primero tu perfil para importar el horario")
        franjas_leidas = horario.analizar_tabla(horario.leer_tabla(f.filename or "", f.read()))
        return jsonify(horario.importar_horario(store, plan, uid, franjas_leidas,
                                                request.form.get("reemplazar") == "1"))

    @app.delete("/api/franjas/<int:id_>")
    def borrar_franja(id_):
        plan.borrar_franja(id_)
        return jsonify(ok=True)

    @app.post("/api/planificar")
    def planificar():
        d = cuerpo()
        desde = d.get("desde") or lunes_de(dt.date.today()).isoformat()
        hasta = d.get("hasta") or (dt.date.fromisoformat(desde) + dt.timedelta(days=4)).isoformat()
        return jsonify(plan.planificar(desde, hasta, bool(d.get("replanificar")), usuario_actual()))

    @app.get("/api/agenda")
    def agenda():
        desde = request.args.get("desde") or lunes_de(dt.date.today()).isoformat()
        hasta = request.args.get("hasta") or (dt.date.fromisoformat(desde) + dt.timedelta(days=4)).isoformat()
        return jsonify(desde=desde, hasta=hasta, sesiones=plan.agenda(desde, hasta, usuario_actual()))

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
