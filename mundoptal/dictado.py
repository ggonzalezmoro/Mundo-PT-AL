"""Traduce el texto dictado por el maestro a la jerarquía de la ACI.

El maestro dicta usando palabras clave al principio de cada elemento:

    "Área comunicación y representación de la realidad.
     Subárea área preverbal.
     Competencia desarrollar la atención.
     Ítem mantiene la mirada en el objeto. Ítem señala el objeto que se le pide."

Reglas:
  * Palabras clave: «área», «subárea» (o «sub área»), «competencia»
    (también «competencias y saberes») e «ítem».
  * Se pueden anteponer «nueva», «nuevo», «otra», «otro» o «siguiente».
  * Una palabra clave precedida de artículo o preposición («el área», «la
    competencia», «de área»…) se considera texto normal, no una orden.
  * Tras «ítem» (o «ítems»), cada frase separada por punto, punto y coma,
    salto de línea o la palabra «punto» se convierte en un ítem distinto.
  * Lo que se dicte sin nivel superior se coloca en el área/subárea/
    competencia que esté seleccionada en la aplicación.
"""
from __future__ import annotations

import re
import unicodedata

AREA, SUBAREA, COMPETENCIA, ITEM, SEP = "area", "subarea", "competencia", "item", "sep"

PREFIJOS = {"nueva", "nuevo", "otra", "otro", "siguiente", "nuevas", "nuevos"}
# Si una palabra clave va justo detrás de una de estas palabras, es texto normal
NO_CLAVE_TRAS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "del", "de", "al", "su", "sus",
    "esta", "este", "estas", "estos", "cada", "por", "en", "con", "mi", "tu", "sin", "que",
}
PALABRAS_SEPARADORAS = {"punto"}  # «punto» (y «punto y aparte» / «punto y seguido»)

_TOKEN_RE = re.compile(r"\n|[.;]+(?=\s|$)|[^\s.;]+(?:\.[^\s.;]+)*|[.;]")


def _norm(palabra: str) -> str:
    t = unicodedata.normalize("NFKD", palabra)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().strip(",:¿?¡!\"'«»()")


def _clave(n: str) -> str | None:
    if n in ("area", "areas"):
        return AREA
    if n in ("subarea", "subareas", "sub-area"):
        return SUBAREA
    if n in ("competencia", "competencias"):
        return COMPETENCIA
    if n in ("item", "items", "itens", "ítem"):
        return ITEM
    return None


def tokenizar(texto: str) -> list[tuple[str, str]]:
    """Devuelve [(tipo, palabra_original)], tipo ∈ {area, subarea, competencia, item, sep, txt}."""
    crudos = _TOKEN_RE.findall(texto or "")
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(crudos):
        w = crudos[i]
        n = _norm(w)
        if w == "\n" or re.fullmatch(r"[.;]+", w):
            out.append((SEP, w))
            i += 1
            continue
        # «punto», «punto y aparte», «punto y seguido», «nueva línea»
        if n in PALABRAS_SEPARADORAS:
            sig = [_norm(x) for x in crudos[i + 1:i + 3]]
            if len(sig) == 2 and sig[0] == "y" and sig[1] in ("aparte", "seguido"):
                i += 3
            else:
                i += 1
            out.append((SEP, "."))
            continue
        if n in ("nueva", "nuevo") and i + 1 < len(crudos) and _norm(crudos[i + 1]) == "linea":
            out.append((SEP, "\n"))
            i += 2
            continue
        # «sub área» en dos palabras
        if n == "sub" and i + 1 < len(crudos) and _norm(crudos[i + 1]) in ("area", "areas"):
            out.append((SUBAREA, w + " " + crudos[i + 1]))
            i += 2
            continue
        clave = _clave(n)
        out.append((clave or "txt", w))
        i += 1
    return out


def _limpiar_nombre(palabras: list[str], nivel: str) -> str:
    texto = " ".join(palabras).strip(" ,:-")
    # Numeración dictada o escrita («1.1», «3.», «1)»)
    texto = re.sub(r"^\(?\d+(?:[.,]\d+)*[.)]?\s+", "", texto)
    if nivel == COMPETENCIA:
        texto = re.sub(r"^(y\s+saberes)\s*[:,]?\s*", "", texto, flags=re.I)
    texto = texto.strip(" ,:-")
    if not texto:
        return ""
    texto = texto[0].upper() + texto[1:]
    if nivel == ITEM:
        texto = texto.rstrip(" ,")
        if texto[-1] not in ".!?…":
            texto += "."
    return texto


