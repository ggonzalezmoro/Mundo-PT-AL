"""Redacción «humana» del informe para las familias a partir de la ACI.

El informe no copia los ítems tal cual (para eso está la ACI): convierte cada ítem
conseguido en una frase natural («ha conseguido señalar lo que quiere») y describe lo
que todavía no ha conseguido por temas (las competencias), sin enumerar la ACI.

Los ítems de las ACIs empiezan por un verbo en tercera persona («Señala…»,
«Se pone…», «Abre y cierra…»); aquí se pasan a infinitivo."""
from __future__ import annotations

import re
import unicodedata

# Formas irregulares, con cambio de raíz o en -ir (el resto se deduce: -a → -ar, -e → -er)
VERBOS = {
    # -ar con cambio de raíz o irregulares
    "muestra": "mostrar", "cuenta": "contar", "juega": "jugar", "recuerda": "recordar",
    "encuentra": "encontrar", "prueba": "probar", "cuelga": "colgar", "suelta": "soltar",
    "acuesta": "acostar", "piensa": "pensar", "empieza": "empezar", "comienza": "comenzar",
    "cierra": "cerrar", "despierta": "despertar", "sienta": "sentar", "aprieta": "apretar",
    "riega": "regar", "friega": "fregar", "merienda": "merendar", "calienta": "calentar",
    "vuela": "volar", "rueda": "rodar", "sueña": "soñar", "almuerza": "almorzar", "esfuerza": "esforzar",
    "da": "dar", "está": "estar", "va": "ir", "es": "ser", "para": "parar",
    # -er irregulares
    "mantiene": "mantener", "tiene": "tener", "detiene": "detener", "obtiene": "obtener",
    "contiene": "contener", "entiende": "entender", "atiende": "atender", "enciende": "encender",
    "defiende": "defender", "pierde": "perder", "extiende": "extender", "mueve": "mover",
    "resuelve": "resolver", "vuelve": "volver", "devuelve": "devolver", "puede": "poder",
    "quiere": "querer", "hace": "hacer", "deshace": "deshacer", "pone": "poner", "dispone": "disponer",
    "compone": "componer", "propone": "proponer", "huele": "oler", "lee": "leer", "ve": "ver",
    "sabe": "saber", "cae": "caer", "trae": "traer", "coge": "coger", "recoge": "recoger",
    "escoge": "escoger", "muerde": "morder", "suele": "soler",
    # -ir
    "adquiere": "adquirir", "requiere": "requerir",
    "sigue": "seguir", "consigue": "conseguir", "distingue": "distinguir",
    "pide": "pedir", "impide": "impedir", "mide": "medir", "repite": "repetir", "compite": "competir",
    "viste": "vestir", "desviste": "desvestir", "sirve": "servir", "dice": "decir", "elige": "elegir",
    "corrige": "corregir", "dirige": "dirigir", "construye": "construir", "destruye": "destruir",
    "incluye": "incluir", "distribuye": "distribuir", "sustituye": "sustituir", "produce": "producir",
    "reproduce": "reproducir", "introduce": "introducir", "traduce": "traducir", "conduce": "conducir",
    "siente": "sentir", "prefiere": "preferir", "duerme": "dormir", "sonríe": "sonreír", "ríe": "reír",
    "oye": "oír", "sale": "salir", "viene": "venir", "abre": "abrir", "escribe": "escribir",
    "describe": "describir", "recibe": "recibir", "percibe": "percibir", "sube": "subir",
    "comparte": "compartir", "parte": "partir", "reparte": "repartir", "divide": "dividir",
    "decide": "decidir", "une": "unir", "reúne": "reunir", "cumple": "cumplir", "añade": "añadir",
    "aplaude": "aplaudir", "acude": "acudir", "sacude": "sacudir", "emite": "emitir", "omite": "omitir",
    "admite": "admitir", "permite": "permitir", "transmite": "transmitir", "asiste": "asistir",
    "insiste": "insistir", "resiste": "resistir", "persiste": "persistir", "imprime": "imprimir",
    "discute": "discutir", "vive": "vivir", "descubre": "descubrir", "cubre": "cubrir",
    "interrumpe": "interrumpir", "confunde": "confundir", "huye": "huir", "contribuye": "contribuir",
    "advierte": "advertir", "convierte": "convertir", "divierte": "divertir",
}
# Verbos regulares frecuentes en las ACIs: los únicos que se aceptan como segundo verbo
# coordinado («Coge la mochila y la cuelga»), para no confundirlos con sustantivos.
REGULARES = set("""
lleva guarda pega despega coloca toma saca mete usa utiliza deja nombra señala entrega participa
alterna mira escucha presta imita empareja clasifica relaciona identifica reconoce responde comprende
aprende permanece obedece acepta respeta espera inicia termina finaliza completa realiza expresa
comenta pregunta contesta busca lanza salta corta ensarta amasa enrolla aplasta pinta colorea dibuja
traza copia recorta rasga arruga lava seca peina quita cambia tolera regula anticipa colabora
""".split())
CLITICOS = ("la", "lo", "las", "los", "le", "les")
NO_VERBOS = {"de", "que", "este", "esta", "ese", "esa", "una", "nombre", "cada", "entre", "ante", "sobre",
             "hasta", "desde", "contra", "durante", "mediante", "siempre", "mientras", "donde", "como",
             "cuando", "parte", "forma", "manera", "vez", "nunca", "ahora", "mucha", "poca", "toda"}


