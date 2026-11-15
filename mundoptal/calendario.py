"""Calendarios externos (Google Calendar u otros) en «Mi trabajo PT/AL», solo de lectura.

La fuente se puede dar de varias formas y se normaliza a una URL .ics (ver normalizar_fuentes):
enlace «embed» o código <iframe> de Google, ID del calendario, URL .ics pública o URL .ics secreta.

- Pública (…/public/basic.ics de Google): se guarda en la base de datos y viaja al exportar los datos.
- Secreta (…/private-…/basic.ics, o cualquier .ics que no sea de Google): es una contraseña;
  se guarda en el Administrador de credenciales de Windows (keyring), nunca en la base de datos,
  en los registros ni en los mensajes. No se exporta: en otro ordenador hay que pegarla de nuevo.

Los eventos se expanden (repeticiones incluidas) y se guardan en eventos_externos para verlos
también sin Internet. Sentido único: nunca se envía nada al calendario."""
from __future__ import annotations

import base64
import datetime as dt
import re
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from .store import Store, StoreError

ZONA = ZoneInfo("Europe/Madrid")
SERVICIO = "MundoPTAL"
DIAS_ATRAS, DIAS_ADELANTE = 62, 400
TIEMPO = 20
MAX_BYTES = 8 * 1024 * 1024
RX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
GOOGLE = ("calendar.google.com", "www.google.com")
GOOGLE_ICAL = "https://calendar.google.com/calendar/ical/{}/public/basic.ics"
RX_ID = re.compile(r"^[A-Za-z0-9._%+#-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
COLORES_SUAVES = ["#7FB3D5", "#F1948A", "#82E0AA", "#F8C471", "#BB8FCE", "#76D7C4", "#F0B27A", "#AEB6BF"]


# ------------------------------------------------------------------ fuentes: normalización
def es_secreta(url: str) -> bool:
    """La URL da acceso sin iniciar sesión, así que se trata como una contraseña.
    En Google, las secretas llevan «/private-…»; fuera de Google no se puede saber, así que
    se tratan todas como secretas (Outlook, iCloud… suelen llevar un token en la URL)."""
    u = urllib.parse.urlsplit(url)
    if u.hostname not in GOOGLE:
        return True
    return "/private-" in u.path or bool(u.query)


def _id_de_cid(cid: str) -> str:
    """El parámetro cid= de los enlaces «Añadir a Google Calendar» es el ID en base64."""
    if "@" in cid:
        return cid
    try:
        return base64.urlsafe_b64decode(cid + "=" * (-len(cid) % 4)).decode("utf-8")
    except Exception:
        return cid


def _ics_de_id(cal_id: str) -> str:
    return GOOGLE_ICAL.format(urllib.parse.quote(cal_id, safe=""))


def _desescapar(t: str) -> str:
    """Solo &amp; (también &amp;amp;) y comillas: html.unescape completo estropearía
    parámetros como «&para=» o «&not=», que HTML acepta como entidades sin «;»."""
    while "&amp;" in t:
        t = t.replace("&amp;", "&")
    return t.replace("&quot;", '"').replace("&#34;", '"').replace("&#39;", "'")


def normalizar_fuentes(texto: str) -> list[str]:
    """Convierte lo que se pegue en una o varias URL .ics https://.

    Acepta: código <iframe> o enlace …/calendar/embed?src=<id>&ctz=… (también con &amp;; un
    embed puede traer varios src=), enlaces con cid=, el ID del calendario
    (alguien@colegio.es, c_…@group.calendar.google.com) y URL .ics (https:// o webcal://)."""
    t = _desescapar((texto or "").strip())
    if "<iframe" in t.lower():
        m = re.search(r"""src\s*=\s*["']([^"']+)["']""", t)
        if m:
            t = _desescapar(m.group(1))
    t = t.strip().strip("<>\"'")
    if t.startswith("webcal://"):
        t = "https://" + t[len("webcal://"):]
    if t.startswith("//"):
        t = "https:" + t
    if RX_ID.match(urllib.parse.unquote(t)):
        return [_ics_de_id(urllib.parse.unquote(t))]
    u = urllib.parse.urlsplit(t)
    if u.scheme == "https" and u.hostname in GOOGLE and "/ical/" not in u.path:
        params = urllib.parse.parse_qs(u.query)
        ids = params.get("src", []) or [_id_de_cid(c) for c in params.get("cid", [])]
        ids = [i.strip() for i in ids if RX_ID.match(i.strip())]
        if ids:
            return list(dict.fromkeys(_ics_de_id(i) for i in ids))
        raise StoreError("Ese enlace de Google Calendar no lleva el calendario. Copia el enlace de «Insertar código» "
                         "o la dirección en formato iCal (Configuración y uso compartido › Integrar el calendario).")
    if u.scheme == "https" and u.hostname and len(u.path) > 1 and not re.search(r"\s", t):
        return [t]
    raise StoreError("No reconozco esa dirección. Pega el enlace «Insertar» de Google Calendar, el ID del "
                     "calendario o la dirección en formato iCal (acaba en .ics).")


def validar_url(url: str) -> str:
    fuentes = normalizar_fuentes(url)
    if len(fuentes) != 1:
        raise StoreError("Esa dirección incluye varios calendarios: añádelos de uno en uno")
    return fuentes[0]


# ------------------------------------------------------------------ URL secreta (keyring)
def _keyring():
    from .ia_material import _keyring as k
    return k()


def _leer_secreta(clave: str) -> str:
    try:
        return _keyring().get_password(SERVICIO, clave) or ""
    except Exception:
        return ""


def _borrar_secreta(clave: str) -> None:
    try:
        _keyring().delete_password(SERVICIO, clave)
    except Exception:
        pass


def _clave_legado(cal_id: int) -> str:  # la v0.6.2 guardaba la URL como «ical_<id>»
    return f"ical_{cal_id}"


def guardar_url(store: Store, cal_id: int, url: str) -> None:
    """Pública -> columna url_publica. Secreta -> keyring con una clave aleatoria (así no choca
    con los calendarios de unos datos importados de otro ordenador, que tienen otros id)."""
    anterior = store.q1("SELECT clave_secreta FROM calendarios_externos WHERE id = ?", (cal_id,))
    if es_secreta(url):
        clave, publica = f"ical_{uuid.uuid4().hex}", ""
        _keyring().set_password(SERVICIO, clave, url)
    else:
        clave, publica = "", url
    with store.tx() as c:
        c.execute("UPDATE calendarios_externos SET url_publica = ?, clave_secreta = ? WHERE id = ?", (publica, clave, cal_id))
    if anterior and anterior["clave_secreta"] and anterior["clave_secreta"] != clave:
        _borrar_secreta(anterior["clave_secreta"])


def leer_url(store: Store, cal_id: int) -> str:
    """URL efectiva del calendario: la pública de la BD o la secreta del keyring."""
    f = store.q1("SELECT url_publica, clave_secreta, origen FROM calendarios_externos WHERE id = ?", (cal_id,))
    if not f or f["origen"] != "url":
        return ""
    if f["url_publica"]:
        return f["url_publica"]
    if f["clave_secreta"]:
        return _leer_secreta(f["clave_secreta"])
    legado = _leer_secreta(_clave_legado(cal_id))
    if legado:
        guardar_url(store, cal_id, legado)
        _borrar_secreta(_clave_legado(cal_id))
    return legado


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
            raise StoreError("Google no deja leer este calendario: no es público o la dirección ha cambiado. Hazlo público o pega su dirección secreta en formato iCal.") from None
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
    filas = store.q("""SELECT c.id, c.usuario_id, c.nombre, c.color, c.origen, c.tipo, c.visible, c.actualizado, c.error,
                              c.url_publica, (SELECT COUNT(*) FROM eventos_externos e WHERE e.calendario_id = c.id) AS eventos
                       FROM calendarios_externos c WHERE c.usuario_id IS ? ORDER BY c.id""", (usuario_id,))
    for f in filas:
        f["secreta"] = f["origen"] == "url" and not f["url_publica"]
        f["tiene_url"] = f["origen"] == "url" and bool(leer_url(store, f["id"]))
        f["falta_secreta"] = f["secreta"] and not f["tiene_url"]  # p. ej., tras importar los datos en otro ordenador
    return filas


def _crear(store: Store, usuario_id, nombre: str, color: str, origen: str, tipo: str = "colegio") -> int:
    nombre = (nombre or "").strip()[:60] or "Calendario del colegio"
    color = color if RX_COLOR.match(color or "") else COLORES_SUAVES[0]
    tipo = tipo if tipo in ("colegio", "personal") else "colegio"
    with store.tx() as c:
        return c.execute("INSERT INTO calendarios_externos(usuario_id, nombre, color, origen, tipo) VALUES (?, ?, ?, ?, ?)",
                         (usuario_id, nombre, color, origen, tipo)).lastrowid


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


def _marcar_error(store: Store, cal_id: int, error: str) -> None:
    with store.tx() as c:
        c.execute("UPDATE calendarios_externos SET error = ? WHERE id = ?", (error, cal_id))


def anadir_url(store: Store, usuario_id, nombre: str, color: str, url: str, descargador=None,
               tipo: str = "colegio", guardar_si_falla: bool = False) -> dict:
    """Añade uno o varios calendarios (un embed puede traer varios). Primero se prueba la
    descarga: si falla no se guarda nada, salvo con guardar_si_falla (queda guardado con el
    aviso de error y se sincroniza solo en cuanto Google lo deje leer)."""
    leidos = []
    for f in normalizar_fuentes(url):
        try:
            leidos.append((f, eventos_de_ics((descargador or descargar)(f)), ""))
        except StoreError as e:
            if not guardar_si_falla:
                raise
            leidos.append((f, None, str(e)))
    ya = len(listar(store, usuario_id))
    creados = []
    for i, (f, evs, error) in enumerate(leidos):
        n = nombre if i == 0 else f"{(nombre or 'Calendario').strip()} {i + 1}"
        col = color if i == 0 and RX_COLOR.match(color or "") else COLORES_SUAVES[(ya + i) % len(COLORES_SUAVES)]
        cal_id = _crear(store, usuario_id, n, col, "url", tipo)
        guardar_url(store, cal_id, f)
        r = {"id": cal_id, "secreta": es_secreta(f)}
        if evs is None:
            _marcar_error(store, cal_id, error)
            r.update(eventos=0, error=error)
        else:
            r["eventos"] = _guardar_eventos(store, cal_id, usuario_id, evs)
        creados.append(r)
    return {**creados[0], "calendarios": creados}


def cambiar_url(store: Store, cal_id: int, url: str, descargador=None) -> dict:
    """Vuelve a pegar la dirección (p. ej., la secreta tras importar los datos en otro ordenador)."""
    cal = store.q1("SELECT * FROM calendarios_externos WHERE id = ?", (cal_id,))
    if not cal:
        raise StoreError("Calendario no encontrado")
    url = validar_url(url)
    evs = eventos_de_ics((descargador or descargar)(url))
    with store.tx() as c:
        c.execute("UPDATE calendarios_externos SET origen = 'url' WHERE id = ?", (cal_id,))
    guardar_url(store, cal_id, url)
    return {"id": cal_id, "eventos": _guardar_eventos(store, cal_id, cal["usuario_id"], evs)}


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
        url = leer_url(store, cal["id"])
        if not url:
            continue
        try:
            n = _guardar_eventos(store, cal["id"], usuario_id, eventos_de_ics((descargador or descargar)(url)))
            resultado.append({"id": cal["id"], "eventos": n})
        except StoreError as e:
            _marcar_error(store, cal["id"], str(e))
            resultado.append({"id": cal["id"], "error": str(e)})
    return resultado


def probar(store: Store, cal_id: int, descargador=None) -> int:
    url = leer_url(store, cal_id)
    if not url:
        raise StoreError("Este calendario no tiene dirección guardada")
    return len(eventos_de_ics((descargador or descargar)(url)))


def quitar(store: Store, cal_id: int) -> None:
    f = store.q1("SELECT clave_secreta FROM calendarios_externos WHERE id = ?", (cal_id,))
    if f and f["clave_secreta"]:
        _borrar_secreta(f["clave_secreta"])
    _borrar_secreta(_clave_legado(cal_id))
    with store.tx() as c:
        c.execute("DELETE FROM calendarios_externos WHERE id = ?", (cal_id,))


def eventos(store: Store, usuario_id, desde: str, hasta: str, todos: bool = False) -> list[dict]:
    """Eventos que tocan el rango [desde, hasta] (fechas AAAA-MM-DD) de los calendarios
    visibles (con todos=True, también de los ocultos)."""
    filtro = "" if todos else "AND c.visible = 1"
    return store.q(
        f"""SELECT e.id, e.calendario_id, e.inicio, e.fin, e.todo_el_dia, e.titulo, e.lugar, e.descripcion,
                  c.nombre AS calendario, c.color, c.tipo FROM eventos_externos e
           JOIN calendarios_externos c ON c.id = e.calendario_id
           WHERE e.usuario_id IS ? AND substr(e.inicio, 1, 10) <= ? AND substr(e.fin, 1, 10) >= ? {filtro}
           ORDER BY e.todo_el_dia DESC, e.inicio, e.titulo""", (usuario_id, hasta, desde))
