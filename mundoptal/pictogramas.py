"""Pictogramas de ARASAAC (https://arasaac.org) con caché en el equipo.

Se buscan por palabra clave con su API pública y se guardan en
Documents\\Mundo PT-AL\\Pictogramas, así cada pictograma solo se descarga una vez.
Si no hay Internet o no se encuentra, se devuelve None y la ficha usa un emoji o
un hueco para dibujar.

Licencia: los pictogramas son de Sergio Palao, propiedad del Gobierno de Aragón,
con licencia CC BY-NC-SA. Todo material que los use lleva el pie ATRIBUCION."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .material import sin_tildes

ATRIBUCION = ("Pictogramas: Sergio Palao. Origen: ARASAAC (http://www.arasaac.org). "
              "Licencia: CC (BY-NC-SA). Propiedad: Gobierno de Aragón (España)")
URL_BUSQUEDA = "https://api.arasaac.org/v1/pictograms/es/search/{}"
URL_IMAGEN = "https://static.arasaac.org/pictograms/{id}/{id}_500.png"
TIEMPO = 6  # segundos por petición

_no_encontrados: set[str] = set()


def _nombre_archivo(palabra: str) -> str:
    return re.sub(r"[^a-z0-9ñ]+", "_", sin_tildes(palabra.lower()).strip()).strip("_") or "x"


def obtener(palabra: str, carpeta: Path, descargar: bool = True) -> Path | None:
    """Ruta a la imagen PNG del pictograma, descargándolo si hace falta y se permite."""
    palabra = (palabra or "").strip()
    if not palabra:
        return None
    ruta = carpeta / f"{_nombre_archivo(palabra)}.png"
    if ruta.exists() and ruta.stat().st_size > 0:
        return ruta
    if not descargar or palabra.lower() in _no_encontrados:
        return None
    try:
        with urllib.request.urlopen(URL_BUSQUEDA.format(urllib.parse.quote(palabra.lower())), timeout=TIEMPO) as r:
            resultados = json.loads(r.read().decode("utf-8"))
        if not resultados:
            raise LookupError(palabra)
        # Mejor el pictograma cuya palabra clave coincide exactamente («lengua», no «lengua de gato»)
        buscada = sin_tildes(palabra.lower()).strip()
        exacto = next((x for x in resultados if any(sin_tildes((k.get("keyword") or "").lower()).strip() == buscada
                                                     for k in x.get("keywords", []))), None)
        pid = int((exacto or resultados[0])["_id"])
        with urllib.request.urlopen(URL_IMAGEN.format(id=pid), timeout=TIEMPO) as r:
            datos = r.read()
        if not datos.startswith(b"\x89PNG"):
            raise LookupError(palabra)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
        return ruta
    except Exception:  # sin Internet, sin resultados o respuesta inesperada: se usa la reserva
        _no_encontrados.add(palabra.lower())
        return None