def _sin_tilde(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _limpia(palabra: str) -> str:
    return re.sub(r"[^\wáéíóúüñ]", "", palabra.lower())


def infinitivo_verbo(palabra: str) -> str | None:
    """«Señala» → «señalar», «Continúa» → «continuar», «Sigue» → «seguir»."""
    p = _limpia(palabra)
    if p in VERBOS:
        return VERBOS[p]
    if p in NO_VERBOS or len(p) < 3 or not p.isalpha():
        return None
    if p.endswith(("ía", "úa")):  # envía → enviar, continúa → continuar
        return p[:-2] + _sin_tilde(p[-2]) + "ar"
    if p.endswith("a"):
        return p[:-1] + "ar"
    if p.endswith("e"):
        return p[:-1] + "er"
    return None


def _es_verbo_seguro(palabra: str) -> bool:
    p = _limpia(palabra)
    return p in VERBOS or p in REGULARES


def _coordinados(texto: str) -> str:
    """Pasa a infinitivo los verbos tras « y »/« o » en la oración principal
    (antes de dos puntos, «cuando», «que»…): «… y la cuelga» → «… y colgarla»."""
    corte = re.search(r"[:(]|\b(cuando|que|si|mientras|porque|pero|para)\b", texto)
    principal, cola = (texto[:corte.start()], texto[corte.start():]) if corte else (texto, "")

    def cambiar(m):
        conj, clitico, verbo = m.group(1), m.group(2), m.group(3)
        if not _es_verbo_seguro(verbo):
            return m.group(0)
        return f"{conj} {infinitivo_verbo(verbo)}{(clitico or '').strip().lower()}"

    principal = re.sub(r"\b(y|o)\s+((?:la|lo|las|los|le|les)\s+)?([a-záéíóúñ]+)\b", cambiar, principal)
    return (principal + cola).strip()


def a_infinitivo(texto: str) -> str | None:
    """«Coge la mochila y la cuelga con o sin ayuda» → «coger la mochila y colgarla con o sin ayuda».
    Devuelve None si el ítem no empieza por un verbo reconocible."""
    palabras = (texto or "").split()
    if not palabras:
        return None
    reflexivo = ""
    if palabras[0].lower() == "se" and len(palabras) > 1:
        reflexivo, palabras = "se", palabras[1:]
    inf = infinitivo_verbo(palabras[0])
    if not inf:
        return None
    resto = palabras[1:]
    cabeza = [inf + reflexivo]
    # «Se pone y quita los zapatos» → «ponerse y quitarse los zapatos»
    if len(resto) >= 2 and resto[0].lower() in ("y", "o") and _es_verbo_seguro(resto[1]):
        cabeza += [resto[0].lower(), infinitivo_verbo(resto[1]) + reflexivo]
        resto = resto[2:]
    return " ".join(cabeza + ([_coordinados(" ".join(resto))] if resto else [])).strip()


def _separar_ejemplo(texto: str) -> tuple[str, str]:
    """Quita «(Ej.: …)» y devuelve (texto, ejemplo)."""
    m = re.search(r"\(\s*ej(?:emplo)?\.?\s*:?\s*([^)]*)\)", texto, re.I)
    if not m:
        return texto, ""
    return (texto[:m.start()] + texto[m.end():]).strip(), m.group(1).strip().rstrip(".")


def _primera_frase(texto: str) -> str:
    """Solo la primera oración (algunos ítems llevan anotaciones detrás)."""
    partes = re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", texto.strip(), maxsplit=1)
    return partes[0].strip().rstrip(".; ")


def _detalle(nota: str) -> str:
    """Observación propia de la maestra para el ítem, si es breve."""
    n = " ".join((nota or "").split()).strip(" .")
    # Anotaciones con paréntesis («camión(no)») son apuntes de la maestra: no se copian
    if not n or len(n) > 90 or "(" in n:
        return ""
    if n.isupper():
        n = n.lower()
    return n if n[:2].isupper() else n[:1].lower() + n[1:]


def redactar_item(texto: str, nota: str = "", con_detalle: bool = True) -> str:
    """Ítem de la ACI → fragmento en infinitivo listo para «ha conseguido …»."""
    t, ejemplo = _separar_ejemplo(texto or "")
    t = _primera_frase(t)
    if not t:
        return ""
    inf = a_infinitivo(t)
    base = inf if inf else f"lo relativo a «{t[:1].lower() + t[1:]}»"
    if con_detalle:
        detalle = _detalle(nota)
        if detalle:
            base += f" ({detalle})"
        elif ejemplo:
            base += f" (por ejemplo, {ejemplo})"
    return base


def sin_comenzar(inf: str) -> str:
    """«comenzar a identificar …» → «identificar …» (para lo que aún no ha conseguido)."""
    return re.sub(r"^(comenzar|empezar|iniciarse) a\s+", "", inf)


def tema(competencia: str) -> str:
    """Nombre de la competencia como tema: «Desarrollar la atención conjunta» → «la atención conjunta»,
    «Desarrollar la sintaxis - lenguaje receptivo» → «la sintaxis (lenguaje receptivo)»."""
    n = " ".join((competencia or "").split()).strip(" .:")
    n = re.sub(r"^(desarrollar|desarrollo de|trabajar|mejorar|potenciar|favorecer|adquirir)\s+", "", n, flags=re.I)
    logico = re.match(r"^l[óo]gico[\s-]*matem[áa]ticas?\s*[-–:]?\s*(.*)$", n, re.I)
    if logico:
        resto = logico.group(1).strip()
        return f"la parte lógico-matemática ({resto[:1].lower() + resto[1:]})" if resto else "la parte lógico-matemática"
    m = re.search(r"\s*[-–]\s+|\s+[-–]\s*", n)
    if m:
        n = f"{n[:m.start()]} ({n[m.end():]})"
    if not n:
        return ""
    if not n[:2].isupper():
        n = n[0].lower() + n[1:]
    if not re.match(r"^(el|la|los|las|un|una|su|sus)\s", n, re.I):
        primera = _sin_tilde(n.split()[0].lower().strip(",("))
        if primera.endswith("s"):
            art = "las" if primera.endswith(("as", "ones", "des")) else "los"
        else:
            art = "la" if primera.endswith(("a", "ion", "dad", "tud")) else "el"
        n = f"{art} {n}"
    return n


def unir(partes: list[str]) -> str:
    """«a, b y c» (con «e» delante de «i-»)."""
    partes = [p for p in partes if p]
    if len(partes) <= 1:
        return "".join(partes)
    conj = "e" if re.match(r"^h?i(?![aeou])", _sin_tilde(partes[-1][:3].lower())) else "y"
    return ", ".join(partes[:-1]) + f" {conj} " + partes[-1]
