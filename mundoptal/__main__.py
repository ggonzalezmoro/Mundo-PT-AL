"""Arranque de la aplicación de escritorio.

1. Levanta la API local en 127.0.0.1 (un puerto libre, nunca accesible desde la red).
2. Abre una ventana nativa de Windows (pywebview + Edge WebView2).
   Si la ventana nativa no está disponible, abre el navegador predeterminado.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser

from werkzeug.serving import make_server

from .config import APP_NAME, APP_VERSION, data_dir, db_path
from .servidor import crear_app


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _configurar_log():
    logging.basicConfig(
        filename=str(data_dir() / "mundo_ptal.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _valor(argv: list[str], opcion: str) -> str | None:
    if opcion in argv:
        i = argv.index(opcion)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def configurar_desde_consola(argv: list[str]) -> int:
    """Alta de un perfil e importación de su horario sin abrir la ventana:

    MundoPTAL --perfil "Fátima" --especialidad PT/AL --importar-horario horario.xlsx [--reemplazar]
    """
    from pathlib import Path

    from . import horario
    from .planificador import Planificador
    from .store import Store

    store = Store(db_path())
    nombre = _valor(argv, "--perfil")
    especialidad = _valor(argv, "--especialidad") or "PT/AL"
    usuario = store.buscar_usuario(nombre)
    if usuario:
        uid = usuario["id"]
        store.actualizar("usuarios", uid, {"especialidad": especialidad})
        mensaje = [f"Perfil existente: {usuario['nombre']} ({especialidad})"]
    else:
        uid = store.crear_usuario(nombre, especialidad)
        mensaje = [f"Perfil creado: {nombre} ({especialidad})"]
    archivo = _valor(argv, "--importar-horario")
    if archivo:
        ruta = Path(archivo)
        franjas = horario.analizar_tabla(horario.leer_tabla(ruta.name, ruta.read_bytes()))
        r = horario.importar_horario(store, Planificador(store), uid, franjas, "--reemplazar" in argv)
        mensaje.append(f"Franjas importadas: {r['franjas']}")
        mensaje.append("Alumnos nuevos: " + (", ".join(r["alumnos_nuevos"]) or "ninguno"))
        if r["omitidas"]:
            mensaje.append("Omitidas: " + "; ".join(r["omitidas"]))
    texto = "\n".join(mensaje)
    logging.info(texto)
    if sys.stdout:
        print(texto)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    _configurar_log()
    if _valor(argv, "--perfil"):
        return configurar_desde_consola(argv)
    app = crear_app(db_path())
    puerto = int(os.environ.get("MUNDOPTAL_PORT", 0)) or _puerto_libre()
    servidor = make_server("127.0.0.1", puerto, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{puerto}/"
    logging.info("%s %s escuchando en %s", APP_NAME, APP_VERSION, url)

    if "--navegador" in argv or "--servidor" in argv:
        if "--navegador" in argv:
            webbrowser.open(url)
        if sys.stdout:
            print(f"{APP_NAME} en {url} (Ctrl+C para salir)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        servidor.shutdown()
        return 0

    try:
        import webview

        ventana = webview.create_window(
            f"{APP_NAME} · Colegio San Ignacio de Loyola", url,
            width=1320, height=860, min_size=(1000, 650),
        )
        ventana.events.closed += lambda: servidor.shutdown()
        webview.start(private_mode=False)
    except Exception:
        logging.exception("No se pudo abrir la ventana nativa; se usa el navegador")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    servidor.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
