"""Informe trimestral descriptivo para las familias.

La maestra redacta cómo ha ido el trimestre: aspecto social, actitud en las
sesiones de PT y de AL, evolución en cada área, valoración general y
orientaciones para casa. La evolución por áreas se puede rellenar con un
borrador a partir de las evaluaciones de la ACI, que después se retoca."""
from __future__ import annotations

import io
import re
from datetime import date

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from .config import static_dir
from .store import Store, StoreError, evaluacion_actual

# Frases de ayuda que la maestra puede insertar con un clic (después las adapta).
# {nombre} se sustituye por el nombre del alumno. Estilo de los informes del colegio.
FRASES = {
    "social": [
        "Durante este trimestre, {nombre} se ha mostrado con buena disposición y con muchas ganas de seguir aprendiendo día a día.",
        "Se relaciona con sus compañeros de forma positiva y disfruta compartiendo juegos.",
        "Busca al adulto como referencia y acepta su ayuda cuando la necesita.",
        "Conviene seguir reforzando la gestión de las esperas y el respeto por los turnos.",
        "Expresa cómo se siente con palabras, gestos o pictogramas.",
    ],
    "actitud": [
        "Destaca especialmente su actitud y predisposición a la hora de realizar las tareas que se le proponen.",
        "Acude a las sesiones con alegría y participa de forma activa.",
        "Mantiene la atención durante la actividad propuesta.",
        "Necesita apoyo para iniciar y terminar las tareas.",
        "Responde muy bien al refuerzo positivo.",
    ],
    "orientaciones": [
        "Es recomendable seguir trabajando en casa la flexibilidad ante los cambios, como aceptar terminar una actividad cuando se le pide.",
        "Os animamos a leer cuentos juntos y a nombrar lo que veis en las imágenes.",
        "Es importante darle tiempo para que se exprese, sin terminar sus frases.",
        "Los juegos de mesa sencillos le ayudarán a esperar su turno y a compartir.",
    ],
    "cierre": [
        "Ha sido un verdadero placer acompañar a {nombre} durante este trimestre y poder formar parte de su camino.",
        "Da alegría ver cómo se esfuerza y cómo celebra cada uno de sus pequeños avances.",
        "¡Muchas gracias por vuestra confianza, esfuerzo y por el gran trabajo que estáis realizando en casa!",
    ],
}

DESPEDIDAS = {
    1: "¡Os deseamos unas felices fiestas de Navidad!",
    2: "¡Os deseamos unas felices vacaciones de Semana Santa!",
    3: "¡Os deseamos unas felices vacaciones de verano!",
}

# Conectores para que cada área empiece de forma distinta, como en los informes del colegio
CONECTORES = ["En el área de {area}", "En cuanto a {area}", "Respecto a {area}", "En relación con {area}"]

MAX_POR_GRUPO = 6


