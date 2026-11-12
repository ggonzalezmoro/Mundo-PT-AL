"""Importación de ACIs en Word con las variantes reales de los documentos del colegio
(documentos sintéticos: nunca datos de alumnos reales)."""
import io
import sqlite3

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from mundoptal.store import Store
from mundoptal.word import exportar_aci, importar_aci


def _fila(tabla, textos, negrita=False):
    celdas = tabla.add_row().cells
    for c, t in zip(celdas, textos):
        c.text = ""
        r = c.paragraphs[0].add_run(t)
        r.bold = negrita
    return celdas


def _titulo(tabla, texto, negrita=True):
    fila = tabla.add_row()
    celda = fila.cells[0].merge(fila.cells[-1])
    celda.text = ""
    celda.paragraphs[0].add_run(texto).bold = negrita


def _en_control_de_contenido(doc, tabla):
    """Mete la tabla dentro de un <w:sdt> como hacen algunas plantillas."""
    sdt = OxmlElement("w:sdt")
    contenido = OxmlElement("w:sdtContent")
    sdt.append(contenido)
    tabla._tbl.addprevious(sdt)
    contenido.append(tabla._tbl)


def documento_variado() -> bytes:
    doc = Document()
    doc.add_paragraph("ADAPTACIÓN CURRICULAR INDIVIDUAL (ACI)")
    doc.add_paragraph("NOMBRE: Alumna Prueba")
    doc.add_paragraph("CURSO: 3º Curso del 2º Ciclo de Educación Infantil")
    doc.add_paragraph("FECHA:  Diciembre 2026")
    doc.add_paragraph("PROF. RESPONSABLE DE LAS ÁREAS :  Profe Área                       PT/AL:  Profe Apoyo")

    ad = doc.add_table(rows=1, cols=5)
    for c, t in zip(ad.rows[0].cells, ["ÁREA", "Adaptación Significativa", "Adaptación No Significativa",
                                       "No tiene adaptación", "Nivel curricular"]):
        c.text = t
    _fila(ad, ["COMUNICACIÓN Y REPRESENTACIÓN DE LA REALIDAD", "X", "", "", "2º ciclo"])
    _fila(ad, ["MÚSICA", "", "", "x", ""])
    _titulo(ad, "Propuesta curricular adaptada:")

    # Tabla de área con columna de observaciones y cabecera de trimestres
    t = doc.add_table(rows=0, cols=6)
    _titulo(t, "ÁREA DE COMUNICACIÓN Y REPRESENTACIÓN DE LA REALIDAD")
    _fila(t, ["TRIMESTRES", "", "", "1T", "2T", "3T"])
    _titulo(t, "Área léxico-semántica", negrita=False)
    _titulo(t, "Competencias y saberes: Desarrollar el léxico")
    _fila(t, ["", "Adquiere vocabulario de colores", "rojo, azul (confunde)", "ED", "", ""])
    _fila(t, ["", "Nombra prendas de ropa", "", "", "", ""])
    _titulo(t, "Objetivo general: Motricidad fina", negrita=False)
    _fila(t, ["", "Recorta líneas rectas", "", "I", "", ""])
    _en_control_de_contenido(doc, t)

    # Tabla con títulos en negrita sin combinar y sin cabecera de trimestres
    t2 = doc.add_table(rows=0, cols=3)
    _fila(t2, ["ÁREA DE CRECIMIENTO EN ARMONÍA", "", ""], negrita=True)
    _fila(t2, ["Autonomía", "", ""], negrita=True)
    _fila(t2, ["Se pone el abrigo solo", "", "ED+"])
    _fila(t2, ["Recoge sus cosas", "Se favorecerá con apoyo visual", ""])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_importa_variantes_reales():
    r = importar_aci(documento_variado())
    assert r["alumno_nombre"] == "Alumna Prueba"
    assert r["curso_escolar"] == "2026/27" and r["trimestre"] == 1
    assert (r["prof_area"], r["prof_ptal"]) == ("Profe Área", "Profe Apoyo")
    assert [a["area"] for a in r["adaptaciones"]] == ["COMUNICACIÓN Y REPRESENTACIÓN DE LA REALIDAD", "MÚSICA"]
    assert [a["tipo"] for a in r["adaptaciones"]] == ["significativa", "ninguna"]

    com, crec = r["areas"]
    assert com["nombre"] == "Comunicación y representación de la realidad" and com["especialidad"] == "AL"
    sub = com["subareas"][0]
    assert sub["nombre"] == "Área léxico-semántica"
    lexico, motricidad = sub["competencias"]
    assert lexico["nombre"] == "Desarrollar el léxico"
    colores, ropa = lexico["items"]
    assert colores["texto"] == "Adquiere vocabulario de colores"
    assert colores["nota"] == "rojo, azul (confunde)" and colores["eval_1t"] == "ED"
    assert ropa["nota"] == "" and ropa["eval_1t"] == ""
    assert motricidad["nombre"] == "Motricidad fina" and motricidad["items"][0]["eval_1t"] == "I"

    assert crec["nombre"] == "Crecimiento en armonía"
    autonomia = crec["subareas"][0]["competencias"][0]
    assert autonomia["nombre"] == "Autonomía"
    abrigo, cosas = autonomia["items"]
    # Sin cabecera de trimestres la evaluación es la del trimestre del documento
    assert abrigo["eval_1t"] == "ED+"
    assert cosas["nota"] == "Se favorecerá con apoyo visual"


