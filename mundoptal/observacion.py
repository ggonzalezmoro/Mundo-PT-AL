"""Informe de observación para alumnos sin ACI (en valoración).

Algunos alumnos acuden a las sesiones de PT/AL mientras Orientación los valora: no
son NEE ni tienen ACI, pero hay que dejar por escrito cómo se muestran en las
sesiones. El informe tiene apartados fijos (que se pueden renombrar, quitar o
añadir), frases de ayuda, las notas de la agenda del periodo y se exporta a Word
con el formato del colegio.
"""
from __future__ import annotations

import datetime as dt
import io
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from . import informes
from .config import DIAS, static_dir
from .store import Store, StoreError, normalizar

# (clave, título, ayuda)
APARTADOS = [
    ("motivo", "Motivo de la observación",
     "Quién lo propone (tutora, Orientación, familia) y qué se quiere observar."),
    ("contexto", "Organización de las sesiones",
     "Días, duración y agrupamiento. Se rellena solo con tu horario; cámbialo si hace falta."),
    ("conducta", "Comportamiento y actitud en las sesiones",
     "Cómo llega, cómo se separa del aula, motivación, respeto de normas, conducta ante las tareas."),
    ("atencion", "Atención, escucha y ritmo de trabajo",
     "Tiempo que mantiene la atención, si sigue la actividad, si termina las tareas, necesidad de apoyo."),
    ("comprension", "Comprensión del lenguaje",
     "Comprensión de órdenes, preguntas, vocabulario y cuentos."),
    ("expresion", "Expresión oral y habla",
     "Cómo se comunica (gestos, palabras, frases), vocabulario, estructura de las frases, pronunciación, fluidez."),
    ("relacion", "Relación con los adultos y con los compañeros",
     "Interacción, juego, respeto de turnos, si inicia o responde a la interacción."),
    ("emocional", "Regulación emocional y autonomía",
     "Reacción ante la frustración o los cambios, gestión de emociones, autonomía en la sesión."),
    ("estrategias", "Qué le ayuda",
     "Apoyos y estrategias que han funcionado en las sesiones."),
    ("conclusiones", "Valoración y propuestas",
     "Resumen de lo observado y propuestas (seguir observando, pautas para el aula y la familia…)."),
]
TITULOS = {k: t for k, t, _ in APARTADOS}
AYUDAS = {k: a for k, _, a in APARTADOS}

