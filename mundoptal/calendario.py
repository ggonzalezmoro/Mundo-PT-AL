"""Calendarios externos (Google Calendar u otros) en «Mi trabajo PT/AL», solo de lectura.

Se leen con la «dirección secreta en formato iCal» (URL .ics privada) o importando un
archivo .ics. La URL es un secreto: se guarda en el Administrador de credenciales de
Windows (keyring), nunca en la base de datos, en los registros ni en los mensajes.
Los eventos se expanden (repeticiones incluidas) y se guardan en la tabla
eventos_externos para verlos también sin Internet. Nunca se envía nada al calendario."""
from __future__ import annotations

import datetime as dt
import re
import urllib.request
from zoneinfo import ZoneInfo

from .store import Store, StoreError

ZONA = ZoneInfo("Europe/Madrid")
SERVICIO = "MundoPTAL"
DIAS_ATRAS, DIAS_ADELANTE = 62, 400
TIEMPO = 20
MAX_BYTES = 8 * 1024 * 1024
RX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


# ------------------------------------------------------------------ URL secreta (keyring)
def _clave(cal_id: int) -> str:
    return f"ical_{cal_id}"


def leer_url(cal_id: int) -> str:
    from .ia_material import _keyring
    try:
        return _keyring().get_password(SERVICIO, _clave(cal_id)) or ""
    except Exception:
        return ""


def guardar_url(cal_id: int, url: str) -> None:
    from .ia_material import _keyring
    _keyring().set_password(SERVICIO, _clave(cal_id), url)


def borrar_url(cal_id: int) -> None:
    from .ia_material import _keyring
    try:
        _keyring().delete_password(SERVICIO, _clave(cal_id))
    except Exception:
        pass


def validar_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not re.match(r"^https://[^\s/]+/\S+$", url):
        raise StoreError("Pega la «dirección secreta en formato iCal» completa (empieza por https:// y acaba en .ics).")
    return url


# ------------------------------------------------------------------ lectura y expansión
def descargar(url: str) -> bytes:
    """GET de la URL del calendario (solo lectura, sin enviar nada más)."""
    req = urllib.request.Request(url, headers={"User-Agent": "MundoPTAL", "Accept": "text/calendar"})
    try:
        with urllib.request.urlopen(req, timeout=TIEMPO) as r:
            datos = r.read(MAX_BYTES + 1)
    except Exception as e:  # noqa: BLE001
        codigo = getattr(e, "code", None)
        if codigo in (401, 403, 404):
            raise StoreError("La dirección del calendario no es válida o se ha cambiado. Copia de nuevo la dirección secreta.") from None
        raise StoreError("No se ha podido leer el calendario. Comprueba la conexión a Internet.") from None
    if len(datos) > MAX_BYTES:
        raise StoreError("El calendario es demasiado grande")
    return datos


def _local(valor) -> tuple[str, bool]:
    """(«AAAA-MM-DD» o «AAAA-MM-DDTHH:MM» en hora de Madrid, es_todo_el_dia)."""
    if isinstance(valor, dt.datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=ZONA)  # hora «flotante»: se toma como hora local
        return valor.astimezone(ZONA).strftime("%Y-%m-%dT%H:%M"), False
    return valor.isoformat(), True


def _texto(comp, campo: str) -> str:
    v = comp.get(campo)
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def eventos_de_ics(datos: bytes, hoy: dt.date | None = None) -> list[dict]:
    """Eventos del calendario entre ~2 meses atrás y ~13 meses adelante, con las
    repeticiones (RRULE/RDATE/EXDATE) ya expandidas."""
    import icalendar
    import recurring_ical_events

    try:
        cal = icalendar.Calendar.from_ical(datos)
    except Exception:
        raise StoreError("El archivo no es un calendario .ics válido") from None
    hoy = hoy or dt.date.today()
    desde, hasta = hoy - dt.timedelta(days=DIAS_ATRAS), hoy + dt.timedelta(days=DIAS_ADELANTE)
    salida = []
    for ev in recurring_ical_events.of(cal).between(desde, hasta):
        if _texto(ev, "STATUS").upper() == "CANCELLED":
            continue
        inicio = ev.get("DTSTART")
        if inicio is None:
            continue
        ini, todo = _local(inicio.dt)
        fin_prop = ev.get("DTEND")
        if fin_prop is not None:
            fin, _ = _local(fin_prop.dt)
        elif todo:
            fin = (inicio.dt + dt.timedelta(days=1)).isoformat()
        else:
            fin = ini
        if todo:  # DTEND de un evento de todo el día es exclusivo: se guarda el último día incluido
            ultimo = dt.date.fromisoformat(fin[:10]) - dt.timedelta(days=1)
            fin = max(ultimo, dt.date.fromisoformat(ini[:10])).isoformat()
        salida.append({"uid": _texto(ev, "UID"), "inicio": ini, "fin": fin, "todo_el_dia": int(todo),
                       "titulo": _texto(ev, "SUMMARY") or "(Sin título)", "lugar": _texto(ev, "LOCATION"),
                       "descripcion": _texto(ev, "DESCRIPTION")[:2000]})
    salida.sort(key=lambda e: (e["inicio"], e["titulo"]))
    return salida


