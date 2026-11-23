"""Juntas de evaluación.

Durante la junta de cada trimestre la maestra apunta (o dicta) lo que se dice de cada
alumno. Después, con un botón, esas notas rápidas se redactan en un borrador más
profesional, repartido por los apartados del informe del trimestre, que se revisa y se
pasa al informe a familias (alumnos con ACI) o al informe de observación (alumnos en
valoración).

Todo se hace con reglas locales (sin internet ni IA). Las notas de la junta no van
unidas a ningún ítem de la ACI, así que nunca se redactan como algo conseguido: lo
conseguido solo sale de los ítems evaluados con C."""
from __future__ import annotations

import re
from . import informes, observacion, redaccion
from .store import Store, StoreError, normalizar

TITULOS_INFORME = {
    "social": "Cómo se ha mostrado este trimestre",
    "actitud_pt": "Actitud en las sesiones de PT",
    "actitud_al": "Actitud en las sesiones de AL",
    "estrategias": "Estrategias y apoyos que han funcionado",
    "orientaciones": "Orientaciones para casa",
    "valoracion": "Cierre",
}
ORDEN_INFORME = ["social", "actitud_pt", "actitud_al", "area", "estrategias", "orientaciones", "valoracion"]

# Quién lo dice en la junta: se quita «La tutora dice que…» y se redacta según el contexto
_QUIEN = (r"(?:la |el |su |sus )?(tutor[ao]s?|profes?(?:or(?:a|es)?)?|maestr[ao]s?|equipo(?: docente)?|"
          r"orientador[ao]?|orientaci[oó]n|familia|padres|madre|padre|mam[aá]|pap[aá])\b(?: de (?:aula|clase|"
          r"ingl[eé]s|m[uú]sica|psico|infantil|apoyo))?")
_VERBO_QUIEN = (r"(?:dice|dicen|comenta|comentan|cuenta|cuentan|indica|indican|señala|señalan|observa|observan|"
                r"nota|notan|ve|ven|ha visto|han visto|ha observado|han observado|ha notado|han notado|traslada|"
                r"trasladan|refiere|refieren|explica|explican|comunica|comunican|informa|informan|destaca|destacan)")
FUENTE = re.compile(rf"^{_QUIEN}\s*(?:[:\-–,]\s*|\s+{_VERBO_QUIEN}(?:\s+(?:que|q|k))?\s*[:,]?\s*)", re.I)
PREFIJO_FUENTE = {"aula": "En el aula, ", "orientacion": "Desde el Departamento de Orientación nos indican que ",
                  "familia": "En casa, "}

# Lo que suena a «conseguido» se rebaja (no hay evaluación C que lo respalde)
LOGROS_JUNTA = [
    (r"\b(?:ya )?(?:ha conseguido|consigue|ha logrado|logra|es capaz de)\s+(?=[a-záéíóúñ]+(?:ar|er|ir)(?:se|lo|la|los|las|le)?\b)",
     "está empezando a "),
    (r"\b(?:ya )?(?:lo )?(?:ha conseguido|consigue|ha logrado|lo logra|lo domina)\b", "está empezando a hacerlo"),
    (r"\b(?:ya )?domina\b", "está afianzando"),
    (r"\b(?:ya )?lo hace (?:sol[oa]|sin ayuda|perfecto|perfectamente|genial|muy bien)\b",
     "lo ha hecho bien en algunos momentos"),
    (r"\bperfect(?:o|amente)\b|\bgenial\b", "bien"),
]
# Palabras con las que suele empezar una nota que describe cómo está («muy contento»)
ESTADOS = set("""muy bastante más mas menos algo super súper contento contenta feliz alegre tranquilo tranquila
nervioso nerviosa motivado motivada desmotivado desmotivada cansado cansada tímido tímida timido timida
participativo participativa colaborador colaboradora cariñoso cariñosa inquieto inquieta risueño risueña
callado callada integrado integrada adaptado adaptada""".split())
ADJETIVOS = ESTADOS - {"muy", "bastante", "más", "mas", "menos", "algo", "super", "súper"}
# Primeras palabras tras las que no se pone el nombre del alumno
SIN_NOMBRE = set("""el la los las un una en con sin a al de del por para cuando todavía aún aun ya también
tambien muy hay es son durante desde este esta estos estas su sus mi nos os y o pero""".split())
CONECTORES = ["Además, ", "", "Asimismo, ", "", "Por otro lado, ", ""]
EMPIEZA_CONECTOR = re.compile(r"^(además|asimismo|por otro lado|también|en el aula|en casa|desde orientación|"
                              r"durante|en las sesiones|en el área|en cuanto|respecto|en relación|sin embargo|"
                              r"aun así|aunque|por último)\b", re.I)