# Frases de ayuda: descriptivas y prudentes (es una observación, no un diagnóstico)
FRASES = {
    "motivo": [
        "{nombre} acude a las sesiones de apoyo mientras el Departamento de Orientación realiza su valoración.",
        "La tutora nos traslada su preocupación por el desarrollo del lenguaje en el aula.",
        "Se propone observar su comunicación, su atención y su conducta en un contexto de pequeño grupo.",
        "El objetivo de este informe es recoger cómo se muestra en las sesiones para completar la valoración.",
    ],
    "contexto": [
        "Las sesiones se realizan fuera del aula, en el aula de apoyo.",
        "Algunas sesiones se realizan dentro del aula ordinaria.",
        "Trabajamos con actividades de juego, cuentos, láminas y material manipulativo.",
    ],
    "conducta": [
        "Acude a las sesiones con agrado y se separa del aula sin dificultad.",
        "Al principio le costaba venir, pero poco a poco se ha ido adaptando a la rutina de las sesiones.",
        "Se muestra colaborador/a y participa en las actividades que se le proponen.",
        "Necesita que se le recuerden las normas de la sesión con frecuencia.",
        "Le cuesta aceptar el final de una actividad que le gusta.",
        "Se muestra tímido/a al principio, aunque va ganando confianza a lo largo de la sesión.",
        "Muestra conductas de oposición cuando la tarea le resulta difícil.",
    ],
    "atencion": [
        "Mantiene la atención en actividades cortas y muy motivadoras.",
        "Se distrae con facilidad con los estímulos del entorno.",
        "Necesita que el adulto le redirija para volver a la tarea.",
        "Termina las tareas con apoyo y refuerzo del adulto.",
        "Su ritmo de trabajo es lento y necesita más tiempo que sus compañeros.",
        "Mantiene la atención durante toda la sesión y termina las tareas de forma autónoma.",
    ],
    "comprension": [
        "Comprende órdenes sencillas relacionadas con el contexto inmediato.",
        "Le cuesta comprender órdenes de dos o más pasos.",
        "Necesita apoyo visual o gestual para comprender lo que se le pide.",
        "Responde adecuadamente a preguntas sencillas sobre un cuento o una lámina.",
        "Le resulta difícil responder a preguntas de tipo «¿por qué?» o «¿qué pasaría si…?».",
    ],
    "expresion": [
        "Se comunica principalmente mediante gestos y señalando.",
        "Utiliza palabras sueltas para pedir lo que quiere.",
        "Utiliza frases cortas de dos o tres palabras.",
        "Construye frases completas, aunque con algunos errores en la estructura.",
        "Su habla resulta poco inteligible para un adulto que no le conoce.",
        "Presenta dificultades en la pronunciación de algunos sonidos.",
        "Su vocabulario es reducido para su edad.",
        "Inicia conversaciones y cuenta cosas que le han pasado.",
    ],
    "relacion": [
        "Busca la interacción con el adulto y responde cuando se le habla.",
        "Se relaciona bien con sus compañeros del grupo.",
        "Prefiere jugar solo/a y le cuesta compartir el juego.",
        "Respeta los turnos con la ayuda del adulto.",
        "Le cuesta esperar su turno y participar en juegos compartidos.",
    ],
    "emocional": [
        "Se frustra con facilidad cuando algo no le sale.",
        "Acepta bien los cambios en la rutina de la sesión.",
        "Necesita anticipación para aceptar los cambios de actividad.",
        "Es capaz de calmarse con la ayuda del adulto.",
        "Muestra autonomía para recoger el material y moverse por el aula.",
    ],
    "estrategias": [
        "Le ayudan los apoyos visuales (pictogramas, imágenes, agenda de la sesión).",
        "Funciona bien el refuerzo positivo inmediato.",
        "Las actividades cortas y variadas le ayudan a mantener la atención.",
        "Anticiparle lo que vamos a hacer le da seguridad.",
        "El juego y los materiales manipulativos aumentan su motivación.",
    ],
    "conclusiones": [
        "Consideramos conveniente seguir observando su evolución en las sesiones.",
        "Proponemos continuar con el apoyo mientras se completa la valoración.",
        "Se recomienda compartir estas observaciones con la familia y la tutora.",
        "Sugerimos pautas sencillas para el aula: órdenes cortas, apoyo visual y refuerzo positivo.",
    ],
}

# Palabras que sugieren a qué apartado va una nota de la agenda
PISTAS = [
    ("atencion", ("atenc", "distra", "concentr", "despist", "termina", "ritmo", "escucha", "atento", "atenta")),
    ("expresion", ("habla", "pronunc", "frase", "palabra", "dice", "vocabul", "articul", "sonido", "cuenta", "tartam", "expres")),
    ("comprension", ("entiend", "comprend", "orden", "pregunta", "instruc")),
    ("relacion", ("compañer", "companer", "juega", "juego", "turno", "amig", "comparte", "interact")),
    ("emocional", ("llor", "rabiet", "frustr", "enfad", "calma", "autonom", "miedo", "nervios", "cambio")),
    ("estrategias", ("pictogram", "visual", "refuerz", "le ayuda", "funciona")),
]


def hoy() -> str:
    return dt.date.today().isoformat()


def _nombre_pila(nombre: str) -> str:
    return informes._nombre_pila(nombre)


def apartado_sugerido(texto: str) -> str:
    n = normalizar(texto)
    for clave, pistas in PISTAS:
        if any(normalizar(p) in n for p in pistas):
            return clave
    return "conducta"


