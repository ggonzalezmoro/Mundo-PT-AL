"""Exportar una ACI a Word (.docx) con el formato del colegio, e importar
ACIs ya hechas en Word con ese mismo formato."""
from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .config import ESCALA, ESCALA_TEXTO, static_dir

VERDE_OSCURO = "92D050"
VERDE_CLARO = "C2D69B"
VERDE_SUAVE = "E2EFD9"
AMARILLO = "FFF2CC"

TIPOS = [("significativa", "Adaptación Significativa"),
         ("no_significativa", "Adaptación No Significativa"),
         ("ninguna", "No tiene adaptación")]


# ======================================================================= exportar
def _sombrear(celda, color: str):
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def _texto(celda, texto: str, negrita=False, tam=9, centro=False, color: str | None = None):
    celda.text = ""
    p = celda.paragraphs[0]
    run = p.add_run(texto or "")
    run.bold = negrita
    run.font.size = Pt(tam)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if centro:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def _fila_completa(tabla, texto, color=None, negrita=True, tam=9):
    fila = tabla.add_row()
    celda = fila.cells[0].merge(fila.cells[-1])
    _texto(celda, texto, negrita=negrita, tam=tam)
    if color:
        _sombrear(celda, color)
    return fila


def _anchos(tabla, anchos_cm):
    tabla.autofit = False
    grid = tabla._tbl.tblGrid
    for i, col in enumerate(grid.findall(qn("w:gridCol"))):
        if i < len(anchos_cm):
            col.set(qn("w:w"), str(int(Cm(anchos_cm[i]).twips)))
    for fila in tabla.rows:
        for i, w in enumerate(anchos_cm):
            if i < len(fila.cells):
                fila.cells[i].width = Cm(w)


def _titulo_area(nombre: str) -> str:
    n = (nombre or "").strip()
    if re.match(r"^[áa]rea\b", n, re.I):
        return n
    return f"Área {n}" if n else "Área"