# Pistas para repartir cada frase. El orden importa (lo más concreto primero).
PISTAS_ORIENTACION = ("recomend", "aconsej", "en casa conviene", "trabajar en casa", "reforzar en casa",
                      "seguir en casa", "pautas", "sugerir a la familia", "pedir a la familia", "decir a la familia")
PISTAS_ESTRATEGIA = ("le ayuda", "le ayudan", "le funciona", "funciona", "pictogram", "apoyo visual", "apoyos visuales",
                     "refuerz", "temporizador", "reloj de arena", "agenda visual", "anticip", "economia de fichas",
                     "le viene bien", "le va bien", "le sirve")
# (clave, título si la ACI no tiene un área parecida, pistas, palabras del nombre del área)
AMBITOS = [
    ("motricidad", "Psicomotricidad y autonomía",
     ("pinza", "recort", "tijera", "colore", "motricidad", "psicomotri", "punzon", "plastilina", "autonom", "aseo",
      "baño", "vestir", "abrigo", "comedor", "esfinter", "pañal", "cordones"),
     ("crecimiento", "armonia", "autonomia", "motricidad", "psicomotricidad")),
    ("lectoescritura", "Lectoescritura",
     ("letra", " lee ", "lectura", "leer", "escrib", "escritura", "silaba", "vocal", "grafomotri", "trazo",
      "su nombre", "copia"),
     ("lectoescritura", "lectura", "escritura", "comunicacion", "lenguaje")),
    ("matematicas", "Lógico-matemática",
     ("numero", "cuenta hasta", "contar", "cantidad", "suma", "resta", "serie", "clasific", "formas geometricas",
      "tamaño", "colores", "logic", "matemat"),
     ("logico", "matemat", "descubrimiento", "entorno")),
    ("lenguaje", "Comunicación y lenguaje",
     ("habla", "lenguaje", "vocabul", "frase", "palabra", "pronunci", "fonema", "articul", "sonido", "expres",
      "comprend", "entiende", "ordenes", "cuento", "narra", "conversa", "comunica", "inteligib", "tartam"),
     ("comunicacion", "lenguaje", "oral", "representacion")),
]
PISTAS_ACTITUD = ("sesion", "actitud", "motiva", "atenc", "atento", "atenta", "concentr", "trabaj", "tarea", "esfuerz",
                  "participa", "ritmo", "termina", "distra", "despist")


# ======================================================================= datos
def obtener(store: Store, usuario_id: int | None, trimestre: int | None = None,
            curso_escolar: str | None = None) -> dict:
    """Junta del perfil para ese trimestre y curso (se crea si no existe), con sus alumnos."""
    trimestre = int(trimestre or informes.trimestre_actual())
    if trimestre not in (1, 2, 3):
        raise StoreError("El trimestre debe ser 1, 2 o 3")
    curso_escolar = (curso_escolar or "").strip() or informes.curso_escolar_actual()
    junta = store.q1("SELECT * FROM juntas WHERE usuario_id IS ? AND curso_escolar = ? AND trimestre = ?",
                     (usuario_id, curso_escolar, trimestre))
    if not junta:
        with store.tx() as c:
            c.execute("INSERT INTO juntas(usuario_id, curso_escolar, trimestre) VALUES (?, ?, ?)",
                      (usuario_id, curso_escolar, trimestre))
        junta = store.q1("SELECT * FROM juntas WHERE usuario_id IS ? AND curso_escolar = ? AND trimestre = ?",
                         (usuario_id, curso_escolar, trimestre))
    notas = {r["alumno_id"]: r for r in store.q("SELECT * FROM junta_alumnos WHERE junta_id = ?", (junta["id"],))}
    alumnos = []
    for a in store.listar_alumnos(usuario_id):
        n = notas.get(a["id"], {})
        destino = _informe_existente(store, a, trimestre, curso_escolar)
        alumnos.append({"alumno_id": a["id"], "nombre": a["nombre"], "curso": a.get("curso") or "",
                        "seguimiento": a.get("seguimiento") or "aci", "notas": n.get("notas", ""),
                        "pasado": n.get("pasado"), "informe": destino})
    junta["alumnos"] = alumnos
    return junta