def analizar(texto: str) -> dict:
    """Convierte un dictado en un árbol:

    {"areas": [{"nombre", "subareas": [{"nombre", "competencias": [{"nombre", "items": [str]}]}]}],
     "avisos": [str], "totales": {...}}

    Los nombres vacíos ("") significan «usar el elemento seleccionado / sin nombre».
    """
    tokens = tokenizar(texto)
    areas: list[dict] = []
    avisos: list[str] = []

    def area_actual():
        if not areas:
            areas.append({"nombre": "", "subareas": []})
        return areas[-1]

    def sub_actual():
        a = area_actual()
        if not a["subareas"]:
            a["subareas"].append({"nombre": "", "competencias": []})
        return a["subareas"][-1]

    def comp_actual():
        s = sub_actual()
        if not s["competencias"]:
            s["competencias"].append({"nombre": "", "items": []})
        return s["competencias"][-1]

    modo: str | None = None      # nivel que se está rellenando
    buffer: list[str] = []
    previo_norm = ""             # palabra anterior normalizada
    tras_sep = True

    def cerrar():
        nonlocal buffer
        if modo is None:
            if any(w.strip() for w in buffer):
                avisos.append(
                    "Texto sin palabra clave al inicio, se ha tratado como ítem: «%s»" % " ".join(buffer)
                )
                _añadir(ITEM, buffer)
        else:
            _añadir(modo, buffer)
        buffer = []

    def _añadir(nivel, palabras):
        nombre = _limpiar_nombre(palabras, nivel)
        if nivel == AREA:
            nombre = re.sub(r"^(de|del)\s+", "", nombre, flags=re.I)
            nombre = nombre[:1].upper() + nombre[1:]
            areas.append({"nombre": nombre, "subareas": []})
        elif nivel == SUBAREA:
            area_actual()["subareas"].append({"nombre": nombre, "competencias": []})
        elif nivel == COMPETENCIA:
            sub_actual()["competencias"].append({"nombre": nombre, "items": []})
        elif nivel == ITEM and nombre:
            comp_actual()["items"].append(nombre)

    for tipo, w in tokens:
        n = _norm(w)
        if tipo == SEP:
            if buffer:
                cerrar()
            # Tras cerrar un nombre o un ítem, la siguiente frase sin palabra
            # clave se considera un ítem del último elemento.
            if modo is not None:
                modo = ITEM
            tras_sep = True
            previo_norm = ""
            continue

        es_clave = tipo in (AREA, SUBAREA, COMPETENCIA, ITEM)
        if es_clave and not tras_sep and previo_norm in NO_CLAVE_TRAS:
            es_clave = False
        # «subárea área preverbal»: el «área» forma parte del nombre
        if es_clave and tipo == AREA and modo == SUBAREA and not buffer:
            es_clave = False
        # «competencias y saberes»: ya es la palabra clave
        if es_clave:
            # quitar prefijos «nueva», «otro»… que quedaron en el buffer
            while buffer and _norm(buffer[-1]) in PREFIJOS:
                buffer.pop()
            if buffer or modo is not None:
                cerrar()
            modo = tipo
            buffer = []
        else:
            buffer.append(w)
        tras_sep = False
        previo_norm = n

    if buffer:
        cerrar()

    # Limpiar elementos vacíos sin contenido (p. ej. «competencia» sin ítems ni nombre)
    for a in areas:
        for s in a["subareas"]:
            s["competencias"] = [c for c in s["competencias"] if c["nombre"] or c["items"]]
        a["subareas"] = [s for s in a["subareas"] if s["nombre"] or s["competencias"]]
    areas[:] = [a for a in areas if a["nombre"] or a["subareas"]]

    totales = {"areas": 0, "subareas": 0, "competencias": 0, "items": 0}
    for a in areas:
        totales["areas"] += bool(a["nombre"])
        for s in a["subareas"]:
            totales["subareas"] += bool(s["nombre"])
            for c in s["competencias"]:
                totales["competencias"] += bool(c["nombre"])
                totales["items"] += len(c["items"])
                if not c["items"]:
                    avisos.append(f"La competencia «{c['nombre']}» no tiene ítems.")
    return {"areas": areas, "avisos": avisos, "totales": totales}