def exportar_aci(aci: dict) -> bytes:
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(1.8))
    sec.top_margin, sec.bottom_margin = Cm(1.5), Cm(1.5)

    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(10)

    logo = static_dir() / "logo.png"
    if logo.exists():
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hp.add_run().add_picture(str(logo), height=Cm(1.6))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(aci.get("titulo") or "INFORME DE EVALUACIÓN TRIMESTRAL")
    r.bold = True
    r.font.size = Pt(12)

    trimestre_txt = f"{aci.get('trimestre', 1)}º Trimestre"
    if aci.get("curso_escolar"):
        trimestre_txt += f" – Curso {aci['curso_escolar']}"
    for etiqueta, valor in (("NOMBRE", aci.get("alumno_nombre", "")),
                            ("CURSO", aci.get("curso", "")),
                            ("FECHA", trimestre_txt)):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(f"{etiqueta}: {valor}")
        r.bold = True
        r.font.size = Pt(9)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("ÁREAS QUE PRECISAN ADAPTACIONES CURRICULARES:").font.size = Pt(9)
    doc.add_paragraph("Tipos de adaptaciones:").runs[0].font.size = Pt(9)

    # ---- Tabla de tipos de adaptaciones
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cab = ["ÁREA", *[n for _, n in TIPOS], "Nivel curricular"]
    for i, c in enumerate(cab):
        _texto(t.rows[0].cells[i], c, negrita=True, centro=True)
        _sombrear(t.rows[0].cells[i], VERDE_SUAVE)
    for ad in aci.get("adaptaciones", []):
        fila = t.add_row().cells
        _texto(fila[0], ad.get("area", ""))
        for i, (clave, _) in enumerate(TIPOS, start=1):
            _texto(fila[i], "X" if ad.get("tipo") == clave else "", centro=True)
        _texto(fila[4], ad.get("nivel_curricular", ""), centro=True, color="FF0000")
    _fila_completa(t, "Propuesta curricular adaptada:")
    fila = _fila_completa(t, "Criterios de evaluación y estándares de aprendizaje:")
    p = fila.cells[0].add_paragraph()
    r = p.add_run("Indicadores de evaluación: ")
    r.font.size = Pt(8)
    for clave in ESCALA:
        rb = p.add_run(f"{clave}: ")
        rb.bold = True
        rb.font.size = Pt(8)
        p.add_run(f"{ESCALA_TEXTO[clave].lower()}  ").font.size = Pt(8)
    _anchos(t, [7.0, 4.5, 4.5, 4.0, 5.5])

    # ---- Propuesta curricular adaptada por áreas
    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(f"ADAPTACIÓN CURRICULAR SIGNIFICATIVA DEL ÁREA/MATERIA: {aci.get('materia', '')}")
    r.bold = True
    r.font.size = Pt(10)

    # Columnas: nº | ítem de evaluación | observaciones | 1T | 2T | 3T
    for ia, area in enumerate(aci.get("areas", []), start=1):
        t = doc.add_table(rows=0, cols=6)
        t.style = "Table Grid"
        if ia == 1:
            _fila_completa(t, "Propuesta curricular adaptada:", VERDE_CLARO)
        _fila_completa(t, _titulo_area(area["nombre"]), VERDE_CLARO)
        fila = t.add_row().cells
        celda = fila[0].merge(fila[1])
        _texto(celda, "TRIMESTRES", negrita=True)
        _texto(fila[2], "OBSERVACIONES", negrita=True, centro=True)
        for i, tt in enumerate(("1T", "2T", "3T"), start=3):
            _texto(fila[i], tt, negrita=True, centro=True)
        n_sub = 0
        for sub in area["subareas"]:
            if sub["nombre"]:
                n_sub += 1
                _fila_completa(t, f"{n_sub}. {sub['nombre']}", VERDE_OSCURO)
            for ic, comp in enumerate(sub["competencias"], start=1):
                fila = t.add_row().cells
                num = f"{n_sub}.{ic}" if sub["nombre"] else str(ic)
                _texto(fila[0], num, negrita=True)
                celda = fila[1].merge(fila[5])
                _texto(celda, f"Competencias y saberes: {comp['nombre']}" if comp["nombre"] else "Competencias y saberes", negrita=True)
                _sombrear(celda, VERDE_CLARO)
                for it in comp["items"]:
                    fila = t.add_row().cells
                    _texto(fila[0], "")
                    _texto(fila[1], it["texto"])
                    if it.get("destacado"):
                        _sombrear(fila[1], AMARILLO)
                    _texto(fila[2], it.get("nota", ""), tam=8)
                    for i, k in enumerate(("eval_1t", "eval_2t", "eval_3t"), start=3):
                        _texto(fila[i], it.get(k, ""), centro=True, negrita=True)
        _anchos(t, [1.1, 12.0, 8.7, 1.4, 1.4, 1.4])
        doc.add_paragraph()

    p = doc.add_paragraph()
    r = p.add_run("+ OBSERVACIONES Y COMENTARIOS")
    r.bold = True
    textos = aci.get("observaciones_familia") or [
        x.strip() for x in (aci.get("observaciones") or "").split("\n") if x.strip()]
    for texto in textos:
        p = doc.add_paragraph(texto)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if aci.get("despedida_familia"):
        doc.add_paragraph().add_run(aci["despedida_familia"]).bold = True
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("PROF. RESPONSABLE DE ÁREA").bold = True
    p.add_run("\t\t\t\t\t")
    p.add_run("PROF. AUDICIÓN Y LENGUAJE/PEDAGOGÍA TERAPÉUTICA").bold = True
    doc.add_paragraph(f"{aci.get('prof_area', '')}\t\t\t\t\t\t\t{aci.get('prof_ptal', '')}")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ======================================================================= importar
PREFIJO_NOTA = "Obs.:"


def _celdas_unicas(fila):
    vistos, out = set(), []
    for c in fila.cells:
        if id(c._tc) in vistos:
            continue
        vistos.add(id(c._tc))
        out.append(c)
    return out


def _relleno(celda) -> str:
    tcPr = celda._tc.tcPr
    if tcPr is None:
        return ""
    shd = tcPr.find(qn("w:shd"))
    return (shd.get(qn("w:fill")) or "").upper() if shd is not None else ""


