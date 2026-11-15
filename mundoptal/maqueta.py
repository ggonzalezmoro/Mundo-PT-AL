"""Maquetación del material (MaterialSpec) en Word (fichas para imprimir) y en
PowerPoint (diapositivas para proyectar), siempre con el estilo del colegio:
cabecera con el logo y la maestra, una actividad por página, enunciado corto
arriba y pie con el colegio (y la atribución de ARASAAC si hay pictogramas)."""
from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import pictogramas
from .config import COLEGIO, static_dir
from .material import MaterialSpec, Pagina, emoji_de

VERDE = RGBColor(0x14, 0x68, 0x34)
LIMA = RGBColor(0x73, 0xBA, 0x1A)
GRIS = RGBColor(0x6B, 0x75, 0x6E)
GRIS_REPASO = RGBColor(0xC4, 0xC9, 0xC2)
LETRA = "Arial"
EMOJI_FUENTE = "Segoe UI Emoji"


@dataclass
class Recursos:
    """Lo que la maqueta necesita del entorno (todo local salvo la descarga de pictogramas)."""
    carpeta_pictos: Path | None = None
    descargar_pictos: bool = True
    logo: Path | None = None
    cabecera: str = ""
    alumno: str = ""
    usados_pictos: bool = field(default=False)

    def imagen(self, palabra: str):
        """("img", ruta) | ("emoji", texto) | ("hueco", None)."""
        if palabra and self.carpeta_pictos is not None:
            ruta = pictogramas.obtener(palabra, self.carpeta_pictos, self.descargar_pictos)
            if ruta:
                self.usados_pictos = True
                return "img", ruta
        e = emoji_de(palabra)
        if e:
            return "emoji", e
        return ("hueco", None) if palabra else (None, None)

    def ruta_logo(self) -> Path | None:
        if self.logo and Path(self.logo).exists():
            return Path(self.logo)
        for nombre in ("logo_fichas.png", "logo.png"):  # logo de la web del colegio (alta resolución) o el pequeño
            defecto = static_dir() / nombre
            if defecto.exists():
                return defecto
        return None


def _mezclar(lista, semilla):
    """Desordena siempre (en «unir», la columna de la derecha nunca queda en el mismo orden)."""
    copia = list(lista)
    random.Random(semilla).shuffle(copia)
    if len(copia) > 1 and copia == list(lista):
        copia = copia[1:] + copia[:1]
    return copia


# ====================================================================== WORD
def _sin_bordes(tabla):
    tblPr = tabla._tbl.tblPr
    bordes = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{lado}")
        b.set(qn("w:val"), "nil")
        bordes.append(b)
    tblPr.append(bordes)


def _bordes_celda(celda, color="146834", grosor=12, estilo="single"):
    tcPr = celda._tc.get_or_add_tcPr()
    bordes = OxmlElement("w:tcBorders")
    for lado in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{lado}")
        b.set(qn("w:val"), estilo)
        b.set(qn("w:sz"), str(grosor))
        b.set(qn("w:color"), color)
        bordes.append(b)
    tcPr.append(bordes)


def _run(p, texto, tam=14, negrita=False, color=None, fuente=LETRA, hueco=False):
    r = p.add_run(texto)
    r.font.size = Pt(tam)
    r.font.bold = negrita
    r.font.name = fuente
    r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), fuente)
    if color is not None:
        r.font.color.rgb = color
    if hueco:
        r.font.outline = True
    return r


def _centro(p):
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    return p


def _poner_imagen(p, rec: Recursos, palabra: str, alto_cm: float, texto_si_no=""):
    """Pictograma, emoji o hueco para dibujar en un párrafo."""
    tipo, valor = rec.imagen(palabra)
    if tipo == "img":
        p.add_run().add_picture(str(valor), height=Cm(alto_cm))
    elif tipo == "emoji":
        _run(p, valor, tam=int(alto_cm * 26), fuente=EMOJI_FUENTE)
    elif tipo == "hueco":
        _run(p, "☐", tam=int(alto_cm * 28), color=GRIS_REPASO)
    elif texto_si_no:
        _run(p, texto_si_no, tam=int(alto_cm * 20), negrita=True)