def trimestre_actual(hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    if hoy.month >= 9:
        return 1
    return 2 if hoy.month <= 3 else 3


def curso_escolar_actual(hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    inicio = hoy.year if hoy.month >= 8 else hoy.year - 1
    return f"{inicio}/{str(inicio + 1)[-2:]}"


def _frase(texto: str) -> str:
    t = re.sub(r"^\[[^\]]*\]\s*", "", (texto or "").strip()).strip().rstrip(".")
    return t[:1].lower() + t[1:] if t else ""


def _lista(items: list[str]) -> str:
    textos = [_frase(t) for t in items if t.strip()]
    extra = len(textos) > MAX_POR_GRUPO
    textos = textos[:MAX_POR_GRUPO]
    if not textos:
        return ""
    txt = textos[0] if len(textos) == 1 else "; ".join(textos[:-1]) + " y " + textos[-1]
    return txt + (", entre otros aspectos" if extra else "")


def _nombre_area(area: str) -> str:
    n = re.sub(r"^\s*[áa]rea\s+(de\s+)?", "", (area or "").strip(), flags=re.I).strip()
    return n[:1].lower() + n[1:] if n and not n[:2].isupper() else n or "esta área"


def borrador_area(area: dict, trimestre: int, nombre: str, indice: int = 0) -> str:
    """Párrafo descriptivo de un área a partir de las evaluaciones de la ACI."""
    logrado, proceso, pendiente = [], [], []
    for s in area.get("subareas", []):
        for c in s.get("competencias", []):
            for it in c.get("items", []):
                v = evaluacion_actual(it, trimestre)
                if v in ("C", "ED+"):
                    logrado.append(it["texto"])
                elif v in ("ED", "I"):
                    proceso.append(it["texto"])
                elif v == "NI":
                    pendiente.append(it["texto"])
    inicio = CONECTORES[indice % len(CONECTORES)].format(area=_nombre_area(area.get("nombre", "")))
    partes = []
    if logrado:
        partes.append(f"{inicio}, {nombre} ha conseguido lo siguiente: {_lista(logrado)}.")
    if proceso:
        partes.append(("Actualmente" if logrado else f"{inicio}, actualmente")
                      + f" se encuentra avanzando en: {_lista(proceso)}.")
    if pendiente:
        partes.append(("Es recomendable" if partes else f"{inicio}, es recomendable")
                      + f" seguir trabajando: {_lista(pendiente)}.")
    if not partes:
        return f"{inicio}, (sin evaluaciones en la ACI para este trimestre: describe aquí su evolución)."
    return " ".join(partes)


def _aci_para(store: Store, alumno_id: int, trimestre: int, curso_escolar: str) -> dict | None:
    fila = store.q1(
        """SELECT id FROM acis WHERE alumno_id = ? AND trimestre = ? AND (curso_escolar = ? OR curso_escolar = '')
           ORDER BY id DESC LIMIT 1""", (alumno_id, trimestre, curso_escolar))
    aci_id = fila["id"] if fila else store.aci_vigente(alumno_id)
    return store.obtener_aci(aci_id) if aci_id else None


def _nombre_pila(nombre: str) -> str:
    return (nombre or "").split(" ")[0] or "el alumno"


def listar(store: Store, alumno_id: int) -> list[dict]:
    return store.q("""SELECT id, trimestre, curso_escolar, actualizado FROM informes
                      WHERE alumno_id = ? ORDER BY curso_escolar DESC, trimestre DESC""", (alumno_id,))


def resumen_usuario(store: Store, usuario_id: int | None) -> list[dict]:
    """Alumnos del perfil con sus informes, para la vista general."""
    alumnos = store.listar_alumnos(usuario_id)
    for a in alumnos:
        a["informes"] = listar(store, a["id"])
    return alumnos


def crear(store: Store, alumno_id: int, trimestre: int | None = None, curso_escolar: str | None = None,
          maestra: str = "") -> int:
    al = store.q1("SELECT * FROM alumnos WHERE id = ?", (alumno_id,))
    if not al:
        raise StoreError("Alumno no encontrado")
    trimestre = int(trimestre or trimestre_actual())
    if trimestre not in (1, 2, 3):
        raise StoreError("El trimestre debe ser 1, 2 o 3")
    curso_escolar = (curso_escolar or "").strip() or curso_escolar_actual()
    existe = store.q1("SELECT id FROM informes WHERE alumno_id = ? AND trimestre = ? AND curso_escolar = ?",
                      (alumno_id, trimestre, curso_escolar))
    if existe:
        return existe["id"]
    aci = _aci_para(store, alumno_id, trimestre, curso_escolar)
    with store.tx():
        cur = store.conn.execute(
            """INSERT INTO informes(alumno_id, aci_id, trimestre, curso_escolar, curso, maestra, prof_area, despedida)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (alumno_id, aci["id"] if aci else None, trimestre, curso_escolar,
             al.get("curso") or (aci or {}).get("curso", ""),
             maestra or (aci or {}).get("prof_ptal", ""), (aci or {}).get("prof_area", ""), DESPEDIDAS[trimestre]))
        informe_id = cur.lastrowid
        _insertar_areas(store, informe_id, aci, trimestre, al["nombre"])
    return informe_id


def _insertar_areas(store: Store, informe_id: int, aci: dict | None, trimestre: int, nombre: str):
    if not aci or not aci.get("areas"):
        return
    pila = _nombre_pila(nombre)
    for i, a in enumerate(aci["areas"]):
        store.conn.execute("INSERT INTO informe_areas(informe_id, area, texto, orden) VALUES (?, ?, ?, ?)",
                           (informe_id, a["nombre"] or "Área", borrador_area(a, trimestre, pila, i), i))


def rehacer_areas(store: Store, informe_id: int) -> None:
    """Vuelve a generar el borrador de las áreas con las evaluaciones actuales de la ACI."""
    inf = store.q1("SELECT informes.*, alumnos.nombre FROM informes JOIN alumnos ON alumnos.id = informes.alumno_id "
                   "WHERE informes.id = ?", (informe_id,))
    if not inf:
        raise StoreError("Informe no encontrado")
    aci = _aci_para(store, inf["alumno_id"], inf["trimestre"], inf["curso_escolar"])
    if not aci:
        raise StoreError("Este alumno no tiene ACI de la que sacar el borrador")
    with store.tx():
        store.conn.execute("DELETE FROM informe_areas WHERE informe_id = ?", (informe_id,))
        store.conn.execute("UPDATE informes SET aci_id = ?, actualizado = CURRENT_TIMESTAMP WHERE id = ?",
                           (aci["id"], informe_id))
        _insertar_areas(store, informe_id, aci, inf["trimestre"], inf["nombre"])


def anadir_area(store: Store, informe_id: int, area: str = "") -> int:
    if not store.q1("SELECT id FROM informes WHERE id = ?", (informe_id,)):
        raise StoreError("Informe no encontrado")
    with store.tx():
        orden = store.conn.execute("SELECT COALESCE(MAX(orden), -1) + 1 FROM informe_areas WHERE informe_id = ?",
                                   (informe_id,)).fetchone()[0]
        cur = store.conn.execute("INSERT INTO informe_areas(informe_id, area, orden) VALUES (?, ?, ?)",
                                 (informe_id, area.strip() or "Nueva área", orden))
        return cur.lastrowid


def obtener(store: Store, informe_id: int) -> dict | None:
    inf = store.q1("""SELECT informes.*, alumnos.nombre AS alumno_nombre FROM informes
                      JOIN alumnos ON alumnos.id = informes.alumno_id WHERE informes.id = ?""", (informe_id,))
    if not inf:
        return None
    inf["areas"] = store.q("SELECT * FROM informe_areas WHERE informe_id = ? ORDER BY orden, id", (informe_id,))
    pila = _nombre_pila(inf["alumno_nombre"])
    inf["frases"] = {k: [f.replace("{nombre}", pila) for f in v] for k, v in FRASES.items()}
    return inf


def parrafos(inf: dict) -> list[str]:
    """Texto del informe en el orden de los modelos del colegio (prosa continua)."""
    bloques = [inf.get("social"), inf.get("actitud_pt"), inf.get("actitud_al"),
               *[a.get("texto") for a in inf.get("areas", [])],
               inf.get("orientaciones"), inf.get("valoracion")]
    salida = []
    for b in bloques:
        salida += [x.strip() for x in re.split(r"\n+", b or "") if x.strip()]
    return salida


# ======================================================================= Word
def exportar_word(inf: dict) -> bytes:
    """Documento con el mismo formato que el apartado «Observaciones y comentarios» de las ACIs."""
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(1.5), Cm(1.5)
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)

    logo = static_dir() / "logo.png"
    if logo.exists():
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hp.add_run().add_picture(str(logo), height=Cm(1.6))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("INFORME DE EVALUACIÓN TRIMESTRAL")
    r.bold = True
    r.font.size = Pt(12)
    for etiqueta, valor in (("NOMBRE", inf.get("alumno_nombre", "")), ("CURSO", inf.get("curso", "")),
                            ("FECHA", f"{inf.get('trimestre', 1)}º Trimestre – Curso {inf.get('curso_escolar', '')}")):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(f"{etiqueta}: {valor}")
        r.bold = True
        r.font.size = Pt(10)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("OBSERVACIONES Y COMENTARIOS:").bold = True
    for texto in parrafos(inf):
        p = doc.add_paragraph(texto)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(8)
    if (inf.get("despedida") or "").strip():
        p = doc.add_paragraph()
        p.add_run(inf["despedida"].strip()).bold = True

    doc.add_paragraph()
    firmas(doc, inf.get("prof_area", ""), inf.get("maestra", ""))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def firmas(doc, prof_area: str, prof_ptal: str):
    """Pie de firmas a dos columnas, como en las ACIs."""
    t = doc.add_table(rows=2, cols=2)
    for i, (cargo, nombre) in enumerate((("PROF. RESPONSABLE DE ÁREA", prof_area),
                                         ("PROF. AUDICIÓN Y LENGUAJE/PEDAGOGÍA TERAPÉUTICA", prof_ptal))):
        c = t.rows[0].cells[i].paragraphs[0]
        c.add_run(cargo).bold = True
        t.rows[1].cells[i].paragraphs[0].add_run(nombre or "")


def nombre_archivo(inf: dict) -> str:
    return re.sub(r"[^\w\-]+", "_", f"Observaciones_{inf['alumno_nombre']}_{inf['trimestre']}T").strip("_")