def contexto_sesiones(store: Store, alumno_id: int) -> str:
    """Texto con los días y horas en que el alumno viene a las sesiones (según el horario)."""
    franjas = store.q(
        """SELECT f.id, f.dia, f.inicio, f.fin, f.especialidad,
                  (SELECT COUNT(*) FROM franja_alumnos x WHERE x.franja_id = f.id) AS tam
           FROM franjas f JOIN franja_alumnos fa ON fa.franja_id = f.id
           WHERE fa.alumno_id = ? AND f.archivada = 0 AND f.tipo = 'sesion' ORDER BY f.dia, f.inicio""",
        (alumno_id,))
    if not franjas:
        return ""
    partes = [f"los {DIAS[f['dia']].lower()} de {f['inicio']} a {f['fin']}" for f in franjas]
    lista = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
    n = len(franjas)
    texto = f"Acude a {n} {'sesión' if n == 1 else 'sesiones'} semanales de apoyo: {lista}."
    tamanos = {f["tam"] for f in franjas}
    if tamanos == {1}:
        texto += " Las sesiones son individuales."
    elif 1 not in tamanos:
        texto += " Las sesiones se realizan en pequeño grupo."
    else:
        texto += " Algunas sesiones son individuales y otras en pequeño grupo."
    return texto


def _primera_sesion(store: Store, alumno_id: int) -> str:
    r = store.q1("SELECT MIN(fecha) AS f FROM sesiones WHERE alumno_id = ? AND estado != 'cancelada'", (alumno_id,))
    return (r or {}).get("f") or ""


def listar(store: Store, alumno_id: int) -> list[dict]:
    return store.q("""SELECT id, titulo, fecha, desde, hasta, actualizado FROM informes_observacion
                      WHERE alumno_id = ? ORDER BY fecha DESC, id DESC""", (alumno_id,))