def _celda_elemento(celda, rec, e, alto=3.0, tam_texto=22, mostrar_texto=True):
    celda.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = _centro(celda.paragraphs[0])
    if e.pictograma:
        _poner_imagen(p, rec, e.pictograma, alto)
        if mostrar_texto and e.texto:
            _run(_centro(celda.add_paragraph()), e.texto, tam=tam_texto, negrita=True)
    else:
        _run(p, e.texto, tam=int(tam_texto * 2.2), negrita=True)


def _tabla(doc, filas, cols, ancho_cm=17.0):
    t = doc.add_table(rows=filas, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for fila in t.rows:
        for c in fila.cells:
            c.width = Cm(ancho_cm / cols)
    return t


def _rejilla(doc, rec, elementos, cols=3, alto=2.8, tam=20, bordes=True, mostrar_texto=True):
    filas = (len(elementos) + cols - 1) // cols
    t = _tabla(doc, filas, cols)
    _sin_bordes(t)
    for fila in t.rows:
        fila.height = Cm(alto + (1.6 if mostrar_texto and any(e.pictograma for e in elementos) else 1.0))
        fila.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    for i, e in enumerate(elementos):
        c = t.cell(i // cols, i % cols)
        if bordes:
            _bordes_celda(c, color="C2D69B", grosor=10)
        _celda_elemento(c, rec, e, alto, tam, mostrar_texto)
    return t


def _pagina_docx(doc, rec: Recursos, pg: Pagina, indice: int):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(14)
    _run(p, pg.enunciado, tam=22, negrita=True, color=VERDE)
    els = pg.elementos
    a = pg.actividad
    if a == "letra":
        p = _centro(doc.add_paragraph())
        _run(p, pg.destacado, tam=150 if len(pg.destacado) <= 4 else 80, negrita=True, color=VERDE)
        p = _centro(doc.add_paragraph())
        _run(p, pg.destacado, tam=150 if len(pg.destacado) <= 4 else 80, negrita=True, hueco=True)
        if els and any(e.pictograma for e in els):
            _rejilla(doc, rec, els[:4], cols=min(4, len(els)), alto=2.4, tam=16, bordes=False)
        elif els and els[0].cantidad:
            _run(_centro(doc.add_paragraph()), "⭐" * els[0].cantidad, tam=36, fuente=EMOJI_FUENTE)
    elif a == "repasar":
        tokens = (pg.destacado or "").split()[:2] or [""]
        filas = 3 if len(tokens) > 1 else 5
        tam = 60 if max(len(t) for t in tokens) <= 2 else 40
        copias = 4 if max(len(t) for t in tokens) <= 2 else 2
        for token in tokens:
            for _ in range(filas):
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.keep_together = True
                _run(p, token + "   ", tam=tam, negrita=True, color=VERDE)
                _run(p, "   ".join([token] * copias), tam=tam, color=GRIS_REPASO)
        for e in els:
            p = doc.add_paragraph()
            _run(p, e.texto + "   ", tam=36, negrita=True)
            _run(p, e.texto, tam=36, color=GRIS_REPASO)
    elif a == "frase":
        for frase in _frases(els):
            # Ancho de cada palabra según su longitud, y filas de hasta 17 cm (sin partir palabras)
            ancho = lambda e: max(2.4 if e.pictograma else 1.4, len(e.texto) * 0.55 + 0.4)  # noqa: E731
            trozos, actual, suma = [], [], 0.0
            for e in frase:
                if actual and suma + ancho(e) > 17.0:
                    trozos.append(actual)
                    actual, suma = [], 0.0
                actual.append(e)
                suma += ancho(e)
            if actual:
                trozos.append(actual)
            for trozo in trozos:
                t = _tabla(doc, 2, len(trozo), ancho_cm=sum(ancho(e) for e in trozo))
                _sin_bordes(t)
                for j, e in enumerate(trozo):
                    for fila in t.rows:
                        fila.cells[j].width = Cm(ancho(e))
                    t.columns[j].width = Cm(ancho(e))
                    p = _centro(t.cell(0, j).paragraphs[0])
                    t.cell(0, j).vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
                    tipo, valor = rec.imagen(e.pictograma) if e.pictograma else (None, None)
                    if tipo == "img":
                        p.add_run().add_picture(str(valor), height=Cm(2.2))
                    elif tipo == "emoji":
                        _run(p, valor, tam=48, fuente=EMOJI_FUENTE)
                    _run(_centro(t.cell(1, j).paragraphs[0]), e.texto, tam=20, negrita=bool(e.pictograma))
            doc.add_paragraph().paragraph_format.space_after = Pt(10)
    elif a in ("rodear", "pregunta"):
        if a == "pregunta" and any(e.grupo in ESPACIALES for e in els):
            _espaciales_docx(doc, rec, els)
        else:
            if a == "pregunta" and pg.destacado:  # modelo (p. ej. la palabra con la que tiene que rimar)
                p = _centro(doc.add_paragraph())
                _poner_imagen(p, rec, pg.destacado, 3.2)
                _run(_centro(doc.add_paragraph()), pg.destacado.upper(), tam=26, negrita=True, color=VERDE)
            cols = 3 if len(els) <= 9 else 4
            if a == "pregunta" and len(els) <= 4:
                cols = len(els) or 1
            _rejilla(doc, rec, els, cols=cols, alto=3.0 if len(els) <= 6 else 2.2, tam=18)
    elif a == "unir":
        derecha = _mezclar(els, indice)
        t = _tabla(doc, len(els), 5)
        _sin_bordes(t)
        anchos = [5.0, 1.0, 5.0, 1.0, 5.0]
        for i, (izq, der) in enumerate(zip(els, derecha)):
            fila = t.rows[i].cells
            for c, w in zip(fila, anchos):
                c.width = Cm(w)
            _celda_elemento(fila[0], rec, izq, 2.4, 20)
            _run(_centro(fila[1].paragraphs[0]), "●", tam=22, color=VERDE)
            _run(_centro(fila[3].paragraphs[0]), "●", tam=22, color=VERDE)
            p = _centro(fila[4].paragraphs[0])
            if set(der.pareja) == {"●"}:
                _run(p, " ".join("⭐" * len(der.pareja)), tam=20, fuente=EMOJI_FUENTE)
            else:
                _run(p, der.pareja, tam=40, negrita=True)
            for c in (fila[1], fila[3], fila[0], fila[4]):
                c.vertical_alignment = 1
            fila[0].add_paragraph()
    elif a == "completar":
        for e in els:
            t = _tabla(doc, 1, 2)
            _sin_bordes(t)
            t.rows[0].cells[0].width, t.rows[0].cells[1].width = Cm(5), Cm(12)
            if e.pictograma:
                _poner_imagen(_centro(t.cell(0, 0).paragraphs[0]), rec, e.pictograma, 2.6)
            p = t.cell(0, 1).paragraphs[0]
            t.cell(0, 1).vertical_alignment = 1
            _run(p, e.texto.upper(), tam=44, negrita=True)
            doc.add_paragraph()
    elif a == "contar":
        maximo = max([e.cantidad for e in els] + [int(pg.destacado) if pg.destacado.isdigit() else 0, 3])
        for e in els:
            t = _tabla(doc, 1, 2)
            _sin_bordes(t)
            t.rows[0].cells[0].width, t.rows[0].cells[1].width = Cm(10), Cm(7)
            c0 = t.cell(0, 0)
            _bordes_celda(c0, color="C2D69B", grosor=10)
            p = c0.paragraphs[0]
            tipo, valor = rec.imagen(e.pictograma or e.texto)
            for _ in range(e.cantidad):
                if tipo == "img":
                    p.add_run().add_picture(str(valor), height=Cm(1.6))
                    p.add_run(" ")
                else:
                    _run(p, (valor if tipo == "emoji" else "●") + " ", tam=30, fuente=EMOJI_FUENTE)
            c1 = t.cell(0, 1)
            c1.vertical_alignment = 1
            _run(_centro(c1.paragraphs[0]), "   ".join(str(n) for n in range(1, maximo + 1)), tam=26, negrita=True)
            doc.add_paragraph()
    elif a == "clasificar":
        grupos = list(dict.fromkeys(e.grupo or "Otros" for e in els))
        t = _tabla(doc, 2, len(grupos) or 1)
        for j, g in enumerate(grupos):
            _bordes_celda(t.cell(0, j))
            _bordes_celda(t.cell(1, j))
            _run(_centro(t.cell(0, j).paragraphs[0]), g.upper(), tam=20, negrita=True, color=VERDE)
            for _ in range(6):
                t.cell(1, j).add_paragraph()
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        _run(p, "✂ Recorta y pega en su grupo:", tam=14, color=GRIS)
        _rejilla(doc, rec, _mezclar(els, indice), cols=4, alto=2.2, tam=14)
    elif a == "secuencia":
        orden = _mezclar(els, indice + 7)
        t = _tabla(doc, 1, len(orden) or 1)
        for j, e in enumerate(orden):
            c = t.cell(0, j)
            _bordes_celda(c)
            _celda_elemento(c, rec, e, 2.6, 14)
            _run(_centro(c.add_paragraph()), "☐", tam=30, color=GRIS)
        p = doc.add_paragraph()
        _run(p, "Escribe el número de cada paso en el cuadrado.", tam=12, color=GRIS)
    elif a == "tarjetas":
        _rejilla(doc, rec, els, cols=2, alto=5.0, tam=26)
    elif a == "cuento":
        for e in els:
            t = _tabla(doc, 1, 2)
            _sin_bordes(t)
            t.rows[0].cells[0].width, t.rows[0].cells[1].width = Cm(4), Cm(13)
            if e.pictograma:
                _poner_imagen(_centro(t.cell(0, 0).paragraphs[0]), rec, e.pictograma, 2.4)
            t.cell(0, 1).vertical_alignment = 1
            _run(t.cell(0, 1).paragraphs[0], e.texto, tam=22)
            doc.add_paragraph()


ESPACIALES = {"arriba", "abajo", "dentro", "fuera", "grande", "pequeño", "pequeno"}


def _frases(els):
    """Agrupa los elementos de una página «frase» por su número de frase (campo grupo)."""
    frases: dict[str, list] = {}
    for e in els:
        frases.setdefault(e.grupo or "0", []).append(e)
    return list(frases.values())


def _espaciales_docx(doc, rec, els):
    t = _tabla(doc, 1, len(els) or 1)
    for j, e in enumerate(els):
        c = t.cell(0, j)
        _bordes_celda(c, color="C2D69B", grosor=10)
        c.vertical_alignment = 1
        g = e.grupo
        caja = "🟫"
        if g == "arriba":
            _poner_imagen(_centro(c.paragraphs[0]), rec, e.pictograma, 2.4)
            _run(_centro(c.add_paragraph()), caja, tam=60, fuente=EMOJI_FUENTE)
        elif g == "abajo":
            _run(_centro(c.paragraphs[0]), caja, tam=60, fuente=EMOJI_FUENTE)
            _poner_imagen(_centro(c.add_paragraph()), rec, e.pictograma, 2.4)
        elif g == "dentro":
            interior = c.add_table(rows=1, cols=1)
            _bordes_celda(interior.cell(0, 0), grosor=24)
            _poner_imagen(_centro(interior.cell(0, 0).paragraphs[0]), rec, e.pictograma, 2.4)
        elif g == "fuera":
            _poner_imagen(_centro(c.paragraphs[0]), rec, e.pictograma, 2.4)
            interior = c.add_table(rows=1, cols=1)
            _bordes_celda(interior.cell(0, 0), grosor=24)
            for _ in range(3):
                interior.cell(0, 0).add_paragraph()
        else:  # grande / pequeño
            _poner_imagen(_centro(c.paragraphs[0]), rec, e.pictograma, 4.5 if g == "grande" else 1.6)
        c.add_paragraph()


def _cabecera_docx(doc, rec: Recursos):
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(1.6), Cm(1.6)
    sec.header_distance = sec.footer_distance = Cm(0.8)
    h = sec.header
    t = h.add_table(rows=1, cols=2, width=Cm(17))
    _sin_bordes(t)
    t.autofit = False
    t.cell(0, 0).width, t.cell(0, 1).width = Cm(4.5), Cm(12.5)
    logo = rec.ruta_logo()
    if logo:
        t.cell(0, 0).paragraphs[0].add_run().add_picture(str(logo), height=Cm(1.3))
    p = t.cell(0, 1).paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(p, " · ".join(x for x in (rec.cabecera, "PT/AL") if x), tam=10, negrita=True, color=VERDE)
    p = t.cell(0, 1).add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    nombre = rec.alumno or "____________________"
    _run(p, f"Nombre: {nombre}   Fecha: ________", tam=11, color=GRIS)
    if h.paragraphs and not h.paragraphs[0].text:
        h.paragraphs[0].paragraph_format.space_after = Pt(0)


def _pie_docx(doc, rec: Recursos):
    f = doc.sections[0].footer
    p = f.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, COLEGIO, tam=9, negrita=True, color=VERDE)
    if rec.usados_pictos:
        p = f.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, pictogramas.ATRIBUCION, tam=7, color=GRIS)