def _limpio(t: str) -> str:
    return " ".join((t or "").split())


def _es_area(texto: str) -> bool:
    return bool(re.match(r"^[áa]rea\b", texto.strip(), re.I))


def _nombre_area(texto: str) -> str:
    n = re.sub(r"^[áa]rea\s*:?\s*(de\s+(la\s+|las\s+|los\s+)?|del\s+)?", "", texto.strip(), flags=re.I)
    n = n.strip(" :")
    if n.isupper():
        n = n.capitalize()
    return n[:1].upper() + n[1:]


def importar_aci(origen) -> dict:
    """Lee un .docx de ACI y devuelve un diccionario con los datos de la ACI,
    sus adaptaciones y su jerarquía de áreas.

    Admite las variantes reales de los documentos del colegio: tablas dentro de
    controles de contenido, varias áreas en una misma tabla, títulos en negrita
    sin celdas combinadas, columnas de observaciones junto a los ítems, etc."""
    if isinstance(origen, (str, Path)):
        doc = Document(str(origen))
    else:
        doc = Document(io.BytesIO(origen) if isinstance(origen, bytes) else origen)

    res: dict = {"alumno_nombre": "", "curso": "", "curso_escolar": "", "trimestre": 1,
                 "materia": "", "observaciones": "", "prof_area": "", "prof_ptal": "",
                 "adaptaciones": [], "areas": []}

    parrafos = [_limpio(p.text) for p in doc.paragraphs]
    for i, t in enumerate(parrafos):
        u = t.upper()
        if u.startswith("NOMBRE:") and not res["alumno_nombre"]:
            res["alumno_nombre"] = t.split(":", 1)[1].strip()
        elif u.startswith("CURSO:") and not res["curso"]:
            res["curso"] = t.split(":", 1)[1].strip()
        elif u.startswith("FECHA:"):
            _leer_fecha(t.split(":", 1)[1], res)
        elif "ÁREA/MATERIA:" in u:
            res["materia"] = t.split(":", 1)[1].strip()
        elif "OBSERVACIONES" in u and not res["observaciones"]:
            obs = []
            for t2 in parrafos[i + 1:]:
                if t2.upper().startswith("PROF.") or t2.upper().startswith("ADAPTACIONES METODOL"):
                    break
                if t2:
                    obs.append(t2)
            res["observaciones"] = "\n".join(obs)
        elif u.startswith("PROF.") and "RESPONSABLE" in u and not (res["prof_area"] or res["prof_ptal"]):
            _leer_profesores([p.text for p in doc.paragraphs[i:i + 4]], res)
    if not res["curso_escolar"]:
        m = re.search(r"\b(20\d{2})\s*[-/–]\s*(\d{2,4})\b", res["curso"])
        if m:
            res["curso_escolar"] = f"{m.group(1)}/{m.group(2)[-2:]}"
            res["curso"] = _limpio(res["curso"].replace(m.group(0), ""))

    for tabla in _tablas(doc):
        if not tabla.rows:
            continue
        if not (res["prof_area"] or res["prof_ptal"]):
            _profesores_en_tabla(tabla, res)
        cab = " ".join(_limpio(c.text) for c in tabla.rows[0].cells).lower()
        if "adaptación significativa" in cab or "adaptacion significativa" in cab:
            _importar_adaptaciones(tabla, res)
        else:
            _importar_tabla_area(tabla, res)
    res["areas"] = [a for a in res["areas"] if any(c["items"] for s in a["subareas"] for c in s["competencias"])
                    or a["nombre"]]
    _textos_de_etiquetas(doc, res)
    return res


RX_ETIQUETA_CON_TEXTO = re.compile(
    r"^(propuesta curricular adaptada|criterios de evaluaci[óo]n[^:]*)\s*:\s*(.+)$", re.I | re.S)


