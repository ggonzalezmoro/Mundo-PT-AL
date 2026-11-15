"""API local (solo escucha en 127.0.0.1) que usa la interfaz de la aplicación."""
from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import (actualizador, biblioteca, calendario, claude_desktop, db as basedatos, dictado, horario, ia_material, informes,
               maqueta, material, mcp_server, trabajo)
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

    ultimo = {"perfil": None}

    def recordar_perfil(uid: int) -> None:
        """Último perfil usado (lo usa el servidor MCP de Claude Desktop si no se le indica otro).
        Solo se escribe cuando cambia."""
        if ultimo["perfil"] == uid:
            return
        ultimo["perfil"] = uid
        with store.tx() as c:
            c.execute("INSERT INTO meta(clave, valor) VALUES ('ultimo_perfil', ?) "
                      "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (str(uid),))

    def usuario_actual() -> int | None:
        """Perfil activo, enviado por la interfaz en la cabecera X-Usuario.
        Si todavía no hay perfiles, se trabaja sin filtrar (compatibilidad)."""
        valor = request.headers.get("X-Usuario", "")
        if valor.isdigit() and store.obtener_usuario(int(valor)):
            recordar_perfil(int(valor))
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

    @app.errorhandler(actualizador.ErrorActualizacion)
    def _error_actualizacion(e):
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

    # ------------------------------------------------------------ mi trabajo PT/AL
    @app.get("/api/trabajo/info")
    def trabajo_info():
        # Como listas para conservar el orden (los diccionarios JSON se ordenan alfabéticamente)
        return jsonify(categorias=list(trabajo.CATEGORIAS.items()), tipos_cita=list(trabajo.TIPOS_CITA.items()))

    @app.get("/api/tareas")
    def tareas():
        return jsonify(trabajo.listar_tareas(store, usuario_actual()))

    @app.post("/api/tareas")
    def crear_tarea():
        return jsonify(id=trabajo.crear_tarea(store, usuario_actual(), cuerpo()))

    @app.post("/api/tareas/borrar-hechas")
    def borrar_tareas_hechas():
        return jsonify(borradas=trabajo.borrar_hechas(store, usuario_actual()))

    @app.get("/api/citas")
    def citas():
        a = request.args
        if a.get("mes"):
            desde, hasta = trabajo.rango_mes(a["mes"])
        else:
            desde, hasta = a.get("desde", ""), a.get("hasta", "")
        return jsonify(desde=desde, hasta=hasta,
                       citas=trabajo.listar_citas(store, usuario_actual(), desde, hasta, a.get("alumno_id", type=int)))

    @app.post("/api/citas")
    def crear_cita():
        return jsonify(id=trabajo.crear_cita(store, usuario_actual(), cuerpo()))

    @app.get("/api/avisos")
    def avisos():
        return jsonify(trabajo.avisos(store, usuario_actual()))

    # ------------------------------------------------------------ calendarios externos (solo lectura)
    @app.get("/api/calendarios")
    def calendarios():
        return jsonify(calendario.listar(store, usuario_actual()))

    @app.post("/api/calendarios")
    def calendario_anadir():
        d = cuerpo()
        return jsonify(calendario.anadir_url(store, usuario_actual(), d.get("nombre", ""), d.get("color", ""), d.get("url", ""),
                                             tipo=d.get("tipo", "colegio"), guardar_si_falla=bool(d.get("guardar_si_falla"))))

    @app.post("/api/calendarios/normalizar")
    def calendario_normalizar():
        """Vista previa de lo que se va a guardar, sin enseñar nunca la URL secreta."""
        fuentes = calendario.normalizar_fuentes(cuerpo().get("url", ""))
        return jsonify([{"url": f if not calendario.es_secreta(f) else "", "secreta": calendario.es_secreta(f)} for f in fuentes])

    @app.put("/api/calendarios/<int:cal_id>/url")
    def calendario_cambiar_url(cal_id):
        return jsonify(calendario.cambiar_url(store, cal_id, cuerpo().get("url", "")))

    @app.post("/api/calendarios/importar")
    def calendario_importar():
        archivo = request.files.get("archivo")
        if not archivo:
            raise StoreError("Elige el archivo .ics exportado de tu calendario")
        f = request.form
        cal_id = f.get("calendario_id", type=int)
        return jsonify(calendario.importar_archivo(store, usuario_actual(), f.get("nombre", ""), f.get("color", ""),
                                                   archivo.read(), cal_id))

    @app.post("/api/calendarios/actualizar")
    def calendarios_actualizar():
        minutos = request.args.get("si_antiguo_min", type=int) or 0
        return jsonify(calendario.actualizar(store, usuario_actual(), minutos))

    @app.post("/api/calendarios/<int:cal_id>/probar")
    def calendario_probar(cal_id):
        return jsonify(eventos=calendario.probar(store, cal_id))

    @app.delete("/api/calendarios/<int:cal_id>")
    def calendario_quitar(cal_id):
        calendario.quitar(store, cal_id)
        return jsonify(ok=True)

    @app.get("/api/eventos-externos")
    def eventos_externos():
        a = request.args
        return jsonify(calendario.eventos(store, usuario_actual(), a.get("desde", ""), a.get("hasta", ""), a.get("todos") == "1"))

    # ------------------------------------------------------------ crear material
    @app.errorhandler(ia_material.ErrorIA)
    def _error_ia(e):
        return jsonify(error=str(e)), 400

    def ajuste(clave: str, defecto: str = "") -> str:
        fila = store.q1("SELECT valor FROM meta WHERE clave = ?", (clave,))
        return fila["valor"] if fila and fila["valor"] is not None else defecto

    def poner_ajuste(clave: str, valor: str) -> None:
        with store.tx():
            store.conn.execute("INSERT INTO meta(clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                               (clave, valor))

    carpeta_material = biblioteca.carpeta_material
    logo_perfil = biblioteca.logo_perfil

    def cabecera_perfil(uid) -> str:
        u = store.obtener_usuario(uid) if uid else None
        return ajuste(f"material.cabecera.{uid or 0}", (u or {}).get("nombre", ""))

    def pictos_activados() -> bool:
        return ajuste("material.pictos", "1") == "1"

    @app.get("/api/material/info")
    def material_info():
        uid = usuario_actual()
        return jsonify(tipos=list(material.TIPOS.items()), clave=ia_material.hay_clave(), pictos=pictos_activados(),
                       cabecera=cabecera_perfil(uid), logo_propio=logo_perfil(uid).exists(),
                       carpeta=str(carpeta_material()))

    @app.get("/api/material/sugerencias")
    def material_sugerencias():
        alumno_id = request.args.get("alumno_id", type=int)
        if not alumno_id:
            return jsonify([])
        return jsonify(material.sugerencias(plan.items_pendientes(alumno_id)))

    @app.post("/api/material/propuesta")
    def material_propuesta():
        d = cuerpo()
        uid = usuario_actual()
        nivel, formato = str(d.get("nivel") or "4"), d.get("formato") or "docx"
        num = int(d.get("num") or 0) or None
        if d.get("modo") == "ia":
            objetivos = []
            if d.get("alumno_id"):
                objetivos = [i["texto"] for i in plan.items_pendientes(int(d["alumno_id"]))]
            nombres = [a["nombre"] for a in store.listar_alumnos(uid, incluir_inactivos=True)]
            r = ia_material.generar(d.get("peticion", ""), nivel, formato, num or 6, objetivos, nombres)
            return jsonify(spec=r["spec"].model_dump(), anonimizados=r["anonimizados"], origen="ia")
        try:
            spec = material.plantilla(d.get("tipo", ""), d.get("contenido", ""), nivel, num)
        except ValueError as e:
            raise StoreError(str(e)) from None
        return jsonify(spec=spec.model_dump(), anonimizados=[], origen="plantilla")

    @app.post("/api/material/crear")
    def material_crear():
        d = cuerpo()
        uid = usuario_actual()
        try:
            spec = material.MaterialSpec.model_validate(d.get("spec") or {})
        except Exception:
            raise StoreError("El material no es válido. Vuelve a preparar la propuesta.") from None
        if not spec.paginas:
            raise StoreError("El material no tiene páginas")
        formato = "pptx" if d.get("formato") == "pptx" else "docx"
        alumno = store.q1("SELECT nombre FROM alumnos WHERE id = ?", (d.get("alumno_id"),)) if d.get("alumno_id") else None
        logo = logo_perfil(uid)
        rec = maqueta.Recursos(carpeta_pictos=carpeta_documentos() / "Pictogramas" if pictos_activados() else None,
                               descargar_pictos=pictos_activados(), logo=logo if logo.exists() else None,
                               cabecera=cabecera_perfil(uid), alumno=(alumno or {}).get("nombre", "") if formato == "docx" else "")
        datos = biblioteca.maquetar(spec, formato, rec)
        ruta = biblioteca.nombre_archivo(spec.titulo, formato)
        ruta.write_bytes(datos)
        with store.tx() as c:
            mid = biblioteca.registrar(c, uid, spec, formato, ruta, d.get("tipo", ""), d.get("origen") or "plantilla",
                                       d.get("alumno_id"))
        if d.get("abrir"):
            abrir_archivo(ruta)
        return jsonify(id=mid, ruta=str(ruta), nombre=ruta.name)

    def abrir_archivo(ruta: Path) -> bool:
        if hasattr(os, "startfile") and ruta.exists():
            try:
                os.startfile(str(ruta))  # noqa: S606 - abre el documento con Word o PowerPoint
                return True
            except OSError:
                return False
        return False

    def material_de(mid: int) -> dict:
        m = store.q1("SELECT * FROM materiales WHERE id = ?", (mid,))
        if not m:
            raise StoreError("Material no encontrado")
        return m

    @app.get("/api/materiales")
    def materiales():
        filas = store.q("""SELECT m.*, al.nombre AS alumno FROM materiales m LEFT JOIN alumnos al ON al.id = m.alumno_id
                           WHERE m.usuario_id IS ? ORDER BY m.id DESC LIMIT 200""", (usuario_actual(),))
        for f in filas:
            f["existe"] = Path(f["ruta"]).exists()
        return jsonify(filas)

    @app.post("/api/materiales/<int:mid>/abrir")
    def material_abrir(mid):
        ruta = Path(material_de(mid)["ruta"])
        if not ruta.exists():
            raise StoreError("El archivo ya no está en la carpeta de material")
        return jsonify(abierto=abrir_archivo(ruta), ruta=str(ruta))

    @app.get("/api/materiales/<int:mid>/archivo")
    def material_archivo(mid):
        ruta = Path(material_de(mid)["ruta"])
        if not ruta.exists():
            return jsonify(error="El archivo ya no existe"), 404
        return send_from_directory(ruta.parent, ruta.name, as_attachment=True)

    @app.post("/api/material/clave")
    def material_guardar_clave():
        ia_material.guardar_clave(cuerpo().get("clave", ""))
        return jsonify(ok=True)

    @app.delete("/api/material/clave")
    def material_borrar_clave():
        ia_material.borrar_clave()
        return jsonify(ok=True)

    @app.post("/api/material/clave/probar")
    def material_probar_clave():
        return jsonify(ok=True, modelo=ia_material.probar_clave())

    @app.post("/api/material/ajustes")
    def material_ajustes():
        d = cuerpo()
        uid = usuario_actual()
        if "pictos" in d:
            poner_ajuste("material.pictos", "1" if d["pictos"] else "0")
        if "cabecera" in d:
            poner_ajuste(f"material.cabecera.{uid or 0}", str(d["cabecera"] or "").strip()[:80])
        return jsonify(ok=True)

    # ------------------------------------------------------------ usar con Claude Desktop (servidor MCP local)
    @app.get("/api/claude-desktop")
    def claude_desktop_estado():
        return jsonify(**claude_desktop.estado(), alumnos=ajuste(mcp_server.AJUSTE_ALUMNOS, "0") == "1")

    @app.post("/api/claude-desktop/configurar")
    def claude_desktop_configurar():
        return jsonify(claude_desktop.configurar())

    @app.post("/api/claude-desktop/ajustes")
    def claude_desktop_ajustes():
        d = cuerpo()
        if "alumnos" in d:
            poner_ajuste(mcp_server.AJUSTE_ALUMNOS, "1" if d["alumnos"] else "0")
        return jsonify(ok=True)

    @app.post("/api/material/logo")
    def material_subir_logo():
        archivo = request.files.get("archivo")
        if not archivo:
            raise StoreError("Elige una imagen PNG o JPG")
        datos = archivo.read()
        if not (datos.startswith(b"\x89PNG") or datos.startswith(b"\xff\xd8")):
            raise StoreError("El logo tiene que ser una imagen PNG o JPG")
        logo_perfil(usuario_actual()).write_bytes(datos)  # python-docx y python-pptx leen PNG y JPG por su contenido
        return jsonify(ok=True)

    @app.delete("/api/material/logo")
    def material_quitar_logo():
        logo = logo_perfil(usuario_actual())
        if logo.exists():
            logo.unlink()
        return jsonify(ok=True)

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

    carpeta_documentos = biblioteca.carpeta_documentos

    def enviar_docx(nombre, datos):
        if request.args.get("guardar") == "1":
            # Guardar directamente en Documentos (la ventana nativa no siempre permite descargas)
            ruta = carpeta_documentos() / f"{nombre}.docx"
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

    @app.get("/api/alumnos/<int:alumno_id>/asistencia")
    def asistencia_alumno(alumno_id):
        trimestre = int(request.args.get("trimestre") or informes.trimestre_actual())
        curso = request.args.get("curso_escolar") or informes.curso_escolar_actual()
        return jsonify(informes.asistencia(store, alumno_id, trimestre, curso))

    @app.get("/api/informes/<int:informe_id>/notas")
    def informe_notas(informe_id):
        datos = informes.notas_trimestre(store, informe_id)
        inf = informes.obtener(store, informe_id)
        datos["borrador"] = informes.redactar_notas(datos, informes._nombre_pila(inf["alumno_nombre"]))
        return jsonify(datos)

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
        plan.marcar_item(sesion_id, item_id, d.get("trabajado"), d.get("evaluacion"), d.get("observacion"))
        return jsonify(ok=True)

    @app.delete("/api/sesiones/<int:sesion_id>/items/<int:item_id>")
    def quitar_item(sesion_id, item_id):
        plan.quitar_item(sesion_id, item_id)
        return jsonify(ok=True)

    # ------------------------------------------------------------ copia de seguridad
    def volcar(ruta: Path) -> Path:
        destino_db = sqlite3.connect(str(ruta))
        try:
            with store.lock:
                store.conn.backup(destino_db)
        finally:
            destino_db.close()
        return ruta

    def copia_interna(motivo: str = "") -> Path:
        destino = data_dir() / "copias"
        destino.mkdir(exist_ok=True)
        return volcar(destino / f"mundo_ptal_{dt.datetime.now():%Y%m%d_%H%M%S}{motivo}.db")

    @app.post("/api/copia-seguridad")
    def copia():
        return jsonify(ruta=str(copia_interna()))

    # ------------------------------------------------------------ pasar los datos a otro ordenador
    @app.get("/api/datos/exportar")
    def exportar_datos():
        nombre = f"MundoPTAL_datos_{dt.datetime.now():%Y-%m-%d_%H%M}.db"
        if request.args.get("guardar") == "1":
            return jsonify(ruta=str(volcar(carpeta_documentos() / nombre)))
        with tempfile.TemporaryDirectory() as tmp:
            datos = volcar(Path(tmp) / nombre).read_bytes()
        return Response(datos, mimetype="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    @app.post("/api/datos/importar")
    def importar_datos():
        archivo = request.files.get("archivo")
        if not archivo:
            raise StoreError("Elige el archivo de datos (.db) que quieres cargar")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "importado.db"
            archivo.save(str(ruta))
            prueba = sqlite3.connect(str(ruta))
            try:
                version = prueba.execute("SELECT valor FROM meta WHERE clave = 'schema_version'").fetchone()
                bien = prueba.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            except sqlite3.DatabaseError:
                version, bien = None, False
            finally:
                prueba.close()  # en Windows, si no se cierra, no se puede borrar la carpeta temporal
            if not version or not bien:
                raise StoreError("Ese archivo no es una copia de datos de Mundo PT-AL")
            if int(version[0]) > basedatos.SCHEMA_VERSION:
                raise StoreError("Esos datos son de una versión más nueva del programa. Actualiza primero.")
            # Pone al día el archivo si viene de una versión anterior
            origen = basedatos.connect(ruta)
            try:
                previa = copia_interna("_antes_de_importar")
                with store.lock:
                    origen.backup(store.conn)
            finally:
                origen.close()
        usuarios = store.listar_usuarios()
        # Las direcciones secretas de calendario no viajan con los datos: hay que pegarlas de nuevo
        sin_dir = sum(1 for c in store.q("SELECT id FROM calendarios_externos WHERE origen = 'url' AND url_publica = ''")
                      if not calendario.leer_url(store, c["id"]))
        return jsonify(ok=True, copia_previa=str(previa), usuarios=len(usuarios),
                       alumnos=store.q1("SELECT COUNT(*) AS n FROM alumnos")["n"], calendarios_sin_direccion=sin_dir)

    # ------------------------------------------------------------ actualizaciones
    @app.get("/api/actualizacion")
    def buscar_actualizacion():
        return jsonify(actualizador.comprobar())

    @app.post("/api/actualizacion/instalar")
    def instalar_actualizacion():
        url = cuerpo().get("url") or actualizador.comprobar().get("url")
        copia_interna(f"_antes_de_{APP_VERSION}")
        return jsonify(actualizador.instalar(url))

    return app