def test_profesores_en_dos_lineas_con_huecos():
    doc = Document()
    doc.add_paragraph("NOMBRE: X")
    doc.add_paragraph("PROF. RESPONSABLE DE ÁREA                                      PROF. PEDAGOGÍA TERAPÉUTICA")
    doc.add_paragraph("_______________________________________                       Profe Apoyo")
    buf = io.BytesIO()
    doc.save(buf)
    r = importar_aci(buf.getvalue())
    assert (r["prof_area"], r["prof_ptal"]) == ("", "Profe Apoyo")


def test_observacion_de_item_ida_y_vuelta(tmp_path):
    s = Store(tmp_path / "a.db")
    alumno = s.crear_alumno("Ana")
    aci = s.crear_aci(alumno, {"trimestre": 1}, con_adaptaciones=False)
    s.importar_arbol(aci, importar_aci(documento_variado()))
    d = s.obtener_aci(aci)
    item = d["areas"][0]["subareas"][0]["competencias"][0]["items"][0]
    assert item["nota"] == "rojo, azul (confunde)"
    s.actualizar("items", item["id"], {"nota": "ya distingue el rojo"})
    d = s.obtener_aci(aci)
    d["alumno_nombre"] = "Ana"
    vuelta = importar_aci(exportar_aci(d))
    it = vuelta["areas"][0]["subareas"][0]["competencias"][0]["items"][0]
    assert it["texto"] == "Adquiere vocabulario de colores" and it["nota"] == "ya distingue el rojo"
    # Duplicar para el trimestre siguiente conserva la observación
    nueva = s.obtener_aci(s.duplicar_aci(aci))
    assert nueva["areas"][0]["subareas"][0]["competencias"][0]["items"][0]["nota"] == "ya distingue el rojo"


def test_migracion_anade_nota(tmp_path):
    ruta = tmp_path / "v3.db"
    Store(ruta).conn.close()
    con = sqlite3.connect(ruta)
    # Simula una base de datos de la versión anterior (sin la columna nota)
    con.executescript("""
        ALTER TABLE items RENAME TO items_viejo;
        CREATE TABLE items (id INTEGER PRIMARY KEY, competencia_id INTEGER NOT NULL, texto TEXT NOT NULL DEFAULT '',
            eval_1t TEXT NOT NULL DEFAULT '', eval_2t TEXT NOT NULL DEFAULT '', eval_3t TEXT NOT NULL DEFAULT '',
            destacado INTEGER NOT NULL DEFAULT 0, orden INTEGER NOT NULL DEFAULT 0);
        DROP TABLE items_viejo;
        UPDATE meta SET valor = '3' WHERE clave = 'schema_version';
    """)
    con.close()
    s = Store(ruta)
    cols = {r["name"] for r in s.conn.execute("PRAGMA table_info(items)")}
    assert "nota" in cols