def _textos_de_etiquetas(doc, res):
    """Algunas ACIs escriben contenido propio tras «Propuesta curricular adaptada:» o
    «Criterios de evaluación…:». La aplicación no tiene un campo para ello, así que se
    conserva en las observaciones de la ACI para no perderlo."""
    extra, vistos = [], set()
    for tc in doc.element.body.iter(qn("w:tc")):
        for p in tc.iter(qn("w:p")):
            t = _limpio("".join(x.text or "" for x in p.iter(qn("w:t"))))
            m = RX_ETIQUETA_CON_TEXTO.match(t)
            if not m:
                continue
            contenido = m.group(2).strip()
            # Solo la leyenda de la escala no es contenido propio
            if not contenido or re.match(r"^indicadores de evaluaci", contenido, re.I) or t in vistos:
                continue
            vistos.add(t)
            extra.append(f"{m.group(1).strip()}: {contenido}")
    if extra:
        previas = [res["observaciones"]] if res["observaciones"] else []
        res["observaciones"] = "\n".join(previas + extra)


def _importar_adaptaciones(tabla, res):
    for i, fila in enumerate(tabla.rows[1:], start=1):
        celdas = fila.cells
        textos = [_limpio(c.text) for c in celdas]
        if len(_celdas_unicas(fila)) < 3:
            continue  # filas combinadas (propuesta / leyenda)
        area = textos[0]
        if not area or RX_SALTAR.match(area) or area.lower().startswith(("área", "area")) and len(textos[0]) < 6:
            continue
        tipo = ""
        for (clave, _), t in zip(TIPOS, textos[1:4]):
            if t.strip().lower() in ("x", "✓", "✔", "sí", "si"):
                tipo = clave
        nivel = " / ".join(_limpio(p.text) for p in celdas[-1].paragraphs if _limpio(p.text))
        res["adaptaciones"].append({"area": area, "tipo": tipo, "nivel_curricular": nivel})


RX_ETIQUETA_PROF = re.compile(
    r"PROF\.?\s*(RESPONSABLE\s+DE\s+(LAS\s+)?[ÁA]REAS?|AUDICI[ÓO]N Y LENGUAJE\s*/\s*PEDAGOG[ÍI]A TERAP[ÉE]UTICA|"
    r"PEDAGOG[ÍI]A TERAP[ÉE]UTICA|AUDICI[ÓO]N Y LENGUAJE|PT\s*/\s*AL|PT|AL)\b\s*:?", re.I)


def _nombre_prof(texto: str) -> str:
    t = _limpio(texto.replace("_", " ")).strip(" :")
    return t


def _leer_profesores(lineas: list[str], res: dict) -> None:
    """Profesores al pie de la ACI. Formatos admitidos:
    «PROF. RESPONSABLE DE LAS ÁREAS: Nombre      PT/AL: Nombre      TÉCNICO: …» o
    una línea de etiquetas y debajo otra con los dos nombres separados por espacios."""
    primera = lineas[0]
    primera = re.split(r"T[ÉE]CNICO", primera, flags=re.I)[0]
    m = re.search(r"RESPONSABLE[^:]*:(.*?)(?:\s{2,}|\t)\s*(?:PROF\.?\s*)?(?:PT\s*/\s*AL|PT|AL)\s*:(.*)$", primera, re.I)
    if m:
        res["prof_area"], res["prof_ptal"] = _nombre_prof(m.group(1)), _nombre_prof(m.group(2))
        return
    # Etiquetas en una línea (a veces con un nombre detrás) y nombres debajo
    sobrante = _nombre_prof(RX_ETIQUETA_PROF.sub(" ", primera))
    nombres = [sobrante] if sobrante else []
    for linea in lineas[1:]:
        if not _limpio(linea) or re.search(r"T[ÉE]CNICO", linea, re.I):
            break
        # «____» cuenta como hueco vacío para no descolocar los nombres
        nombres += [_nombre_prof(x) for x in re.split(r"\t+|\s{3,}", linea.strip()) if x.strip()]
        if any(nombres):
            break
    if any(nombres):
        res["prof_area"] = nombres[0]
        res["prof_ptal"] = nombres[-1] if len(nombres) > 1 else ""


