"""Subir el material a Google Drive y abrirlo con Documentos o Presentaciones de Google.

Sirve para los ordenadores sin Word ni PowerPoint: el .docx/.pptx se guarda igual en
Documentos › Mundo PT-AL › Material y, además, se sube convertido a Google Docs o Google
Slides a la carpeta «material mundo pt/al» de Mi unidad, y se abre en el navegador.

- Inicio de sesión de Google para aplicaciones de escritorio (OAuth 2.0 con PKCE y
  redirección a 127.0.0.1, la propia aplicación). Permiso mínimo «drive.file»: la aplicación
  solo ve los archivos y carpetas que ha creado ella, nunca el resto de tu Drive.
- El «token de actualización» de cada perfil se guarda en el Administrador de credenciales
  de Windows (keyring), nunca en la base de datos ni en los registros.
- Solo se conecta a Google cuando el usuario sube o abre un material. Sin Internet todo
  lo demás sigue funcionando y el archivo queda en el ordenador.
- Las credenciales del cliente OAuth (client_secret.json del proyecto de Google Cloud) se
  buscan en este orden: Ajustes (keyring), google_cliente.json junto al programa (lo añade
  la compilación) y la variable MUNDOPTAL_GOOGLE_CLIENTE (pruebas). En las aplicaciones de
  escritorio Google no las considera secretas, pero no se suben al repositorio.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .config import base_dir

SERVICIO = "MundoPTAL"
CLAVE_CLIENTE = "google_cliente"
ALCANCES = "https://www.googleapis.com/auth/drive.file openid email"
URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_REVOCAR = "https://oauth2.googleapis.com/revoke"
URL_ARCHIVOS = "https://www.googleapis.com/drive/v3/files"
URL_SUBIDA = "https://www.googleapis.com/upload/drive/v3/files"
NOMBRE_CARPETA = "material mundo pt/al"
URL_MI_UNIDAD = "https://drive.google.com/drive/my-drive"

MIME_ORIGEN = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
MIME_GOOGLE = {
    "docx": "application/vnd.google-apps.document",
    "pptx": "application/vnd.google-apps.presentation",
}
MIME_CARPETA = "application/vnd.google-apps.folder"


class ErrorDrive(RuntimeError):
    """Error con un mensaje que se puede enseñar tal cual a la maestra."""


# ------------------------------------------------------------------ almacén de credenciales
def _keyring():
    from .ia_material import _keyring as k
    return k()


def _leer(clave: str) -> str:
    try:
        return _keyring().get_password(SERVICIO, clave) or ""
    except Exception:
        return ""


def _guardar(clave: str, valor: str) -> None:
    _keyring().set_password(SERVICIO, clave, valor)


def _borrar(clave: str) -> None:
    try:
        _keyring().delete_password(SERVICIO, clave)
    except Exception:
        pass


def _clave_token(uid) -> str:
    return f"google_token_{uid or 0}"


# ------------------------------------------------------------------ cliente OAuth
def _interpretar_cliente(texto: str) -> dict:
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        raise ErrorDrive("El archivo no es el JSON que descarga Google Cloud (client_secret_….json).") from None
    datos = datos.get("installed") or datos.get("web") or datos if isinstance(datos, dict) else {}
    cid, secreto = str(datos.get("client_id", "")).strip(), str(datos.get("client_secret", "")).strip()
    if not cid.endswith(".apps.googleusercontent.com") or not secreto:
        raise ErrorDrive("Faltan «client_id» o «client_secret». Descarga el JSON del cliente de tipo «App de escritorio».")
    return {"client_id": cid, "client_secret": secreto}


def cliente() -> dict | None:
    """Credenciales del cliente OAuth o None si no hay ninguno configurado."""
    candidatos = [_leer(CLAVE_CLIENTE), os.environ.get("MUNDOPTAL_GOOGLE_CLIENTE", "")]
    archivo = base_dir() / "google_cliente.json"
    if archivo.exists():
        candidatos.insert(1, archivo.read_text(encoding="utf-8"))
    for texto in candidatos:
        if texto:
            try:
                return _interpretar_cliente(texto)
            except ErrorDrive:
                continue
    return None


def guardar_cliente(texto: str) -> None:
    _interpretar_cliente(texto)
    _guardar(CLAVE_CLIENTE, texto.strip())


def borrar_cliente() -> None:
    _borrar(CLAVE_CLIENTE)


def cliente_propio() -> bool:
    """True si el cliente se cargó desde Ajustes (y por tanto se puede quitar desde allí)."""
    return bool(_leer(CLAVE_CLIENTE))


# ------------------------------------------------------------------ HTTP
def _http(metodo: str, url: str, datos: bytes | None = None, cabeceras: dict | None = None, timeout: float = 30) -> dict:
    """Petición a Google. Devuelve el JSON de la respuesta (o {}). Las pruebas la sustituyen."""
    req = urllib.request.Request(url, data=datos, method=metodo, headers={"User-Agent": "MundoPTAL", **(cabeceras or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - solo URL fijas de Google
            cuerpo = r.read()
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read() or b"{}")
        except ValueError:
            detalle = {}
        raise ErrorHTTP(e.code, detalle) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErrorDrive("No hay conexión con Google. El archivo está guardado en el ordenador; "
                         "vuelve a intentarlo cuando tengas Internet.") from None
    return json.loads(cuerpo) if cuerpo else {}


class ErrorHTTP(ErrorDrive):
    def __init__(self, codigo: int, detalle: dict):
        self.codigo, self.detalle = codigo, detalle
        err = detalle.get("error")
        texto = (err.get("message") if isinstance(err, dict) else detalle.get("error_description") or err) or ""
        super().__init__(f"Google ha respondido con un error ({codigo}). {texto}".strip())


def _formulario(datos: dict) -> bytes:
    return urllib.parse.urlencode(datos).encode()


# ------------------------------------------------------------------ inicio de sesión
_PENDIENTES: dict[str, dict] = {}
_TOKENS: dict[int, tuple[str, float]] = {}
_CERROJO = threading.Lock()


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def iniciar(uid, redireccion: str) -> str:
    """URL de inicio de sesión de Google. «redireccion» es la dirección local de la aplicación."""
    c = cliente()
    if not c:
        raise ErrorDrive("Falta configurar la conexión con Google (Ajustes › Google Drive).")
    verificador = _b64(secrets.token_bytes(48))
    estado = secrets.token_urlsafe(24)
    with _CERROJO:
        ahora = time.time()
        for k in [k for k, v in _PENDIENTES.items() if ahora - v["creado"] > 900]:
            del _PENDIENTES[k]
        _PENDIENTES[estado] = {"uid": uid, "verificador": verificador, "redireccion": redireccion, "creado": ahora}
    return URL_AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redireccion, "response_type": "code", "scope": ALCANCES,
        "state": estado, "code_challenge": _b64(hashlib.sha256(verificador.encode()).digest()),
        "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent select_account",
    })


def es_estado(estado: str) -> bool:
    return estado in _PENDIENTES


def cancelar(estado: str) -> None:
    with _CERROJO:
        _PENDIENTES.pop(estado, None)


def completar(estado: str, codigo: str) -> dict:
    """Canjea el código que devuelve Google. Devuelve {uid, email}."""
    with _CERROJO:
        p = _PENDIENTES.pop(estado, None)
    if not p:
        raise ErrorDrive("El enlace de inicio de sesión ha caducado. Vuelve a pulsar «Conectar con Google».")
    c = cliente() or {}
    r = _http("POST", URL_TOKEN, _formulario({
        "client_id": c.get("client_id", ""), "client_secret": c.get("client_secret", ""), "code": codigo,
        "code_verifier": p["verificador"], "grant_type": "authorization_code", "redirect_uri": p["redireccion"],
    }), {"Content-Type": "application/x-www-form-urlencoded"})
    if not r.get("refresh_token"):
        raise ErrorDrive("Google no ha dado permiso para seguir conectado. Vuelve a intentarlo.")
    _guardar(_clave_token(p["uid"]), r["refresh_token"])
    with _CERROJO:
        _TOKENS[p["uid"] or 0] = (r.get("access_token", ""), time.time() + int(r.get("expires_in", 0)) - 60)
    return {"uid": p["uid"], "email": _email_de(r.get("id_token", ""))}


def _email_de(id_token: str) -> str:
    """Correo de la cuenta (solo para enseñarlo en Ajustes; no se usa para nada más)."""
    try:
        carga = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4))).get("email", "")
    except Exception:
        return ""


def conectado(uid) -> bool:
    return bool(_leer(_clave_token(uid)))


def desconectar(uid) -> None:
    token = _leer(_clave_token(uid))
    _borrar(_clave_token(uid))
    with _CERROJO:
        _TOKENS.pop(uid or 0, None)
    if token:
        try:
            _http("POST", URL_REVOCAR, _formulario({"token": token}), {"Content-Type": "application/x-www-form-urlencoded"}, 10)
        except ErrorDrive:
            pass  # sin Internet: el permiso se puede quitar también desde la cuenta de Google


def _token(uid) -> str:
    with _CERROJO:
        guardado = _TOKENS.get(uid or 0)
    if guardado and guardado[0] and guardado[1] > time.time():
        return guardado[0]
    refresco = _leer(_clave_token(uid))
    c = cliente()
    if not refresco or not c:
        raise ErrorDrive("No estás conectada a Google Drive. Conéctate en Ajustes › Google Drive.")
    try:
        r = _http("POST", URL_TOKEN, _formulario({
            "client_id": c["client_id"], "client_secret": c["client_secret"], "refresh_token": refresco,
            "grant_type": "refresh_token"}), {"Content-Type": "application/x-www-form-urlencoded"})
    except ErrorHTTP as e:
        if e.codigo in (400, 401):  # permiso retirado o caducado
            _borrar(_clave_token(uid))
            raise ErrorDrive("Google ha cerrado la conexión. Vuelve a conectarte en Ajustes › Google Drive.") from None
        raise
    with _CERROJO:
        _TOKENS[uid or 0] = (r["access_token"], time.time() + int(r.get("expires_in", 0)) - 60)
    return r["access_token"]


# ------------------------------------------------------------------ Drive
def _con_token(uid) -> dict:
    return {"Authorization": f"Bearer {_token(uid)}"}


def asegurar_carpeta(uid, carpeta_id: str = "") -> str:
    """Id de la carpeta «material mundo pt/al». Si no existe (o está en la papelera) se crea en
    Mi unidad. La maestra puede moverla a otra carpeta de su Drive: se sigue usando."""
    if carpeta_id:
        try:
            f = _http("GET", f"{URL_ARCHIVOS}/{urllib.parse.quote(carpeta_id)}?fields=id,trashed", None, _con_token(uid))
            if f.get("id") and not f.get("trashed"):
                return f["id"]
        except ErrorHTTP as e:
            if e.codigo != 404:
                raise
    f = _http("POST", f"{URL_ARCHIVOS}?fields=id", json.dumps({"name": NOMBRE_CARPETA, "mimeType": MIME_CARPETA}).encode(),
              {**_con_token(uid), "Content-Type": "application/json; charset=UTF-8"})
    return f["id"]


def url_carpeta(carpeta_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{carpeta_id}" if carpeta_id else URL_MI_UNIDAD


def subir(uid, ruta: Path, titulo: str, formato: str, carpeta_id: str) -> dict:
    """Sube el archivo convertido a Documentos/Presentaciones de Google. Devuelve {id, url}."""
    if formato not in MIME_ORIGEN:
        raise ErrorDrive("Solo se pueden subir fichas de Word o diapositivas de PowerPoint.")
    meta = {"name": titulo or ruta.stem, "mimeType": MIME_GOOGLE[formato], "parents": [carpeta_id]}
    limite = "mundoptal" + uuid.uuid4().hex
    cuerpo = b"".join([
        f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
        json.dumps(meta).encode(),
        f"\r\n--{limite}\r\nContent-Type: {MIME_ORIGEN[formato]}\r\n\r\n".encode(),
        ruta.read_bytes(),
        f"\r\n--{limite}--\r\n".encode(),
    ])
    f = _http("POST", f"{URL_SUBIDA}?uploadType=multipart&fields=id,webViewLink", cuerpo,
              {**_con_token(uid), "Content-Type": f"multipart/related; boundary={limite}"}, timeout=120)
    return {"id": f["id"], "url": f.get("webViewLink") or (
        f"https://docs.google.com/{'document' if formato == 'docx' else 'presentation'}/d/{f['id']}/edit")}