# ------------------------------------------------------------------ calendarios del perfil
def listar(store: Store, usuario_id: int | None) -> list[dict]:
    filas = store.q("""SELECT c.*, (SELECT COUNT(*) FROM eventos_externos e WHERE e.calendario_id = c.id) AS eventos
                       FROM calendarios_externos c WHERE c.usuario_id IS ? ORDER BY c.id""", (usuario_id,))
    for f in filas:
        f["tiene_url"] = f["origen"] == "url" and bool(leer_url(f["id"]))
    return filas


def _crear(store: Store, usuario_id, nombre: str, color: str, origen: str) -> int:
    nombre = (nombre or "").strip()[:60] or "Calendario del colegio"
    color = color if RX_COLOR.match(color or "") else "#2B7BB9"
    with store.tx() as c:
        return c.execute("INSERT INTO calendarios_externos(usuario_id, nombre, color, origen) VALUES (?, ?, ?, ?)",
                         (usuario_id, nombre, color, origen)).lastrowid


def _guardar_eventos(store: Store, cal_id: int, usuario_id, eventos: list[dict]) -> int:
    with store.tx() as c:
        c.execute("DELETE FROM eventos_externos WHERE calendario_id = ?", (cal_id,))
        c.executemany("""INSERT INTO eventos_externos(calendario_id, usuario_id, uid, inicio, fin, todo_el_dia, titulo, lugar, descripcion)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      [(cal_id, usuario_id, e["uid"], e["inicio"], e["fin"], e["todo_el_dia"], e["titulo"], e["lugar"],
                        e["descripcion"]) for e in eventos])
        c.execute("UPDATE calendarios_externos SET actualizado = ?, error = '' WHERE id = ?",
                  (dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), cal_id))
    return len(eventos)


def anadir_url(store: Store, usuario_id, nombre: str, color: str, url: str, descargador=None) -> dict:
    url = validar_url(url)
    eventos = eventos_de_ics((descargador or descargar)(url))  # primero se prueba: si falla, no se guarda nada
    cal_id = _crear(store, usuario_id, nombre, color, "url")
    guardar_url(cal_id, url)
    return {"id": cal_id, "eventos": _guardar_eventos(store, cal_id, usuario_id, eventos)}


def importar_archivo(store: Store, usuario_id, nombre: str, color: str, datos: bytes, cal_id: int | None = None) -> dict:
    eventos = eventos_de_ics(datos)
    if cal_id is None:
        cal_id = _crear(store, usuario_id, nombre, color, "archivo")
    return {"id": cal_id, "eventos": _guardar_eventos(store, cal_id, usuario_id, eventos)}


def actualizar(store: Store, usuario_id, solo_antiguos_min: int = 0, descargador=None) -> list[dict]:
    """Vuelve a leer los calendarios con URL del perfil. Con solo_antiguos_min, solo los
    que llevan más de esos minutos sin actualizarse (al abrir la aplicación)."""
    resultado = []
    for cal in store.q("SELECT * FROM calendarios_externos WHERE usuario_id IS ? AND origen = 'url'", (usuario_id,)):
        if solo_antiguos_min and cal["actualizado"]:
            hace = dt.datetime.now() - dt.datetime.fromisoformat(cal["actualizado"])
            if hace < dt.timedelta(minutes=solo_antiguos_min):
                continue
        url = leer_url(cal["id"])
        if not url:
            continue
        try:
            n = _guardar_eventos(store, cal["id"], usuario_id, eventos_de_ics((descargador or descargar)(url)))
            resultado.append({"id": cal["id"], "eventos": n})
        except StoreError as e:
            with store.tx() as c:
                c.execute("UPDATE calendarios_externos SET error = ? WHERE id = ?", (str(e), cal["id"]))
            resultado.append({"id": cal["id"], "error": str(e)})
    return resultado


def probar(store: Store, cal_id: int, descargador=None) -> int:
    url = leer_url(cal_id)
    if not url:
        raise StoreError("Este calendario no tiene dirección guardada")
    return len(eventos_de_ics((descargador or descargar)(url)))


def quitar(store: Store, cal_id: int) -> None:
    borrar_url(cal_id)
    with store.tx() as c:
        c.execute("DELETE FROM calendarios_externos WHERE id = ?", (cal_id,))


def eventos(store: Store, usuario_id, desde: str, hasta: str) -> list[dict]:
    """Eventos que tocan el rango [desde, hasta] (fechas AAAA-MM-DD)."""
    return store.q(
        """SELECT e.id, e.inicio, e.fin, e.todo_el_dia, e.titulo, e.lugar, e.descripcion,
                  c.nombre AS calendario, c.color FROM eventos_externos e
           JOIN calendarios_externos c ON c.id = e.calendario_id
           WHERE e.usuario_id IS ? AND substr(e.inicio, 1, 10) <= ? AND substr(e.fin, 1, 10) >= ?
           ORDER BY e.todo_el_dia DESC, e.inicio, e.titulo""", (usuario_id, hasta, desde))