def _profesores_en_tabla(tabla, res: dict) -> None:
    """Pie en forma de tabla: «PROF. RESPONSABLE DE ÁREA⏎Nombre» | «PROF. AUDICIÓN…⏎Nombre»."""
    for fila in tabla.rows:
        for c in _celdas_unicas(fila):
            lineas = [_limpio(x) for x in c.text.split("\n") if _limpio(x)]
            if len(lineas) < 2 or not lineas[0].upper().startswith("PROF"):
                continue
            nombre = _nombre_prof(" ".join(lineas[1:]))
            if "RESPONSABLE" in lineas[0].upper():
                res["prof_area"] = res["prof_area"] or nombre
            else:
                res["prof_ptal"] = res["prof_ptal"] or nombre


MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def _leer_fecha(texto: str, res: dict) -> None:
    """«1º trimestre 2026-2027», «Diciembre 2026», «Octubre de 2026»…"""
    m = re.search(r"(\d)\s*º?\s*(trimestre|t\b)", texto, re.I)
    if m:
        res["trimestre"] = max(1, min(3, int(m.group(1))))
    m = re.search(r"\b(20\d{2})\s*[-/–]\s*(\d{2,4})\b", texto)
    if m:
        res["curso_escolar"] = f"{m.group(1)}/{m.group(2)[-2:]}"
        return
    bajo = texto.lower()
    mes = next((n for nombre, n in MESES.items() if nombre in bajo), None)
    anio = re.search(r"\b(20\d{2})\b", texto)
    if mes and anio:
        a = int(anio.group(1))
        inicio = a if mes >= 9 else a - 1
        res["curso_escolar"] = f"{inicio}/{str(inicio + 1)[-2:]}"
        if not m and not re.search(r"trimestre", bajo):
            res["trimestre"] = 1 if mes >= 9 else (2 if mes <= 3 else 3)


def _tablas(doc):
    """Tablas del documento en orden, también las que están dentro de controles
    de contenido (que python-docx no devuelve en doc.tables)."""
    from docx.table import Table
    for el in doc.element.body.iter(qn("w:tbl")):
        padre = el.getparent()
        anidada = False
        while padre is not None:
            if padre.tag == qn("w:tbl"):
                anidada = True
                break
            padre = padre.getparent()
        if not anidada:
            yield Table(el, doc)


RX_COMPETENCIA = re.compile(
    r"^(competencias?(\s+espec[ií]ficas?)?(\s+y\s+saberes)?|objetivos?\s+general(es)?)\s*[:|\-–]?\s*", re.I)
RX_SALTAR = re.compile(
    r"^(propuesta curricular|propuesta de trabajo|criterios de evaluaci|indicadores de evaluaci|trimestres?\b|prof\.)",
    re.I)
RX_NUMERO = re.compile(r"^\d+(\.\d+)*\.?$")
RX_TRIMESTRE = re.compile(r"^\d\s*º?\s*T?$", re.I)
AREAS_PRINCIPALES = ("comunicación", "comunicacion", "crecimiento en armon", "descubrimiento", "camino de las letras",
                     "música", "musica", "inglés", "ingles", "lengua extranjera", "funciones ejecutivas",
                     "atención y funciones", "teoría de la mente", "teoria de la mente")


def _negrita(celda) -> bool:
    runs = [r for p in celda.paragraphs for r in p.runs if r.text.strip()]
    return bool(runs) and all(r.bold or (r.style is not None and r.style.font.bold) for r in runs)


def _es_area_principal(texto: str) -> bool:
    nombre = _nombre_area(texto).lower() if _es_area(texto) else texto.lower()
    return any(nombre.startswith(k) for k in AREAS_PRINCIPALES) or (
        _es_area(texto) and any(k in nombre for k in AREAS_PRINCIPALES))