def _informe_existente(store: Store, alumno: dict, trimestre: int, curso_escolar: str) -> dict | None:
    if alumno.get("seguimiento") == "observacion":
        f = store.q1("SELECT id FROM informes_observacion WHERE alumno_id = ? ORDER BY fecha DESC, id DESC LIMIT 1",
                     (alumno["id"],))
        return {"tipo": "observacion", "id": f["id"]} if f else None
    f = store.q1("SELECT id FROM informes WHERE alumno_id = ? AND trimestre = ? AND curso_escolar = ?",
                 (alumno["id"], trimestre, curso_escolar))
    return {"tipo": "informe", "id": f["id"]} if f else None


def _junta(store: Store, junta_id: int) -> dict:
    j = store.q1("SELECT * FROM juntas WHERE id = ?", (junta_id,))
    if not j:
        raise StoreError("Junta no encontrada")
    return j


def guardar_notas(store: Store, junta_id: int, alumno_id: int, notas: str) -> None:
    _junta(store, junta_id)
    if not store.q1("SELECT id FROM alumnos WHERE id = ?", (alumno_id,)):
        raise StoreError("Alumno no encontrado")
    with store.tx() as c:
        c.execute("""INSERT INTO junta_alumnos(junta_id, alumno_id, notas) VALUES (?, ?, ?)
                     ON CONFLICT(junta_id, alumno_id) DO UPDATE SET notas = excluded.notas,
                     actualizado = CURRENT_TIMESTAMP""", (junta_id, alumno_id, notas or ""))
        c.execute("UPDATE juntas SET actualizado = CURRENT_TIMESTAMP WHERE id = ?", (junta_id,))


# ======================================================================= redacción
def _minuscula(t: str, nombre: str = "") -> str:
    if not t:
        return t
    primera = t.split(" ")[0].strip(",.")
    if (nombre and primera.lower() == nombre.lower()) or t[1:2].isupper():
        return t
    return t[0].lower() + t[1:]


def _mayuscula(t: str) -> str:
    return t[:1].upper() + t[1:] if t else t