def a_word(spec: MaterialSpec, rec: Recursos) -> bytes:
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = LETRA
    estilo.font.size = Pt(12)
    _cabecera_docx(doc, rec)
    for i, pg in enumerate(spec.paginas):
        if i:
            doc.add_page_break()
        _pagina_docx(doc, rec, pg, i)
    _pie_docx(doc, rec)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ====================================================================== POWERPOINT
def a_powerpoint(spec: MaterialSpec, rec: Recursos) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor as PRGB
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn as pqn
    from pptx.util import Emu, Inches, Pt as PPt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    verde, gris, claro = PRGB(0x14, 0x68, 0x34), PRGB(0x6B, 0x75, 0x6E), PRGB(0xE2, 0xEF, 0xD9)
    blanco_vacio = prs.slide_layouts[6]
    margen = Inches(0.5)
    arriba = Inches(1.75)
    abajo = H - Inches(0.6)

    def texto(slide, x, y, w, h, contenido, tam=24, negrita=False, color=None, centro=True, fuente=LETRA, hueco=False):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER if centro else PP_ALIGN.LEFT
        r = p.add_run()
        r.text = contenido
        r.font.size = PPt(tam)
        r.font.bold = negrita
        r.font.name = fuente
        if hueco:  # letra hueca para repasar: sin relleno y con contorno
            rPr = r._r.get_or_add_rPr()
            ln = rPr.makeelement(pqn("a:ln"), {"w": "28575"})
            sf = ln.makeelement(pqn("a:solidFill"), {})
            sf.append(sf.makeelement(pqn("a:srgbClr"), {"val": "146834"}))
            ln.append(sf)
            prst = ln.makeelement(pqn("a:prstDash"), {"val": "dash"})
            ln.append(prst)
            rPr.insert(0, ln)
            rPr.insert(1, rPr.makeelement(pqn("a:noFill"), {}))
        elif color is not None:
            r.font.color.rgb = color
        return tb

    def imagen(slide, palabra, x, y, w, h, texto_alt=""):
        tipo, valor = rec.imagen(palabra)
        if tipo == "img":
            lado = min(w, h)
            slide.shapes.add_picture(str(valor), x + (w - lado) // 2, y + (h - lado) // 2, height=lado)
        elif tipo == "emoji":
            texto(slide, x, y, w, h, valor, tam=int(min(w, h) / 12700 * 0.62), fuente=EMOJI_FUENTE)
        elif tipo == "hueco":
            s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x + w // 6, y + h // 6, w * 2 // 3, h * 2 // 3)
            s.fill.background()
            s.line.color.rgb = gris
            s.line.dash_style = 4
        elif texto_alt:
            texto(slide, x, y, w, h, texto_alt, tam=int(min(w, h) / 12700 * 0.5), negrita=True)

    def caja(slide, x, y, w, h, color=None, grosor=1.5):
        s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        s.adjustments[0] = 0.08
        s.fill.solid()
        s.fill.fore_color.rgb = PRGB(0xFF, 0xFF, 0xFF)
        s.line.color.rgb = color or PRGB(0xC2, 0xD6, 0x9B)
        s.line.width = PPt(grosor)
        s.shadow.inherit = False
        return s

    def elemento(slide, e, x, y, w, h, con_caja=True):
        if con_caja:
            caja(slide, x, y, w, h)
        pad = Emu(int(min(w, h) * 0.08))
        if e.pictograma:
            alto_txt = int(h * 0.24) if e.texto else 0
            imagen(slide, e.pictograma, x + pad, y + pad, w - 2 * pad, h - 2 * pad - alto_txt)
            if e.texto:
                texto(slide, x, y + h - alto_txt - pad // 2, w, alto_txt, e.texto, tam=max(14, int(alto_txt / 12700 * 0.55)), negrita=True)
        else:
            texto(slide, x, y, w, h, e.texto, tam=max(18, int(min(w, h) / 12700 * 0.45)), negrita=True)

    def rejilla(slide, els, cols=None, x0=None, y0=None, ancho=None, alto=None):
        n = len(els)
        if not n:
            return
        cols = cols or (n if n <= 4 else 4 if n <= 8 else 5)
        filas = (n + cols - 1) // cols
        x0 = margen if x0 is None else x0
        y0 = arriba if y0 is None else y0
        ancho = (W - 2 * margen) if ancho is None else ancho
        alto = (abajo - y0 - Inches(0.1)) if alto is None else alto
        hueco = Inches(0.2)
        cw = (ancho - hueco * (cols - 1)) // cols
        ch = min((alto - hueco * (filas - 1)) // filas, int(cw * 1.1))
        y_ini = y0 + (alto - (ch * filas + hueco * (filas - 1))) // 2
        for i, e in enumerate(els):
            f, c = divmod(i, cols)
            elemento(slide, e, x0 + c * (cw + hueco), y_ini + f * (ch + hueco), cw, ch)

    def marco(slide, pg):
        banda = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.12))
        banda.fill.solid()
        banda.fill.fore_color.rgb = verde
        banda.line.fill.background()
        logo = rec.ruta_logo()
        if logo:
            slide.shapes.add_picture(str(logo), margen, Inches(0.25), height=Inches(0.65))
        texto(slide, W - margen - Inches(5), Inches(0.25), Inches(5), Inches(0.4),
              " · ".join(x for x in (rec.cabecera, "PT/AL") if x), tam=12, negrita=True, color=verde, centro=False)._element
        if rec.alumno:
            texto(slide, W - margen - Inches(5), Inches(0.6), Inches(5), Inches(0.35), rec.alumno, tam=12, color=gris, centro=False)
        texto(slide, margen, Inches(0.95), W - 2 * margen, Inches(0.75), pg.enunciado, tam=32, negrita=True, color=verde)

    for i, pg in enumerate(spec.paginas):
        s = prs.slides.add_slide(blanco_vacio)
        marco(s, pg)
        els = pg.elementos
        a = pg.actividad
        if a in ("letra", "repasar"):
            grande = len(pg.destacado) <= 4
            if a == "letra":
                alto_letra = abajo - arriba - (Inches(1.6) if els and any(e.pictograma for e in els) else 0)
                texto(s, margen, arriba, W - 2 * margen, alto_letra, pg.destacado, tam=220 if grande else 110,
                      negrita=True, color=verde)
                if els and any(e.pictograma for e in els):
                    rejilla(s, els[:4], cols=min(4, len(els)), y0=abajo - Inches(1.6), alto=Inches(1.5),
                            x0=Inches(3), ancho=W - Inches(6))
            else:
                texto(s, margen, arriba, W - 2 * margen, abajo - arriba, pg.destacado, tam=260 if grande else 120,
                      negrita=True, hueco=True)
        elif a == "unir":
            derecha = _mezclar(els, i)
            n = max(1, len(els))
            alto_f = (abajo - arriba) // n
            lado = min(alto_f - Inches(0.15), Inches(2.4))
            for k, (izq, der) in enumerate(zip(els, derecha)):
                y = arriba + k * alto_f + (alto_f - lado) // 2
                elemento(s, izq, Inches(1.5), y, Inches(3), lado)
                texto(s, Inches(4.6), y, Inches(0.6), lado, "●", tam=28, color=verde)
                texto(s, W - Inches(5.2), y, Inches(0.6), lado, "●", tam=28, color=verde)
                if set(der.pareja) == {"●"}:
                    caja(s, W - Inches(4.5), y, Inches(3), lado)
                    texto(s, W - Inches(4.5), y, Inches(3), lado, " ".join("⭐" * len(der.pareja)), tam=20, fuente=EMOJI_FUENTE)
                else:
                    elemento(s, type(der)(texto=der.pareja, pictograma="", pareja="", correcto=False, grupo="", cantidad=0),
                             W - Inches(4.5), y, Inches(3), lado)
        elif a == "contar":
            maximo = max([e.cantidad for e in els] + [int(pg.destacado) if pg.destacado.isdigit() else 0, 3])
            n = max(1, len(els))
            alto_f = (abajo - arriba) // n
            for k, e in enumerate(els):
                y = arriba + k * alto_f
                caja(s, margen, y + Inches(0.05), Inches(7.6), alto_f - Inches(0.1))
                lado = min(alto_f - Inches(0.3), Inches(7.2) // max(1, e.cantidad))
                for j in range(e.cantidad):
                    imagen(s, e.pictograma or e.texto, margen + Inches(0.2) + j * lado, y + (alto_f - lado) // 2, lado, lado, "●")
                texto(s, Inches(8.4), y, W - Inches(8.9), alto_f, "   ".join(str(x) for x in range(1, maximo + 1)),
                      tam=30, negrita=True)
        elif a == "pregunta" and any(e.grupo in ESPACIALES for e in els):
            n = max(1, len(els))
            ancho = (W - 2 * margen) // n
            for k, e in enumerate(els):
                x = margen + k * ancho + Inches(0.3)
                w = ancho - Inches(0.6)
                caja(s, x, arriba, w, abajo - arriba)
                g = e.grupo
                cx, alto_z = x + w // 2, abajo - arriba
                lado = Inches(1.6)
                if g in ("arriba", "abajo"):
                    yb = arriba + (alto_z * 2 // 5 if g == "arriba" else alto_z // 8)
                    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx - Inches(1.2), yb, Inches(2.4), Inches(1.6))
                    box.fill.solid()
                    box.fill.fore_color.rgb = PRGB(0xC8, 0x9B, 0x6A)
                    box.line.color.rgb = PRGB(0x8A, 0x5A, 0x2B)
                    yp = yb - lado - Inches(0.1) if g == "arriba" else yb + Inches(1.7)
                    imagen(s, e.pictograma, cx - lado // 2, yp, lado, lado)
                elif g in ("dentro", "fuera"):
                    bx = cx - Inches(1.5) if g == "dentro" else x + Inches(0.3)
                    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, bx, arriba + Inches(1.2), Inches(3), Inches(2.6))
                    box.fill.background()
                    box.line.color.rgb = verde
                    box.line.width = PPt(4)
                    px = cx - lado // 2 if g == "dentro" else x + w - lado - Inches(0.3)
                    imagen(s, e.pictograma, px, arriba + Inches(1.7), lado, lado)
                else:
                    lado = Inches(3.6) if g == "grande" else Inches(1.2)
                    imagen(s, e.pictograma, cx - lado // 2, arriba + (alto_z - lado) // 2, lado, lado)
        elif a == "clasificar":
            grupos = list(dict.fromkeys(e.grupo or "Otros" for e in els))
            ancho = (W - 2 * margen) // max(1, len(grupos))
            for k, g in enumerate(grupos):
                caja(s, margen + k * ancho + Inches(0.1), arriba, ancho - Inches(0.2), Inches(2.4), color=verde, grosor=2.5)
                texto(s, margen + k * ancho, arriba + Inches(0.05), ancho, Inches(0.5), g.upper(), tam=20, negrita=True, color=verde)
            rejilla(s, _mezclar(els, i), y0=arriba + Inches(2.6), alto=abajo - arriba - Inches(2.6))
        elif a == "tarjetas":
            rejilla(s, els, cols=min(4, max(1, len(els))))
        elif a == "frase":
            frases = _frases(els)
            alto_f = (abajo - arriba) // max(1, len(frases))
            for k, frase in enumerate(frases):
                y = arriba + k * alto_f
                cw = (W - 2 * margen) // max(6, len(frase))
                x0 = margen + ((W - 2 * margen) - cw * len(frase)) // 2
                lado = min(cw - Inches(0.1), alto_f - Inches(0.6))
                for j, e in enumerate(frase):
                    x = x0 + j * cw
                    if e.pictograma:
                        tipo, valor = rec.imagen(e.pictograma)
                        if tipo in ("img", "emoji"):
                            imagen(s, e.pictograma, x + (cw - lado) // 2, y, lado, lado)
                    texto(s, x, y + lado, cw, Inches(0.5), e.texto, tam=22, negrita=bool(e.pictograma))
        elif a == "pregunta" and pg.destacado:
            caja(s, margen, arriba, Inches(3.2), abajo - arriba, color=verde, grosor=2.5)
            imagen(s, pg.destacado, margen + Inches(0.3), arriba + Inches(0.4), Inches(2.6), Inches(2.6))
            texto(s, margen, arriba + Inches(3.1), Inches(3.2), Inches(0.8), pg.destacado.upper(), tam=28, negrita=True, color=verde)
            rejilla(s, els, x0=margen + Inches(3.5), ancho=W - 2 * margen - Inches(3.5))
        else:  # rodear, pregunta, completar, secuencia, cuento
            if a == "secuencia":
                els = _mezclar(els, i + 7)
            if a in ("cuento", "completar"):
                n = max(1, len(els))
                alto_f = (abajo - arriba) // n
                for k, e in enumerate(els):
                    y = arriba + k * alto_f
                    lado = min(alto_f - Inches(0.1), Inches(1.8))
                    if e.pictograma:
                        imagen(s, e.pictograma, margen + Inches(0.5), y + (alto_f - lado) // 2, lado, lado)
                    texto(s, margen + Inches(2.6), y, W - 2 * margen - Inches(2.6), alto_f,
                          e.texto.upper() if a == "completar" else e.texto, tam=40 if a == "completar" else 28,
                          negrita=a == "completar", centro=False)
            else:
                rejilla(s, els)
        pie = COLEGIO + ("   ·   " + pictogramas.ATRIBUCION if rec.usados_pictos else "")
        texto(s, margen, H - Inches(0.45), W - 2 * margen, Inches(0.35), pie, tam=9, color=gris)
        if spec.instrucciones_maestra and i == 0:
            s.notes_slide.notes_text_frame.text = f"{spec.objetivo}\n\n{spec.instrucciones_maestra}"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
