"""Informe trimestral descriptivo para las familias.

La maestra redacta cómo ha ido el trimestre: aspecto social y conducta,
actitud en las sesiones de PT y de AL, evolución en cada área, estrategias y
apoyos que han funcionado, orientaciones para casa y cierre. La evolución por áreas se puede rellenar con un
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
        "Se ha trabajado la relación con sus compañeros y el juego compartido.",
        "Busca al adulto como referencia y acepta su ayuda cuando la necesita.",
        "Conviene seguir reforzando la gestión de las esperas y el respeto por los turnos.",
        "Se ha trabajado la expresión de cómo se siente con palabras, gestos o pictogramas.",
        "{nombre} ha finalizado la etapa de Educación Infantil habiendo precisado adaptaciones metodológicas y apoyos a nivel curricular para favorecer su proceso de aprendizaje.",
        "{nombre} ha finalizado la etapa de Educación Infantil habiendo precisado adaptaciones metodológicas, así como apoyos tanto a nivel curricular como en el área del desarrollo atencional y funciones ejecutivas.",
        "Queremos destacar el gran cambio positivo de {nombre} en este trimestre: se muestra más motivado/a, cariñoso/a y con mucha más iniciativa.",
        "Las conductas disruptivas han disminuido de forma muy notable y cada vez acepta mejor las normas y los límites.",
        "Con el apoyo y la mediación del adulto, se incorpora cada vez más a las dinámicas grupales y al juego con sus compañeros.",
        "Todavía necesita la presencia y la guía cercana del adulto para regular su conducta en los momentos de más estimulación.",
    ],
    "actitud": [
        "Destaca especialmente su actitud y predisposición a la hora de realizar las tareas que se le proponen.",
        "Acude a las sesiones con alegría y participa de forma activa.",
        "Todavía necesita apoyo para mantener la atención durante la actividad propuesta.",
        "Necesita apoyo para iniciar y terminar las tareas.",
        "Responde muy bien al refuerzo positivo.",
    ],
    "estrategias": [
        "Para conseguir estos avances ha sido clave mantener una alta motivación y ofrecerle supervisión cercana.",
        "El uso de apoyos visuales y estructuradores del tiempo (como el reloj de arena y los temporizadores) le ha ayudado a anticipar y a mantenerse en la tarea.",
        "Combinar los apoyos visuales con sistemas de refuerzo externo ha favorecido que termine las actividades que se le proponen.",
        "Ha sido de gran ayuda el uso de materiales altamente motivadores relacionados con sus intereses.",
        "Responde mejor cuando cuenta con la presencia y la guía cercana del adulto.",
        "Dividir las tareas en pasos cortos y anticiparle lo que vamos a hacer le da seguridad.",
        "Las rutinas estables y la agenda visual le ayudan a afrontar los cambios con más tranquilidad.",
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
        "Por último, me gustaría daros las gracias y expresar lo orgullosa que estoy de {nombre}.",
        "Ha sido un verdadero placer acompañarle durante todo Infantil y poder formar parte de su camino y de sus avances.",
        "¡Muchas gracias por vuestra confianza, esfuerzo y por el gran trabajo que habéis realizado!",
    ],
    "despedida": [
        "¡Os deseamos unas felices fiestas de Navidad!",
        "¡Os deseamos unas felices vacaciones de Semana Santa!",
        "¡Os deseamos unas felices vacaciones de verano!",
        "¡Os deseamos un muy feliz verano y un merecido descanso!",
    ],
}

# Frases para describir lo que se ha trabajado en cada ámbito (se añaden al texto del área)
# Frases por ámbito: describen lo que se ha TRABAJADO o lo que aún NO ha conseguido.
# Nunca presuponen un logro: lo conseguido sale solo de los ítems evaluados con C.
FRASES_AMBITOS = {
    "Lenguaje oral": [
        "Se ha trabajado la descripción de imágenes, la narración de experiencias pasadas y la creación y narración de historias.",
        "Se ha trabajado la ampliación de vocabulario y la construcción de frases cada vez más completas.",
        "A nivel articulatorio, todavía no ha adquirido algunos fonemas, por lo que es necesario continuar reforzándolos.",
        "Se ha trabajado la comprensión de órdenes sencillas y las respuestas a preguntas sobre lo que ve o escucha.",
    ],
    "Lectoescritura": [
        "Se ha trabajado el reconocimiento de las vocales y la iniciación a la unión silábica.",
        "Se ha trabajado la asociación fonema-grafema con apoyo visual.",
        "Se ha trabajado la realización de trazos y la copia de palabras sencillas a partir de un modelo.",
    ],
    "Lógico-matemática": [
        "Se han trabajado los números del 1 al 3 y su asociación con la cantidad, por ejemplo colocando gomets.",
        "Se ha trabajado la clasificación de objetos por color, forma y tamaño.",
        "Se han trabajado series sencillas de dos elementos.",
    ],
    "Atención y funciones ejecutivas": [
        "Se han realizado actividades como búsqueda de diferencias, seguimiento de series y copia de modelos.",
        "Todavía necesita recordatorios y apoyo del adulto para mantener la atención y terminar la tarea.",
        "Aún no es capaz de inhibir las respuestas impulsivas, por lo que seguiremos trabajando la espera.",
    ],
    "Psicomotricidad fina": [
        "Se ha trabajado la psicomotricidad fina con pinchitos, materiales de enroscar, plastilina, punzones y pinturas.",
        "Se ha trabajado la pinza y el control del trazo al colorear.",
    ],
    "Autonomía": [
        "Se han trabajado las rutinas del aula, como colgar el abrigo o recoger el material.",
        "Todavía necesita apoyo verbal para seguir los pasos de las rutinas de aseo y vestido.",
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


def _lista(items: list[str], comillas: bool = False) -> str:
    textos = [_frase(t) for t in items if t.strip()]
    extra = len(textos) > MAX_POR_GRUPO
    textos = textos[:MAX_POR_GRUPO]
    if not textos:
        return ""
    if comillas:  # «…»: se lee como objetivo de la ACI, no como algo que el alumno ya hace
        textos = [f"«{t}»" for t in textos]
    txt = textos[0] if len(textos) == 1 else ", ".join(textos[:-1]) + " y " + textos[-1]
    if not comillas:
        txt = textos[0] if len(textos) == 1 else "; ".join(textos[:-1]) + " y " + textos[-1]
    return txt + (", entre otros aspectos" if extra else "")


def _nombre_area(area: str) -> str:
    n = re.sub(r"^\s*[áa]rea\s+(de\s+)?", "", (area or "").strip(), flags=re.I).strip()
    return n[:1].lower() + n[1:] if n and not n[:2].isupper() else n or "esta área"


# Cómo se redacta cada nivel de la escala. Hay que ser estrictos: la familia no debe
# entender que el alumno hace algo que no hace. Solo C se redacta como conseguido.
#   C   = conseguido y dominado
#   ED+ = casi conseguido, falta generalizarlo a todos los contextos (todavía NO conseguido)
#   ED  = en proceso, le falta mucho por trabajar (NO conseguido)
#   I   = lo ha hecho en alguna ocasión aislada; no se puede decir que lo haga (NO conseguido)
#   NI  = no lo ha iniciado (NO conseguido)
NIVELES_INFORME = [
    ("C", "ha conseguido lo siguiente", False),
    ("ED+", "todavía no ha conseguido del todo los siguientes objetivos, porque aunque está cerca, aún no "
            "los realiza en todos los contextos", True),
    ("ED", "todavía no ha conseguido los siguientes objetivos, en los que está en proceso y aún le queda "
           "mucho por trabajar", True),
    ("I", "todavía no ha conseguido los siguientes objetivos (solo los hemos observado en alguna ocasión aislada, "
          "por lo que no podemos decir que los realice)", True),
    ("NI", "todavía no ha iniciado los siguientes objetivos, que seguiremos trabajando", True),
]


def borrador_area(area: dict, trimestre: int, nombre: str, indice: int = 0) -> str:
    """Párrafo descriptivo de un área a partir de las evaluaciones de la ACI.

    Solo los ítems en C se redactan como conseguidos; el resto se describe según su nivel."""
    grupos: dict[str, list[str]] = {k: [] for k, _, _ in NIVELES_INFORME}
    for s in area.get("subareas", []):
        for c in s.get("competencias", []):
            for it in c.get("items", []):
                v = evaluacion_actual(it, trimestre)
                if v in grupos:
                    grupos[v].append(it["texto"])
    inicio = CONECTORES[indice % len(CONECTORES)].format(area=_nombre_area(area.get("nombre", "")))
    partes = []
    for clave, frase, comillas in NIVELES_INFORME:
        if not grupos[clave]:
            continue
        lista = _lista(grupos[clave], comillas)
        if not partes:
            partes.append(f"{inicio}, {nombre} {frase}: {lista}.")
        else:
            partes.append(f"{frase[0].upper()}{frase[1:]}: {lista}.")
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
    inf["frases_ambitos"] = FRASES_AMBITOS
    return inf


def parrafos(inf: dict) -> list[str]:
    """Texto del informe en el orden de los modelos del colegio (prosa continua)."""
    bloques = [inf.get("social"), inf.get("actitud_pt"), inf.get("actitud_al"),
               *[a.get("texto") for a in inf.get("areas", [])],
               inf.get("estrategias"), inf.get("orientaciones"), inf.get("valoracion")]
    salida = []
    for b in bloques:
        salida += [x.strip() for x in re.split(r"\n+", b or "") if x.strip()]
    return salida


# ============================================================ notas de la agenda
# Abreviaturas habituales al escribir deprisa
ABREVIATURAS = {
    "q": "que", "xq": "porque", "pq": "porque", "porq": "porque", "x": "por", "tb": "también", "tmb": "también",
    "tbn": "también", "mñn": "mañana", "d": "de", "k": "que", "cn": "con", "sn": "sin", "dl": "del",
    "msj": "mensaje", "mto": "mucho", "mta": "mucha", "bn": "bien", "mjr": "mejor", "aten": "atención",
    "dif": "dificultad", "difs": "dificultades", "act": "actividad", "acts": "actividades",
}
# Primera persona del singular -> plural del equipo, como en los informes del colegio
PERSONA = {
    "he trabajado": "hemos trabajado", "he visto": "hemos observado",
    "he observado": "hemos observado", "noto": "notamos", "veo": "vemos", "he notado": "hemos notado",
}
MOMENTOS = ["Al comienzo del trimestre", "A lo largo del trimestre", "En las últimas sesiones"]


def rango_trimestre(trimestre: int, curso_escolar: str) -> tuple[str, str]:
    """Fechas aproximadas de cada trimestre del curso «2026/27»."""
    try:
        inicio = int((curso_escolar or "").split("/")[0])
    except ValueError:
        inicio = date.today().year if date.today().month >= 8 else date.today().year - 1
    return {1: (f"{inicio}-09-01", f"{inicio}-12-31"),
            2: (f"{inicio + 1}-01-01", f"{inicio + 1}-03-31"),
            3: (f"{inicio + 1}-04-01", f"{inicio + 1}-07-31")}[int(trimestre)]


def asistencia(store: Store, alumno_id: int, trimestre: int, curso_escolar: str) -> dict:
    """Registro de asistencia del alumno en un trimestre a partir de las sesiones de la agenda."""
    desde, hasta = rango_trimestre(trimestre, curso_escolar)
    filas = store.q("""SELECT fecha, estado, falta, motivo FROM sesiones
                       WHERE alumno_id = ? AND fecha BETWEEN ? AND ? ORDER BY fecha""", (alumno_id, desde, hasta))
    return {"trimestre": int(trimestre), "curso_escolar": curso_escolar, "desde": desde, "hasta": hasta,
            "realizadas": sum(1 for f in filas if f["estado"] == "realizada"),
            "faltas": [{"fecha": f["fecha"], "motivo": f["motivo"] or ""} for f in filas if f["falta"]],
            "canceladas": sum(1 for f in filas if f["estado"] == "cancelada" and not f["falta"])}


def notas_trimestre(store: Store, informe_id: int) -> dict:
    """Notas de la agenda e ítems trabajados del alumno en el trimestre del informe."""
    inf = store.q1("SELECT * FROM informes WHERE id = ?", (informe_id,))
    if not inf:
        raise StoreError("Informe no encontrado")
    desde, hasta = rango_trimestre(inf["trimestre"], inf["curso_escolar"])
    sesiones = store.q(
        """SELECT se.id, se.fecha, se.notas, se.estado, f.especialidad FROM sesiones se
           JOIN franjas f ON f.id = se.franja_id
           WHERE se.alumno_id = ? AND se.fecha BETWEEN ? AND ? AND se.estado != 'cancelada'
           ORDER BY se.fecha, f.inicio""", (inf["alumno_id"], desde, hasta))
    items = store.q(
        """SELECT DISTINCT i.texto FROM sesion_items si JOIN sesiones se ON se.id = si.sesion_id
           JOIN items i ON i.id = si.item_id
           WHERE se.alumno_id = ? AND se.fecha BETWEEN ? AND ? AND si.trabajado = 1
           ORDER BY se.fecha""", (inf["alumno_id"], desde, hasta))
    return {"desde": desde, "hasta": hasta,
            "asistencia": asistencia(store, inf["alumno_id"], inf["trimestre"], inf["curso_escolar"]),
            "notas": [s for s in sesiones if (s["notas"] or "").strip()],
            "sesiones": len(sesiones), "items": [i["texto"] for i in items]}


def pulir_nota(texto: str) -> str:
    """Convierte una nota rápida en una frase limpia: abreviaturas, persona, mayúscula y punto."""
    t = re.sub(r"\s+", " ", (texto or "").strip())
    t = re.sub(r"\s*[-–•]+\s*", ", ", t).strip(" ,")
    t = re.sub(r"\b(\w+)\b", lambda m: ABREVIATURAS.get(m.group(1).lower(), m.group(1)), t)
    for yo, nosotros in PERSONA.items():
        t = re.sub(rf"\b{yo}\b", nosotros, t, flags=re.I)
    # En un informe trimestral sobra el «hoy» de la nota del día
    t = re.sub(r"\b(hoy|esta mañana|esta tarde|este día)\b,?\s*", "", t, flags=re.I).strip(" ,")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,;:])(?=\S)", r"\1 ", t)
    t = re.sub(r"\bmuy muy\b", "muy", t, flags=re.I)
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    # mayúscula tras cada punto
    t = re.sub(r"([.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), t)
    return t if t[-1] in ".!?" else t + "."


def redactar_notas(datos: dict, nombre: str) -> str:
    """Borrador en prosa para la familia a partir de las notas rápidas de la agenda."""
    notas = [pulir_nota(n["notas"]) for n in datos.get("notas", [])]
    notas = [n for i, n in enumerate(notas) if n and n not in notas[:i]]
    partes = []
    if notas:
        tercio = max(1, round(len(notas) / 3))
        grupos = [notas[:tercio], notas[tercio:2 * tercio], notas[2 * tercio:]] if len(notas) >= 3 else [notas]
        for i, grupo in enumerate(g for g in grupos if g):
            if len(grupos) == 1:
                partes.append(f"Durante las sesiones de este trimestre, {grupo[0][0].lower() + grupo[0][1:]}")
                partes += grupo[1:]
            else:
                momento = MOMENTOS[min(i, 2)]
                partes.append(f"{momento}, {grupo[0][0].lower() + grupo[0][1:]}")
                partes += grupo[1:]
    if datos.get("items"):
        partes.append(f"En las sesiones hemos trabajado especialmente estos objetivos: {_lista(datos['items'], True)}.")
    return " ".join(partes)


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