def _importar_tabla_area(tabla, res):
    area = None
    sub = None
    comp = None
    posicional = False  # la tabla tiene cabecera 1T / 2T / 3T
    trimestre = res.get("trimestre", 1) or 1

    def nueva_area(nombre):
        nonlocal area, sub, comp
        nombre = (_nombre_area(nombre) if _es_area(nombre) else nombre).strip()
        if nombre.isupper():
            nombre = nombre.capitalize()
        area = {"nombre": nombre, "especialidad": "", "subareas": []}
        bajo = nombre.lower()
        if "comunicaci" in bajo or "audici" in bajo or "lenguaje" in bajo:
            area["especialidad"] = "AL"
        res["areas"].append(area)
        sub = comp = None

    def nueva_sub(nombre):
        nonlocal sub, comp
        if area is None:
            nueva_area("")
        sub = {"nombre": nombre, "competencias": []}
        area["subareas"].append(sub)
        comp = None

    def nueva_comp(nombre):
        nonlocal comp
        if sub is None:
            nueva_sub("")
        comp = {"nombre": nombre, "items": []}
        sub["competencias"].append(comp)

    for fila in tabla.rows:
        celdas = _celdas_unicas(fila)
        textos = [_limpio(c.text) for c in celdas]
        if not any(textos):
            continue
        if any(RX_TRIMESTRE.match(t) for t in textos) and sum(bool(RX_TRIMESTRE.match(t)) for t in textos) >= 2:
            posicional = True
        # Primera celda con texto (sin contar numeraciones, evaluaciones ni cabeceras 1T/2T/3T)
        idx = next((k for k, t in enumerate(textos)
                    if t and not RX_NUMERO.match(t) and not RX_TRIMESTRE.match(t)
                    and t.upper().replace(" ", "") not in ESCALA), None)
        if idx is None:
            continue
        texto = textos[idx]
        nota_propia = ""
        parrafos = [_limpio(p.text) for p in celdas[idx].paragraphs if _limpio(p.text)]
        if len(parrafos) > 1 and parrafos[-1].startswith(PREFIJO_NOTA):
            # Observación exportada por la propia aplicación (segundo párrafo «Obs.: …»)
            nota_propia = parrafos[-1][len(PREFIJO_NOTA):].strip()
            texto = " ".join(parrafos[:-1])
        if RX_SALTAR.match(texto):
            continue
        resto = textos[idx + 1:]
        evals = [t.upper().replace(" ", "") for t in resto]
        tiene_eval = any(e in ESCALA for e in evals)
        es_ultima = idx == len(celdas) - 1
        es_titulo = not tiene_eval and (es_ultima or (not any(resto) and _negrita(celdas[idx]))
                                        or bool(RX_COMPETENCIA.match(texto)))
        if es_titulo:
            sin_num = re.sub(r"^\d+(\.\d+)*\.?\s+", "", texto)
            if RX_COMPETENCIA.match(sin_num):
                nueva_comp(RX_COMPETENCIA.sub("", sin_num).strip(" :|"))
            elif re.match(r"^bloque\b", sin_num, re.I):
                nueva_sub(sin_num)
            elif _es_area_principal(sin_num) or area is None:
                nueva_area(sin_num)
            elif len(celdas) == 1 or _es_area(sin_num) or sin_num.isupper():
                nueva_sub(sin_num)
            else:
                nueva_comp(sin_num)
            continue
        # Ítem
        if area is None:
            continue
        if comp is None:
            nueva_comp("")
        if posicional:
            ev = evals[-3:] if len(evals) >= 3 else evals + [""] * (3 - len(evals))
            ev = [e if e in ESCALA else "" for e in ev]
        else:
            # Sin cabecera de trimestres: la evaluación que haya es la del trimestre del documento
            valor = next((e for e in evals if e in ESCALA), "")
            ev = ["", "", ""]
            ev[trimestre - 1] = valor
        # Columna de observaciones junto al ítem (textos que no son evaluaciones)
        notas = [t for t, e in zip(resto, evals) if t and e not in ESCALA and not RX_NUMERO.match(t)]
        if nota_propia:
            notas.insert(0, nota_propia)
        comp["items"].append({
            "texto": texto,
            "nota": " · ".join(notas),
            "eval_1t": ev[0], "eval_2t": ev[1], "eval_3t": ev[2],
            "destacado": _relleno(celdas[idx]) == AMARILLO,
        })