def _punto(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip(" ,;")
    t = re.sub(r"\s+([,.;:])", r"\1", t).replace("..", ".")
    return t if not t or t[-1] in ".!?" else t + "."


def frases(notas: str) -> list[dict]:
    """Notas de la junta → frases pulidas, cada una con su fuente (aula, orientación, casa)."""
    salida = []
    for linea in (notas or "").split("\n"):
        linea = re.sub(r"^\s*(?:[-*•·▪◦→>]+|\d{1,2}[.)]|\[\s?[xX]?\s?\]|☐|☑)\s*", "", linea).strip()
        if not linea:
            continue
        for trozo in re.split(r"(?<=[.?;])\s+", linea):
            trozo = trozo.strip(" ;")
            if not trozo:
                continue
            fuente = ""
            m = FUENTE.match(trozo)
            if m and len(trozo) > m.end() + 3:
                quien = normalizar(m.group(1))
                fuente = ("familia" if quien.startswith(("famil", "padre", "madre", "mama", "papa"))
                          else "orientacion" if quien.startswith("orienta") else "aula")
                trozo = trozo[m.end():]
            trozo = re.sub(r"[!¡]+", "", trozo)
            trozo = re.sub(r"(^|,\s*)(rabietas|pataletas)\b", r"\1tiene \2", trozo, flags=re.I)
            t = informes.pulir_nota(trozo).rstrip(".")
            # «mto contento» → «muy contento» (la abreviatura «mto» es «mucho»)
            t = re.sub(r"\bmuch[oa] (?=(?:" + "|".join(sorted(ADJETIVOS)) + r")\b)", "muy ", t, flags=re.I)
            for patron, cambio in LOGROS_JUNTA:
                t = re.sub(patron, cambio, t, flags=re.I)
            t = redaccion.suavizar(t, conseguido=True)  # los logros ya se han rebajado arriba
            if not t:
                continue
            if t.split(" ")[0].lower() in ESTADOS:
                t = "se muestra " + _minuscula(t)
            salida.append({"texto": _mayuscula(t), "fuente": fuente, "original": linea})
    return salida


def _con_nombre(t: str, nombre: str) -> str:
    """Primera frase del informe: «Durante este trimestre, Ana participa…»."""
    primera = t.split(" ")[0].lower()
    if not nombre or primera == nombre.lower() or primera in SIN_NOMBRE or t[:1].isupper():
        return t
    if primera in ("le", "les"):
        return f"a {nombre} {t}"
    return f"{nombre} {t}"


def componer(lista: list[dict], inicio: str = "", nombre: str = "", indice: int = 0) -> str:
    """Une las frases en un párrafo con conectores. «inicio» se pone delante de la primera."""
    partes = []
    for i, f in enumerate(lista):
        t = f["texto"].rstrip(".")
        pref = PREFIJO_FUENTE.get(f.get("fuente") or "", "")
        if pref == "En casa, " and "en casa" in normalizar(t):
            pref = ""
        cuerpo = _minuscula(t, nombre)
        if i == 0 and inicio and pref in ("", "En el aula, ", "En casa, "):
            # «Durante este trimestre, en el aula Ana se muestra…»
            lugar = pref[:-2].lower() + " " if pref else ""
            t = inicio + lugar + (_con_nombre(cuerpo, nombre) if nombre else cuerpo)
        elif pref:
            t = pref + cuerpo
        if i > 0:
            con = CONECTORES[(i - 1 + indice) % len(CONECTORES)]
            if con and not EMPIEZA_CONECTOR.match(t):
                t = con + _minuscula(t, nombre)
        partes.append(_punto(_mayuscula(t)))
    return " ".join(partes)


def _orientacion(t: str) -> str:
    """«Recomendar a la familia que lea cuentos» → «Os animamos a que lea cuentos»."""
    t2 = re.sub(r"^(?:recomendar|aconsejar|sugerir|decir|pedir)(?:le)? a (?:la familia|los padres|casa)\s+(?:que\s+)?",
                "Os animamos a que ", t, flags=re.I)
    if t2 != t:
        return t2
    t2 = re.sub(r"^(?:se )?(?:recomienda|aconseja|sugiere)\s+(?:a la familia\s+)?(?:que\s+)?",
                "Es recomendable que ", t, flags=re.I)
    if t2 != t:
        return t2
    primera = normalizar(t.split(" ")[0]) if t else ""
    if re.match(r"^[a-zñ]+(ar|er|ir)(lo|la|le|se)?$", primera) and primera not in ("mejor", "lugar", "hogar"):
        return "Es recomendable " + _minuscula(t)
    return t


def _clasificar(texto: str, fuente: str) -> str:
    n = f" {normalizar(texto)} "
    if any(p in n for p in PISTAS_ORIENTACION):
        return "orientaciones"
    if any(normalizar(p) in n for p in PISTAS_ESTRATEGIA):
        return "estrategias"
    for clave, _, pistas, _ in AMBITOS:
        if any(normalizar(p) in n for p in pistas):
            return "area:" + clave
    if fuente != "aula" and fuente != "familia" and any(p in n for p in PISTAS_ACTITUD):
        return "actitud"
    return "social"


def _areas_alumno(store: Store, alumno_id: int, trimestre: int, curso_escolar: str) -> list[str]:
    inf = store.q1("SELECT id FROM informes WHERE alumno_id = ? AND trimestre = ? AND curso_escolar = ?",
                   (alumno_id, trimestre, curso_escolar))
    if inf:
        nombres = [r["area"] for r in store.q("SELECT area FROM informe_areas WHERE informe_id = ? ORDER BY orden, id",
                                               (inf["id"],))]
        if nombres:
            return nombres
    aci = informes._aci_para(store, alumno_id, trimestre, curso_escolar)
    return [a["nombre"] for a in (aci or {}).get("areas", []) if a.get("nombre")]


def _area_para(ambito: str, areas: list[str]) -> str:
    _, titulo, _, nombres = next(a for a in AMBITOS if a[0] == ambito)
    for p in nombres:  # por orden de preferencia: «Lectoescritura» antes que «Comunicación y lenguaje»
        for area in areas:
            if p in normalizar(area):
                return area
    return titulo


def borrador(store: Store, junta_id: int, alumno_id: int, especialidad: str = "PT/AL") -> dict:
    """Borrador profesional, repartido por los apartados del informe del trimestre."""
    j = _junta(store, junta_id)
    al = store.q1("SELECT * FROM alumnos WHERE id = ?", (alumno_id,))
    if not al:
        raise StoreError("Alumno no encontrado")
    fila = store.q1("SELECT notas FROM junta_alumnos WHERE junta_id = ? AND alumno_id = ?", (junta_id, alumno_id))
    lista = frases((fila or {}).get("notas", ""))
    nombre = informes._nombre_pila(al["nombre"])
    if al.get("seguimiento") == "observacion":
        grupos: dict[str, list[dict]] = {}
        for f in lista:
            tipo = _clasificar(f["texto"], f["fuente"])
            if tipo == "orientaciones":
                f = {**f, "texto": re.sub(r"^(?:recomendar|aconsejar|sugerir)(?:le)? a ", "Se recomienda a ",
                                           f["texto"], flags=re.I)}
            clave = ("motivo" if f["fuente"] == "orientacion" else "conclusiones" if tipo == "orientaciones"
                     else "estrategias" if tipo == "estrategias" else observacion.apartado_sugerido(f["texto"]))
            grupos.setdefault(clave, []).append(f)
        apartados = [{"clave": k, "titulo": t, "texto": componer(grupos[k], nombre=nombre, indice=i)}
                     for i, (k, t, _) in enumerate(observacion.APARTADOS) if k in grupos]
        return {"tipo": "observacion", "alumno": al["nombre"], "trimestre": j["trimestre"], "apartados": apartados,
                "frases": len(lista)}

    areas = _areas_alumno(store, alumno_id, j["trimestre"], j["curso_escolar"])
    actitud = "actitud_al" if especialidad == "AL" else "actitud_pt"
    grupos = {}
    for f in lista:
        clave = _clasificar(f["texto"], f["fuente"])
        if clave == "actitud":
            n = normalizar(f["texto"])
            clave = "actitud_al" if especialidad == "PT/AL" and re.search(r"\b(al|audicion|logopedia)\b", n) else actitud
        elif clave.startswith("area:"):
            clave = "area:" + _area_para(clave[5:], areas)
        elif clave == "orientaciones":
            f = {**f, "texto": _orientacion(f["texto"]), "fuente": ""}
        grupos.setdefault(clave, []).append(f)

    apartados = []
    inicios = {"social": "Durante este trimestre, ", "actitud_pt": "En las sesiones de PT, ",
               "actitud_al": "En las sesiones de AL, "}
    for base in ORDEN_INFORME:
        claves = [k for k in grupos if k.startswith("area:")] if base == "area" else [base] if base in grupos else []
        for k in claves:
            if k.startswith("area:"):
                area = k[5:]
                i = len([a for a in apartados if a["clave"].startswith("area:")])
                conector = informes.CONECTORES[i % len(informes.CONECTORES)].format(area=informes._nombre_area(area))
                texto = componer(grupos[k], inicio=conector + ", ", indice=i)
                apartados.append({"clave": k, "titulo": f"Área: {area}", "texto": texto})
            else:
                inicio = inicios.get(k, "")
                if inicio and any("sesion" in normalizar(f["texto"]) for f in grupos[k][:1]):
                    inicio = ""
                texto = componer(grupos[k], inicio=inicio, nombre=nombre if k == "social" else "")
                apartados.append({"clave": k, "titulo": TITULOS_INFORME[k], "texto": texto})
    return {"tipo": "informe", "alumno": al["nombre"], "trimestre": j["trimestre"], "apartados": apartados,
            "frases": len(lista)}


# ======================================================================= pasar al informe
def _anadir(actual: str, texto: str) -> str:
    actual = (actual or "").strip()
    if not texto or texto in actual:
        return actual
    return f"{actual}\n{texto}" if actual else texto


def pasar_al_informe(store: Store, junta_id: int, alumno_id: int, apartados: list[dict], maestra: str = "") -> dict:
    """Añade el borrador (ya revisado) al informe del trimestre; lo crea si no existe.
    No borra nada de lo que ya hubiera: el texto se añade al final de cada apartado."""
    j = _junta(store, junta_id)
    al = store.q1("SELECT * FROM alumnos WHERE id = ?", (alumno_id,))
    if not al:
        raise StoreError("Alumno no encontrado")
    apartados = [a for a in (apartados or []) if (a.get("texto") or "").strip()]
    if not apartados:
        raise StoreError("No hay texto que pasar al informe")
    if al.get("seguimiento") == "observacion":
        previo = observacion.listar(store, alumno_id)
        inf_id = previo[0]["id"] if previo else observacion.crear(store, alumno_id, maestra=maestra)
        existentes = {r["clave"]: r for r in store.q("SELECT * FROM observacion_apartados WHERE informe_id = ?",
                                                      (inf_id,)) if r["clave"]}
        for a in apartados:
            r = existentes.get(a.get("clave"))
            if not r:
                titulo = observacion.TITULOS.get(a.get("clave"), a.get("titulo") or "Otras observaciones")
                nuevo = observacion.anadir_apartado(store, inf_id, titulo)
                r = store.q1("SELECT * FROM observacion_apartados WHERE id = ?", (nuevo,))
            store.actualizar("observacion_apartados", r["id"], {"texto": _anadir(r["texto"], a["texto"].strip())})
        tipo = "observacion"
    else:
        inf_id = informes.crear(store, alumno_id, j["trimestre"], j["curso_escolar"], maestra=maestra)
        inf = informes.obtener(store, inf_id)
        for a in apartados:
            clave, texto = a.get("clave") or "", a["texto"].strip()
            if clave in TITULOS_INFORME:
                store.actualizar("informes", inf_id, {clave: _anadir(inf.get(clave), texto)})
                inf[clave] = _anadir(inf.get(clave), texto)
            elif clave.startswith("area:"):
                nombre = clave[5:]
                area = next((x for x in inf["areas"] if informes._clave_area(x["area"]) == informes._clave_area(nombre)),
                            None)
                if not area:
                    nuevo = informes.anadir_area(store, inf_id, nombre)
                    area = {"id": nuevo, "texto": ""}
                    inf["areas"].append({"id": nuevo, "area": nombre, "texto": ""})
                store.actualizar("informe_areas", area["id"], {"texto": _anadir(area.get("texto"), texto)})
        tipo = "informe"
    with store.tx() as c:
        c.execute("""INSERT INTO junta_alumnos(junta_id, alumno_id, pasado) VALUES (?, ?, CURRENT_TIMESTAMP)
                     ON CONFLICT(junta_id, alumno_id) DO UPDATE SET pasado = CURRENT_TIMESTAMP""", (junta_id, alumno_id))
    return {"tipo": tipo, "id": inf_id}
