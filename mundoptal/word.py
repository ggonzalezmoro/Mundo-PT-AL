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

    for ia, area in enumerate(aci.get("areas", []), start=1):
        t = doc.add_table(rows=0, cols=5)
        t.style = "Table Grid"
        if ia == 1:
            _fila_completa(t, "Propuesta curricular adaptada:", VERDE_CLARO)
        _fila_completa(t, _titulo_area(area["nombre"]), VERDE_CLARO)
        fila = t.add_row().cells
        celda = fila[0].merge(fila[1])
        _texto(celda, "TRIMESTRES", negrita=True)
        for i, tt in enumerate(("1T", "2T", "3T"), start=2):
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
                celda = fila[1].merge(fila[4])
                _texto(celda, f"Competencias y saberes: {comp['nombre']}" if comp["nombre"] else "Competencias y saberes", negrita=True)
                _sombrear(celda, VERDE_CLARO)
                for it in comp["items"]:
                    fila = t.add_row().cells
                    _texto(fila[0], "")
                    _texto(fila[1], it["texto"])
                    if it.get("destacado"):
                        _sombrear(fila[1], AMARILLO)
                    for i, k in enumerate(("eval_1t", "eval_2t", "eval_3t"), start=2):
                        _texto(fila[i], it.get(k, ""), centro=True, negrita=True)
        _anchos(t, [1.3, 18.5, 2.0, 2.0, 2.0])
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
    n = re.sub(r"^[áa]rea\s+(de\s+(la\s+|las\s+|los\s+)?|del\s+)?", "", texto.strip(), flags=re.I)
    n = n.strip(" :")
    if n.isupper():
        n = n.capitalize()
    return n[:1].upper() + n[1:]


def importar_aci(origen) -> dict:
    """Lee un .docx con el formato del colegio y devuelve un diccionario con
    los datos de la ACI, sus adaptaciones y su jerarquía de áreas."""
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
        if u.startswith("NOMBRE:"):
            res["alumno_nombre"] = t.split(":", 1)[1].strip()
        elif u.startswith("CURSO:"):
            res["curso"] = t.split(":", 1)[1].strip()
        elif u.startswith("FECHA:"):
            m = re.search(r"(\d)\s*º?\s*trimestre", t, re.I)
            if m:
                res["trimestre"] = max(1, min(3, int(m.group(1))))
            m = re.search(r"(\d{4}\s*[-/–]\s*\d{2,4})", t)
            if m:
                res["curso_escolar"] = re.sub(r"\s", "", m.group(1)).replace("–", "-")
        elif "ÁREA/MATERIA:" in u:
            res["materia"] = t.split(":", 1)[1].strip()
        elif "OBSERVACIONES" in u:
            obs = []
            for t2 in parrafos[i + 1:]:
                if t2.upper().startswith("PROF."):
                    break
                if t2:
                    obs.append(t2)
            res["observaciones"] = "\n".join(obs)
        elif u.startswith("PROF.") and "RESPONSABLE" in u:
            for j in range(i + 1, len(parrafos)):
                if parrafos[j]:
                    raw = doc.paragraphs[j].text
                    partes = [x.strip() for x in re.split(r"\t+|\s{3,}", raw) if x.strip()]
                    if partes:
                        res["prof_area"] = partes[0]
                        res["prof_ptal"] = partes[-1] if len(partes) > 1 else ""
                    break

    for tabla in doc.tables:
        if not tabla.rows:
            continue
        cab = " ".join(_limpio(c.text) for c in tabla.rows[0].cells).lower()
        if "adaptación significativa" in cab or "adaptacion significativa" in cab:
            _importar_adaptaciones(tabla, res)
        else:
            _importar_tabla_area(tabla, res)
    return res


def _importar_adaptaciones(tabla, res):
    for i, fila in enumerate(tabla.rows[1:], start=1):
        celdas = fila.cells
        textos = [_limpio(c.text) for c in celdas]
        if len(_celdas_unicas(fila)) < 3:
            continue  # filas combinadas (propuesta / leyenda)
        area = textos[0]
        if not area:
            continue
        tipo = ""
        for (clave, _), t in zip(TIPOS, textos[1:4]):
            if t.strip().lower() in ("x", "✓", "✔", "sí", "si"):
                tipo = clave
        nivel = " / ".join(_limpio(p.text) for p in celdas[-1].paragraphs if _limpio(p.text))
        res["adaptaciones"].append({"area": area, "tipo": tipo, "nivel_curricular": nivel})


def _importar_tabla_area(tabla, res):
    area = None
    sub = None
    comp = None

    def nueva_sub(nombre):
        nonlocal sub, comp
        sub = {"nombre": nombre, "competencias": []}
        area["subareas"].append(sub)
        comp = None

    for fila in tabla.rows:
        celdas = _celdas_unicas(fila)
        textos = [_limpio(c.text) for c in celdas]
        no_vacios = [t for t in textos if t]
        if not no_vacios:
            continue
        primero = no_vacios[0]
        bajo = primero.lower()
        if bajo.startswith("propuesta curricular") or bajo.startswith("trimestres"):
            continue
        comp_txt = next((t for t in textos if t.lower().startswith("competencias y saberes")), None)
        if comp_txt is not None:
            if area is None:
                area = {"nombre": "", "especialidad": "", "subareas": []}
                res["areas"].append(area)
            if sub is None:
                nueva_sub("")
            nombre = comp_txt.split(":", 1)[1].strip() if ":" in comp_txt else ""
            comp = {"nombre": nombre, "items": []}
            sub["competencias"].append(comp)
            continue
        if len(no_vacios) == 1 and len(celdas) <= 2 and not re.fullmatch(r"[\d.]+", primero):
            # Fila de título (combinada): área o subárea
            nombre = re.sub(r"^\d+(\.\d+)*\.?\s*", "", primero)
            if area is None:
                area = {"nombre": _nombre_area(nombre) if _es_area(nombre) else nombre,
                        "especialidad": "", "subareas": []}
                if "comunicaci" in nombre.lower() or "audici" in nombre.lower() or "lenguaje" in nombre.lower():
                    area["especialidad"] = "AL"
                res["areas"].append(area)
            else:
                nueva_sub(nombre)
            continue
        # Fila de ítem: celda de texto más larga + tres últimas de evaluación
        if area is None:
            continue
        if sub is None:
            nueva_sub("")
        if comp is None:
            comp = {"nombre": "", "items": []}
            sub["competencias"].append(comp)
        idx_texto = max(range(len(celdas)), key=lambda k: len(textos[k]))
        texto = textos[idx_texto]
        if not texto or texto in ESCALA:
            continue
        evals = [t.upper().replace(" ", "") for t in textos[idx_texto + 1:]][-3:]
        evals = [e if e in ESCALA else "" for e in evals] + [""] * (3 - len(evals))
        comp["items"].append({
            "texto": texto,
            "eval_1t": evals[0], "eval_2t": evals[1], "eval_3t": evals[2],
            "destacado": _relleno(celdas[idx_texto]) == AMARILLO,
        })