def crear(store: Store, alumno_id: int, maestra: str = "") -> int:
    al = store.q1("SELECT * FROM alumnos WHERE id = ?", (alumno_id,))
    if not al:
        raise StoreError("Alumno no encontrado")
    fecha = hoy()
    desde = _primera_sesion(store, alumno_id) or fecha
    nombre = _nombre_pila(al["nombre"])
    with store.tx() as c:
        informe_id = c.execute(
            """INSERT INTO informes_observacion(alumno_id, curso, curso_escolar, fecha, desde, hasta, maestra,
                                                destinatario) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (alumno_id, al.get("curso") or "", informes.curso_escolar_actual(), fecha, min(desde, fecha), "",
             maestra, "Departamento de Orientación")).lastrowid
        for i, (clave, titulo, _) in enumerate(APARTADOS):
            texto = ""
            if clave == "contexto":
                texto = contexto_sesiones(store, alumno_id)
            elif clave == "motivo":
                texto = FRASES["motivo"][0].format(nombre=nombre)
            c.execute("""INSERT INTO observacion_apartados(informe_id, clave, titulo, texto, orden)
                         VALUES (?, ?, ?, ?, ?)""", (informe_id, clave, titulo, texto, i))
    return informe_id


def obtener(store: Store, informe_id: int) -> dict | None:
    inf = store.q1("""SELECT o.*, al.nombre AS alumno_nombre, al.seguimiento FROM informes_observacion o
                      JOIN alumnos al ON al.id = o.alumno_id WHERE o.id = ?""", (informe_id,))
    if not inf:
        return None
    inf["apartados"] = store.q("SELECT * FROM observacion_apartados WHERE informe_id = ? ORDER BY orden, id",
                               (informe_id,))
    nombre = _nombre_pila(inf["alumno_nombre"])
    inf["frases"] = {k: [f.format(nombre=nombre) for f in v] for k, v in FRASES.items()}
    inf["ayudas"] = AYUDAS
    return inf


def anadir_apartado(store: Store, informe_id: int, titulo: str = "") -> int:
    if not store.q1("SELECT id FROM informes_observacion WHERE id = ?", (informe_id,)):
        raise StoreError("Informe no encontrado")
    with store.tx() as c:
        orden = c.execute("SELECT COALESCE(MAX(orden), -1) + 1 FROM observacion_apartados WHERE informe_id = ?",
                          (informe_id,)).fetchone()[0]
        return c.execute("INSERT INTO observacion_apartados(informe_id, clave, titulo, orden) VALUES (?, '', ?, ?)",
                         (informe_id, (titulo or "").strip() or "Otras observaciones", orden)).lastrowid


def asistencia(store: Store, alumno_id: int, desde: str, hasta: str) -> dict:
    filas = store.q("""SELECT fecha, estado, falta, motivo FROM sesiones
                       WHERE alumno_id = ? AND fecha BETWEEN ? AND ? ORDER BY fecha""", (alumno_id, desde, hasta))
    return {"realizadas": sum(1 for f in filas if f["estado"] == "realizada"),
            "faltas": [{"fecha": f["fecha"], "motivo": f["motivo"] or ""} for f in filas if f["falta"]]}


def notas(store: Store, informe_id: int) -> dict:
    """Notas de la agenda del periodo observado, pulidas y con el apartado sugerido."""
    inf = store.q1("SELECT * FROM informes_observacion WHERE id = ?", (informe_id,))
    if not inf:
        raise StoreError("Informe no encontrado")
    desde, hasta = inf["desde"] or "0000-01-01", inf["hasta"] or hoy()  # sin «hasta»: hasta hoy
    filas = store.q(
        """SELECT se.fecha, se.notas, f.inicio FROM sesiones se JOIN franjas f ON f.id = se.franja_id
           WHERE se.alumno_id = ? AND se.fecha BETWEEN ? AND ? AND se.estado != 'cancelada'
             AND TRIM(COALESCE(se.notas, '')) != '' ORDER BY se.fecha, f.inicio""",
        (inf["alumno_id"], desde, hasta))
    lista = []
    for f in filas:
        # Una nota puede mezclar cosas («Se distrae. Hace frases cortas»): cada frase va a su apartado
        for frase in re.split(r"(?<=[.!?])\s+|\n+", informes.pulir_nota(f["notas"])):
            frase = frase.strip()
            if frase:
                lista.append({"fecha": f["fecha"], "original": f["notas"], "texto": frase,
                              "apartado": apartado_sugerido(frase)})
    return {"desde": desde, "hasta": hasta, "notas": lista,
            "asistencia": asistencia(store, inf["alumno_id"], desde, hasta)}


# ======================================================================= Word
def _fecha_es(iso: str) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def exportar_word(store: Store, inf: dict) -> bytes:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
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
    r = p.add_run((inf.get("titulo") or "INFORME DE OBSERVACIÓN").upper())
    r.bold = True
    r.font.size = Pt(13)

    hasta = inf.get("hasta") or inf.get("fecha") or hoy()
    asis = asistencia(store, inf["alumno_id"], inf.get("desde") or "0000-01-01", hasta)
    datos = [("NOMBRE", inf.get("alumno_nombre", "")), ("CURSO", inf.get("curso", "")),
             ("CURSO ESCOLAR", inf.get("curso_escolar", "")), ("FECHA DEL INFORME", _fecha_es(inf.get("fecha", ""))),
             ("PERIODO OBSERVADO", f"del {_fecha_es(inf.get('desde', ''))} al {_fecha_es(hasta)}"),
             ("SESIONES REALIZADAS", f"{asis['realizadas']}" + (f" (faltas: {len(asis['faltas'])})" if asis["faltas"] else ""))]
    if (inf.get("destinatario") or "").strip():
        datos.append(("DIRIGIDO A", inf["destinatario"]))
    for etiqueta, valor in datos:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(f"{etiqueta}: ")
        r.bold = True
        r.font.size = Pt(10)
        p.add_run(str(valor or "")).font.size = Pt(10)

    for ap in inf.get("apartados", []):
        texto = (ap.get("texto") or "").strip()
        if not texto:
            continue
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(2)
        p.add_run((ap.get("titulo") or "").upper()).bold = True
        for parrafo in [x.strip() for x in texto.split("\n") if x.strip()]:
            q = doc.add_paragraph(parrafo)
            q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            q.paragraph_format.space_after = Pt(4)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("PROF. AUDICIÓN Y LENGUAJE/PEDAGOGÍA TERAPÉUTICA").bold = True
    doc.add_paragraph(inf.get("maestra") or "")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def nombre_archivo(inf: dict) -> str:
    return re.sub(r"[^\w\-]+", "_", f"Observacion_{inf['alumno_nombre']}_{inf.get('fecha', '')}").strip("_")
