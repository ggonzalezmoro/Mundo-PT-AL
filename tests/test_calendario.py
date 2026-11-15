"""Calendarios externos (Google Calendar) de solo lectura, con un .ics sintético.
Sin Internet (descarga simulada) y sin tocar el Administrador de credenciales real."""
import datetime as dt
import io

import keyring
import pytest
from keyring.backend import KeyringBackend

from mundoptal import calendario
from mundoptal.servidor import crear_app
from mundoptal.store import StoreError

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Prueba//ES
BEGIN:VTIMEZONE
TZID:Europe/Madrid
BEGIN:STANDARD
DTSTART:19701025T030000
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700329T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:normal@prueba
DTSTART;TZID=Europe/Madrid:20261118T163000
DTEND;TZID=Europe/Madrid:20261118T171500
SUMMARY:Claustro
LOCATION:Sala de profesores
DESCRIPTION:Orden del dia\\, puntos 1 y 2
END:VEVENT
BEGIN:VEVENT
UID:todo-el-dia@prueba
DTSTART;VALUE=DATE:20261120
DTEND;VALUE=DATE:20261122
SUMMARY:Excursion de Infantil
END:VEVENT
BEGIN:VEVENT
UID:semanal@prueba
DTSTART;TZID=Europe/Madrid:20261102T090000
DTEND;TZID=Europe/Madrid:20261102T093000
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=Europe/Madrid:20261116T090000
SUMMARY:Coordinacion PT/AL
END:VEVENT
BEGIN:VEVENT
UID:nueva-york@prueba
DTSTART;TZID=America/New_York:20261119T100000
DTEND;TZID=America/New_York:20261119T110000
SUMMARY:Videollamada
END:VEVENT
BEGIN:VEVENT
UID:utc@prueba
DTSTART:20261123T080000Z
DTEND:20261123T090000Z
SUMMARY:Reunion en UTC
END:VEVENT
BEGIN:VEVENT
UID:cancelado@prueba
DTSTART;TZID=Europe/Madrid:20261124T100000
DTEND;TZID=Europe/Madrid:20261124T110000
STATUS:CANCELLED
SUMMARY:Cancelado
END:VEVENT
END:VCALENDAR
"""
URL = "https://calendar.google.com/calendar/ical/prueba%40group.calendar.google.com/private-0123456789abcdef/basic.ics"


class KeyringMemoria(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.datos = {}

    def get_password(self, s, u):
        return self.datos.get((s, u))

    def set_password(self, s, u, p):
        self.datos[(s, u)] = p

    def delete_password(self, s, u):
        self.datos.pop((s, u), None)


@pytest.fixture(autouse=True)
def keyring_memoria(monkeypatch):
    anterior = keyring.get_keyring()
    keyring.set_keyring(KeyringMemoria())
    monkeypatch.setattr(calendario, "descargar", lambda url: ICS)  # sin Internet
    yield
    keyring.set_keyring(anterior)


def test_parseo_de_eventos_normal_todo_el_dia_recurrente_y_zonas():
    ev = calendario.eventos_de_ics(ICS, hoy=dt.date(2026, 11, 15))
    por_titulo = {}
    for e in ev:
        por_titulo.setdefault(e["titulo"], []).append(e)
    claustro = por_titulo["Claustro"][0]
    assert (claustro["inicio"], claustro["fin"], claustro["lugar"]) == ("2026-11-18T16:30", "2026-11-18T17:15", "Sala de profesores")
    assert claustro["descripcion"] == "Orden del dia, puntos 1 y 2"
    excursion = por_titulo["Excursion de Infantil"][0]
    assert (excursion["inicio"], excursion["fin"], excursion["todo_el_dia"]) == ("2026-11-20", "2026-11-21", 1)
    # Semanal: 4 repeticiones menos la del 16 (EXDATE)
    assert [e["inicio"] for e in por_titulo["Coordinacion PT/AL"]] == ["2026-11-02T09:00", "2026-11-09T09:00", "2026-11-23T09:00"]
    assert por_titulo["Videollamada"][0]["inicio"] == "2026-11-19T16:00"  # 10:00 en Nueva York = 16:00 en Madrid
    assert por_titulo["Reunion en UTC"][0]["inicio"] == "2026-11-23T09:00"
    assert "Cancelado" not in por_titulo
    with pytest.raises(StoreError):
        calendario.eventos_de_ics(b"esto no es un calendario")


def _cliente(tmp_path):
    app = crear_app(tmp_path / "c.db")
    c = app.test_client()
    uid = c.post("/api/usuarios", json={"nombre": "Maestra Prueba", "especialidad": "PT/AL"}).get_json()["id"]
    return app, c, {"X-Usuario": str(uid)}


def test_calendario_por_url_sin_guardar_la_url_en_la_bd(tmp_path):
    app, c, h = _cliente(tmp_path)
    assert c.post("/api/calendarios", json={"nombre": "Cole", "url": "no es una url"}, headers=h).status_code == 400
    r = c.post("/api/calendarios", json={"nombre": "Colegio", "color": "#E67C73", "url": URL}, headers=h).get_json()
    assert r["eventos"] >= 5
    lista = c.get("/api/calendarios", headers=h).get_json()
    assert lista[0]["nombre"] == "Colegio" and lista[0]["tiene_url"] and lista[0]["actualizado"]
    assert "url" not in lista[0] and URL not in str(lista)
    assert calendario.leer_url(lista[0]["id"]) == URL  # está en el almacén de credenciales
    app.extensions["store"].conn.execute("PRAGMA wal_checkpoint(FULL)")
    for f in tmp_path.glob("c.db*"):
        assert b"private-0123456789abcdef" not in f.read_bytes()
    ev = c.get("/api/eventos-externos?desde=2026-11-16&hasta=2026-11-22", headers=h).get_json()
    titulos = [e["titulo"] for e in ev]
    assert titulos[0] == "Excursion de Infantil"  # los de todo el día, primero
    assert "Claustro" in titulos and "Videollamada" in titulos and ev[0]["color"] == "#E67C73"
    assert all(e["titulo"] != "Coordinacion PT/AL" for e in ev)  # el 16 está excluido
    # Actualizar y probar
    assert c.post("/api/calendarios/actualizar", headers=h).get_json()[0]["eventos"] == r["eventos"]
    assert c.post("/api/calendarios/actualizar?si_antiguo_min=30", headers=h).get_json() == []  # recién actualizado
    assert c.post(f"/api/calendarios/{r['id']}/probar", headers=h).get_json()["eventos"] == r["eventos"]
    assert c.patch(f"/api/calendarios_externos/{r['id']}", json={"color": "rojo"}, headers=h).status_code == 400
    # Quitar borra la URL del almacén y los eventos
    c.delete(f"/api/calendarios/{r['id']}", headers=h)
    assert calendario.leer_url(r["id"]) == "" and c.get("/api/eventos-externos?desde=2026-11-01&hasta=2026-12-31", headers=h).get_json() == []


def test_importar_archivo_ics(tmp_path):
    app, c, h = _cliente(tmp_path)
    r = c.post("/api/calendarios/importar", data={"archivo": (io.BytesIO(ICS), "cole.ics"), "nombre": "Exportado", "color": "#33B679"},
               headers=h, content_type="multipart/form-data").get_json()
    assert r["eventos"] >= 5
    cal = c.get("/api/calendarios", headers=h).get_json()[0]
    assert cal["origen"] == "archivo" and not cal["tiene_url"]
    # Volver a importar en el mismo calendario sustituye los eventos (no los duplica)
    c.post("/api/calendarios/importar", data={"archivo": (io.BytesIO(ICS), "cole.ics"), "calendario_id": str(r["id"])},
           headers=h, content_type="multipart/form-data")
    assert c.get("/api/calendarios", headers=h).get_json()[0]["eventos"] == r["eventos"]
