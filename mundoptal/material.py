"""Material para trabajar con los alumnos: fichas (Word) y diapositivas (PowerPoint).

Todo el material se describe con un MaterialSpec (título, objetivo y páginas con un
tipo de actividad de una lista cerrada). El MaterialSpec lo pueden crear:
  - las plantillas de este módulo, sin Internet, a partir de un tipo y un contenido;
  - Claude (ia_material.py), a partir de una petición libre de la maestra.
Después maqueta.py lo convierte en .docx o .pptx con el estilo del colegio."""
from __future__ import annotations

import random
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel

Actividad = Literal["letra", "repasar", "rodear", "unir", "completar", "contar", "clasificar",
                    "secuencia", "tarjetas", "pregunta", "cuento"]

ACTIVIDADES = {
    "letra": "Letra o número grande para presentar (y hueco para repasar)",
    "repasar": "Repasar con el lápiz siguiendo el modelo punteado",
    "rodear": "Rodear los elementos correctos entre varios",
    "unir": "Unir con flechas cada elemento con su pareja",
    "completar": "Completar palabras o frases con el hueco que falta",
    "contar": "Contar los elementos y rodear el número",
    "clasificar": "Clasificar elementos en grupos",
    "secuencia": "Ordenar los pasos de una secuencia",
    "tarjetas": "Tarjetas de vocabulario con imagen y palabra",
    "pregunta": "Pregunta con opciones para rodear la respuesta",
    "cuento": "Cuento o frases cortas con pictogramas",
}


class Elemento(BaseModel):
    texto: str          # palabra, letra, número o frase corta
    pictograma: str     # palabra clave para buscar el pictograma ("" si no lleva)
    pareja: str         # «unir»: el elemento de la otra columna; «completar»: la solución
    correcto: bool      # «rodear» / «pregunta»: si es la respuesta correcta
    grupo: str          # «clasificar»: grupo al que pertenece
    cantidad: int       # «contar»: cuántos objetos dibujar (0 si no aplica)


class Pagina(BaseModel):
    actividad: Actividad
    enunciado: str      # instrucción corta para el alumno («Rodea la letra A»)
    destacado: str      # letra, número o palabra principal de la página ("" si no hay)
    elementos: list[Elemento]


class MaterialSpec(BaseModel):
    titulo: str
    objetivo: str
    instrucciones_maestra: str
    paginas: list[Pagina]


def el(texto="", pictograma="", pareja="", correcto=False, grupo="", cantidad=0) -> Elemento:
    return Elemento(texto=texto, pictograma=pictograma, pareja=pareja, correcto=correcto, grupo=grupo,
                    cantidad=cantidad)


def pag(actividad, enunciado, destacado="", elementos=None) -> Pagina:
    return Pagina(actividad=actividad, enunciado=enunciado, destacado=destacado, elementos=elementos or [])


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ vocabulario
# Palabras que empiezan por cada letra (con pictograma de ARASAAC o emoji de reserva)
PALABRAS_LETRA = {
    "A": ["avión", "abeja", "árbol", "anillo"], "E": ["elefante", "estrella", "erizo", "escoba"],
    "I": ["isla", "iglú", "imán", "iguana"], "O": ["oso", "oveja", "ojo", "ola"],
    "U": ["uva", "uña", "unicornio", "uno"], "M": ["mano", "mono", "manzana", "mesa"],
    "P": ["pato", "pera", "perro", "pez"], "L": ["luna", "león", "limón", "lápiz"],
    "S": ["sol", "sapo", "seta", "silla"], "T": ["tomate", "tren", "tortuga", "taza"],
    "N": ["nube", "nido", "naranja", "nariz"], "D": ["dado", "dedo", "delfín", "dinosaurio"],
    "B": ["barco", "ballena", "boca", "bota"], "C": ["casa", "coche", "caracol", "conejo"],
    "G": ["gato", "gallina", "gafas", "globo"], "F": ["foca", "flor", "fresa", "fuego"],
    "R": ["ratón", "rana", "rosa", "reloj"], "V": ["vaca", "vaso", "vela", "volcán"],
    "J": ["jirafa", "jabón", "jarra", "juguete"], "Ñ": ["ñu", "ñandú"], "Z": ["zapato", "zorro", "zanahoria", "zumo"],
    "Y": ["yate", "yogur", "yoyó"], "CH": ["chocolate", "chaqueta", "churro"], "LL": ["llave", "lluvia", "llama"],
    "H": ["helado", "hoja", "huevo", "hormiga"], "K": ["koala", "kiwi"], "Q": ["queso"], "W": ["wifi"], "X": ["xilófono"],
}
# Palabras de dos sílabas por consonante (para leer y completar)
SILABAS_PALABRAS = {
    "M": [("ma", "no"), ("mo", "no"), ("me", "sa"), ("mi", "mo"), ("mu", "la")],
    "P": [("pa", "to"), ("pe", "ra"), ("pi", "pa"), ("po", "llo"), ("pu", "ma")],
    "L": [("lu", "na"), ("lo", "ro"), ("la", "ta"), ("li", "ma"), ("le", "che")],
    "S": [("so", "pa"), ("se", "ta"), ("si", "lla"), ("sa", "po"), ("su", "mo")],
    "T": [("ta", "za"), ("to", "ro"), ("tu", "bo"), ("te", "la"), ("ti", "za")],
    "N": [("ni", "do"), ("nu", "be"), ("no", "che"), ("na", "ta")],
    "D": [("da", "do"), ("de", "do"), ("du", "cha"), ("di", "no")],
    "B": [("bo", "ca"), ("ba", "ño"), ("bo", "ta"), ("bu", "rro")],
    "C": [("ca", "sa"), ("co", "pa"), ("cu", "na"), ("co", "che")],
    "G": [("ga", "to"), ("go", "ma"), ("ga", "fas"), ("go", "rro")],
    "F": [("fo", "ca"), ("fa", "ro"), ("fo", "to"), ("fi", "la")],
    "R": [("ro", "sa"), ("ra", "na"), ("ro", "ca"), ("ru", "da")],
    "V": [("va", "ca"), ("ve", "la"), ("va", "so"), ("vi", "no")],
    "J": [("ja", "rra"), ("jo", "ya"), ("ju", "go")],
    "Ñ": [("ni", "ño"), ("ba", "ño"), ("pi", "ña")],
}
CAMPOS = {
    "comida": ["manzana", "plátano", "pan", "leche", "queso", "pizza", "zanahoria", "tomate"],
    "colegio": ["lápiz", "libro", "mochila", "tijeras", "pegamento", "pizarra", "silla", "mesa"],
    "casa": ["cama", "puerta", "ventana", "bañera", "sofá", "llave", "mesa", "lámpara"],
    "ropa": ["camiseta", "pantalón", "zapatillas", "calcetines", "gorro", "abrigo", "falda", "bufanda"],
    "transporte": ["coche", "autobús", "bicicleta", "avión", "tren", "barco", "moto", "camión"],
    "animales": ["perro", "gato", "vaca", "cerdo", "caballo", "rana", "pez", "pájaro"],
    "cuerpo": ["cabeza", "mano", "pie", "ojo", "boca", "nariz", "oreja", "pelo"],
}
EMOCIONES = [("alegre", "alegre"), ("triste", "triste"), ("enfadado", "enfadado"), ("asustado", "miedo")]

# Emoji de reserva cuando no hay pictograma (sin Internet o pictogramas desactivados)
EMOJI = {
    "avión": "✈️", "abeja": "🐝", "árbol": "🌳", "anillo": "💍", "elefante": "🐘", "estrella": "⭐", "erizo": "🦔",
    "escoba": "🧹", "isla": "🏝️", "iglú": "🧊", "imán": "🧲", "iguana": "🦎", "oso": "🐻", "oveja": "🐑", "ojo": "👁️",
    "ola": "🌊", "uva": "🍇", "uña": "💅", "unicornio": "🦄", "uno": "1️⃣", "mano": "✋", "mono": "🐒", "manzana": "🍎",
    "mesa": "🪑", "pato": "🦆", "pera": "🍐", "perro": "🐶", "pez": "🐟", "luna": "🌙", "león": "🦁", "limón": "🍋",
    "lápiz": "✏️", "sol": "☀️", "sapo": "🐸", "seta": "🍄", "silla": "🪑", "tomate": "🍅", "tren": "🚂",
    "tortuga": "🐢", "taza": "☕", "nube": "☁️", "nido": "🪺", "naranja": "🍊", "nariz": "👃", "dado": "🎲",
    "dedo": "☝️", "delfín": "🐬", "dinosaurio": "🦕", "barco": "⛵", "ballena": "🐳", "boca": "👄", "bota": "👢",
    "casa": "🏠", "coche": "🚗", "caracol": "🐌", "conejo": "🐰", "gato": "🐱", "gallina": "🐔", "gafas": "👓",
    "globo": "🎈", "foca": "🦭", "flor": "🌸", "fresa": "🍓", "fuego": "🔥", "ratón": "🐭", "rana": "🐸", "rosa": "🌹",
    "reloj": "⏰", "vaca": "🐮", "vaso": "🥛", "vela": "🕯️", "volcán": "🌋", "jirafa": "🦒", "jabón": "🧼",
    "juguete": "🧸", "zapato": "👞", "zorro": "🦊", "zanahoria": "🥕", "zumo": "🧃", "yogur": "🥛", "helado": "🍦",
    "hoja": "🍃", "huevo": "🥚", "hormiga": "🐜", "koala": "🐨", "kiwi": "🥝", "queso": "🧀", "llave": "🔑",
    "lluvia": "🌧️", "chocolate": "🍫", "plátano": "🍌", "pan": "🍞", "leche": "🥛", "pizza": "🍕", "libro": "📚",
    "mochila": "🎒", "tijeras": "✂️", "pegamento": "🧴", "pizarra": "🧑‍🏫", "cama": "🛏️", "puerta": "🚪",
    "ventana": "🪟", "bañera": "🛁", "sofá": "🛋️", "lámpara": "💡", "camiseta": "👕", "pantalón": "👖",
    "zapatillas": "👟", "calcetines": "🧦", "gorro": "🧢", "abrigo": "🧥", "falda": "👗", "bufanda": "🧣",
    "autobús": "🚌", "bicicleta": "🚲", "moto": "🏍️", "camión": "🚚", "cerdo": "🐷", "caballo": "🐴",
    "pájaro": "🐦", "cabeza": "🙂", "pie": "🦶", "oreja": "👂", "pelo": "💇", "alegre": "😀", "triste": "😢",
    "enfadado": "😠", "miedo": "😨", "asustado": "😨", "pelota": "⚽", "círculo": "⚪", "cuadrado": "🟥",
    "triángulo": "🔺", "corazón": "❤️", "pollo": "🍗", "copa": "🏆", "foto": "📷", "faro": "🗼", "lata": "🥫",
    "loro": "🦜", "toro": "🐂", "niño": "🧒", "baño": "🚽", "piña": "🍍", "burro": "🫏", "cuna": "🛏️",
    "ducha": "🚿", "noche": "🌙", "agua": "💧", "caja": "📦",
}


def emoji_de(palabra: str) -> str:
    p = (palabra or "").strip().lower()
    return EMOJI.get(p) or EMOJI.get(sin_tildes(p)) or ""


# ------------------------------------------------------------------ plantillas
TIPOS = {
    "letras": {"nombre": "Vocales o letras", "ejemplo": "A E I O U", "ayuda": "Letras separadas por espacios, o «vocales»."},
    "silabas": {"nombre": "Sílabas", "ejemplo": "M P L", "ayuda": "Consonantes para formar sílabas (MA ME MI MO MU)."},
    "numeros": {"nombre": "Números y cantidades", "ejemplo": "1-5", "ayuda": "Un rango («1-5») o números sueltos («1 2 3»)."},
    "emparejar": {"nombre": "Emparejar", "ejemplo": "A E I O U", "ayuda": "Letras (mayúscula-minúscula), números (número-cantidad) o palabras (iguales)."},
    "espaciales": {"nombre": "Conceptos espaciales", "ejemplo": "arriba abajo dentro fuera grande pequeño",
                   "ayuda": "Conceptos: arriba/abajo, dentro/fuera, grande/pequeño."},
    "emociones": {"nombre": "Emociones básicas", "ejemplo": "alegre triste enfadado asustado", "ayuda": "Emociones que quieres trabajar."},
    "vocabulario": {"nombre": "Tarjetas de vocabulario", "ejemplo": "animales",
                    "ayuda": "Campo semántico (comida, colegio, casa, ropa, transporte, animales, cuerpo) o palabras sueltas."},
}
NIVELES = {"3": {"rejilla": 6, "opciones": 3, "max_num": 3}, "4": {"rejilla": 9, "opciones": 4, "max_num": 5},
           "5": {"rejilla": 12, "opciones": 5, "max_num": 10}}


def _letras(contenido: str) -> list[str]:
    t = (contenido or "").strip()
    if not t or "vocal" in t.lower():
        return list("AEIOU")
    letras = []
    for tok in re.split(r"[\s,;]+", t.upper()):
        if tok in ("CH", "LL"):
            letras.append(tok)
        else:
            letras += [c for c in tok if c.isalpha()]
    return list(dict.fromkeys(letras)) or list("AEIOU")


def _numeros(contenido: str) -> list[int]:
    t = (contenido or "").strip()
    m = re.match(r"^\s*(\d+)\s*[-–a]\s*(\d+)\s*$", t)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return list(range(max(0, a), min(20, b) + 1))
    nums = [int(x) for x in re.findall(r"\d+", t) if int(x) <= 20]
    return list(dict.fromkeys(nums)) or [1, 2, 3, 4, 5]


def _palabras(contenido: str) -> list[str]:
    t = sin_tildes((contenido or "").lower())
    for campo, lista in CAMPOS.items():
        if campo in t or (campo == "animales" and "animal" in t) or (campo == "cuerpo" and "cuerpo" in t):
            return lista
    return [p for p in re.split(r"[\s,;]+", (contenido or "").strip().lower()) if p] or CAMPOS["animales"]


def _ajustar(paginas: list[Pagina], num: int | None) -> list[Pagina]:
    """Recorta al número pedido o repite el ciclo para completarlo (máximo 40)."""
    if not num or num <= 0:
        return paginas[:40]
    num = min(int(num), 40)
    salida = []
    while len(salida) < num and paginas:
        salida += paginas[: num - len(salida)]
    return salida


def plantilla(tipo: str, contenido: str = "", nivel: str = "4", num: int | None = None, semilla: int | None = None) -> MaterialSpec:
    """Material sin Internet a partir de un tipo de plantilla y su contenido."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de material no válido: {tipo}")
    rnd = random.Random(semilla)
    cfg = NIVELES.get(str(nivel), NIVELES["4"])
    paginas = globals()[f"_plantilla_{tipo}"](contenido, cfg, rnd)
    return MaterialSpec(titulo=_titulo(tipo, contenido), objetivo=_objetivo(tipo, contenido),
                        instrucciones_maestra="Material creado con las plantillas de Mundo PT-AL. Adáptalo a cada alumno.",
                        paginas=_ajustar(paginas, num))


def _titulo(tipo, contenido):
    if tipo == "letras":
        letras = _letras(contenido)
        return "Las vocales" if letras == list("AEIOU") else "Letras: " + " ".join(letras)
    if tipo == "silabas":
        return "Sílabas con " + ", ".join(_letras(contenido))
    if tipo == "numeros":
        n = _numeros(contenido)
        return f"Números del {n[0]} al {n[-1]}" if len(n) > 1 else f"El número {n[0]}"
    if tipo == "vocabulario":
        return "Vocabulario: " + ((contenido or "animales").strip().lower())
    return TIPOS[tipo]["nombre"]


def _objetivo(tipo, contenido):
    return {
        "letras": "Reconocer y trazar las letras, y asociarlas a palabras que empiezan por ellas.",
        "silabas": "Formar y leer sílabas directas, y completar palabras de dos sílabas.",
        "numeros": "Reconocer y trazar los números y asociarlos a su cantidad.",
        "emparejar": "Discriminar y emparejar elementos iguales o relacionados.",
        "espaciales": "Comprender conceptos espaciales básicos.",
        "emociones": "Reconocer y nombrar emociones básicas.",
        "vocabulario": "Ampliar el vocabulario de un campo semántico.",
    }[tipo]


def _plantilla_letras(contenido, cfg, rnd):
    letras = _letras(contenido)
    por_letra = []
    for L in letras:
        paginas = []
        por_letra.append(paginas)
        palabras = PALABRAS_LETRA.get(sin_tildes(L), [])
        paginas.append(pag("letra", f"Esta es la letra {L}", f"{L} {L.lower()}",
                           [el(p, p) for p in palabras[:3]]))
        paginas.append(pag("repasar", f"Repasa la letra {L}", f"{L} {L.lower()}"))
        otras = [x for x in "AEIOUMPLSTN" if x != L]
        celdas = [L] * max(2, cfg["rejilla"] // 3) + rnd.sample(otras, cfg["rejilla"] - max(2, cfg["rejilla"] // 3))
        rnd.shuffle(celdas)
        paginas.append(pag("rodear", f"Rodea todas las letras {L}", L, [el(c, correcto=(c == L)) for c in celdas]))
        if palabras:
            distractores = [p for k, v in PALABRAS_LETRA.items() if k != sin_tildes(L) and k in "AEIOUMPLST" for p in v[:1]]
            opciones = palabras[:2] + rnd.sample(distractores, min(len(distractores), cfg["opciones"] - 2))
            rnd.shuffle(opciones)
            paginas.append(pag("rodear", f"Rodea los dibujos que empiezan por {L}", L,
                               [el(p, p, correcto=p in palabras) for p in opciones]))
    # Por actividades: primero todas las presentaciones, luego repasar, etc. (con pocas fichas salen todas las letras)
    return [ps[i] for i in range(4) for ps in por_letra if i < len(ps)]


def _plantilla_silabas(contenido, cfg, rnd):
    paginas = []
    for C in _letras(contenido):
        c = C.lower()
        silabas = [c + v for v in "aeiou"]
        paginas.append(pag("letra", f"Leemos las sílabas con {C}", " ".join(s.upper() for s in silabas)))
        paginas.append(pag("unir", f"Une cada sílaba con la letra {C} y su vocal",
                           elementos=[el(s.upper(), pareja=f"{C} + {s[-1].upper()}") for s in silabas[:cfg["opciones"]]]))
        palabras = SILABAS_PALABRAS.get(sin_tildes(C), [])
        if palabras:
            paginas.append(pag("completar", "Completa la sílaba que falta",
                               elementos=[el(f"___{b}" if i % 2 == 0 else f"{a}___", a + b, pareja=a + b)
                                          for i, (a, b) in enumerate(palabras[:4])]))
            paginas.append(pag("tarjetas", "Lee las palabras", elementos=[el((a + b).upper(), a + b) for a, b in palabras[:4]]))
    return paginas


def _plantilla_numeros(contenido, cfg, rnd):
    nums = _numeros(contenido)
    paginas = []
    for n in nums:
        paginas.append(pag("letra", f"Este es el número {n}", str(n), [el(str(n), cantidad=n)]))
        paginas.append(pag("repasar", f"Repasa el número {n}", str(n)))
    maximo = max(nums)
    grupos = rnd.sample(nums, min(len(nums), 4))
    figuras = ["manzana", "pelota", "flor", "pez", "coche"]
    paginas.append(pag("contar", "Cuenta y rodea el número", str(maximo),
                       [el(figuras[i % len(figuras)], figuras[i % len(figuras)], cantidad=n) for i, n in enumerate(grupos)]))
    paginas.append(pag("unir", "Une cada número con su cantidad",
                       elementos=[el(str(n), pareja="●" * n, cantidad=n) for n in grupos]))
    return paginas


def _plantilla_emparejar(contenido, cfg, rnd):
    t = (contenido or "").strip()
    if re.search(r"\d", t):
        nums = _numeros(t)[:cfg["opciones"] + 1]
        return [pag("unir", "Une cada número con su cantidad", elementos=[el(str(n), pareja="●" * n) for n in nums])]
    letras = _letras(t) if (not t or len(re.split(r"\s+", t)[0]) <= 2 or "vocal" in t.lower()) else None
    if letras:
        paginas = []
        for i in range(0, len(letras), 5):
            grupo = letras[i:i + 5]
            paginas.append(pag("unir", "Une cada mayúscula con su minúscula", elementos=[el(L, pareja=L.lower()) for L in grupo]))
        return paginas
    palabras = _palabras(t)[:5]
    return [pag("unir", "Une cada dibujo con su igual", elementos=[el(p, p, pareja=p) for p in palabras])]


def _plantilla_espaciales(contenido, cfg, rnd):
    t = sin_tildes((contenido or "").lower())
    paginas = []
    if not t or "arriba" in t or "abajo" in t:
        paginas.append(pag("pregunta", "Rodea la pelota que está ARRIBA de la caja", "arriba",
                           [el("arriba", "pelota", correcto=True, grupo="arriba"), el("abajo", "pelota", grupo="abajo")]))
        paginas.append(pag("pregunta", "Rodea la pelota que está ABAJO de la caja", "abajo",
                           [el("arriba", "pelota", grupo="arriba"), el("abajo", "pelota", correcto=True, grupo="abajo")]))
    if not t or "dentro" in t or "fuera" in t:
        paginas.append(pag("pregunta", "Rodea el perro que está DENTRO de la caja", "dentro",
                           [el("dentro", "perro", correcto=True, grupo="dentro"), el("fuera", "perro", grupo="fuera")]))
        paginas.append(pag("pregunta", "Rodea el perro que está FUERA de la caja", "fuera",
                           [el("dentro", "perro", grupo="dentro"), el("fuera", "perro", correcto=True, grupo="fuera")]))
    if not t or "grande" in t or "pequen" in t:
        paginas.append(pag("pregunta", "Rodea la manzana GRANDE", "grande",
                           [el("grande", "manzana", correcto=True, grupo="grande"), el("pequeño", "manzana", grupo="pequeño")]))
        paginas.append(pag("pregunta", "Rodea la manzana PEQUEÑA", "pequeño",
                           [el("grande", "manzana", grupo="grande"), el("pequeño", "manzana", correcto=True, grupo="pequeño")]))
    return paginas


def _plantilla_emociones(contenido, cfg, rnd):
    t = sin_tildes((contenido or "").lower())
    elegidas = [e for e in EMOCIONES if not t or e[0][:5] in t or (e[0] == "asustado" and "miedo" in t)] or EMOCIONES
    paginas = [pag("tarjetas", "Así nos sentimos", elementos=[el(n.upper(), p) for n, p in elegidas])]
    for n, p in elegidas:
        opciones = [(n, p)] + rnd.sample([e for e in EMOCIONES if e[0] != n], min(cfg["opciones"] - 1, len(EMOCIONES) - 1))
        rnd.shuffle(opciones)
        paginas.append(pag("rodear", f"Rodea la cara {n.upper()}", n, [el(x.upper(), q, correcto=(x == n)) for x, q in opciones]))
    paginas.append(pag("unir", "Une cada cara con su nombre", elementos=[el("", p, pareja=n.upper()) for n, p in elegidas]))
    paginas.append(pag("pregunta", "¿Cómo te sientes hoy? Rodea tu cara", "", [el(n.upper(), p) for n, p in elegidas]))
    return paginas


def _plantilla_vocabulario(contenido, cfg, rnd):
    palabras = _palabras(contenido)
    paginas = [pag("tarjetas", "Mira, señala y nombra", elementos=[el(p.upper(), p) for p in palabras[i:i + 4]])
               for i in range(0, len(palabras), 4)]
    objetivo = palabras[0]
    opciones = rnd.sample(palabras, min(len(palabras), cfg["opciones"]))
    if objetivo not in opciones:
        opciones[0] = objetivo
    rnd.shuffle(opciones)
    paginas.append(pag("rodear", f"Rodea: {objetivo.upper()}", objetivo, [el(p.upper(), p, correcto=(p == objetivo)) for p in opciones]))
    paginas.append(pag("unir", "Une cada dibujo con su nombre", elementos=[el("", p, pareja=p.upper()) for p in palabras[:5]]))
    return paginas


# ------------------------------------------------------------------ sugerencias por la ACI
SUGERENCIAS = [
    ("letras", "vocales", r"\bvocal"), ("silabas", "M P L", r"s[ií]laba"), ("letras", "", r"\bletra|grafema|fonema"),
    ("numeros", "1-5", r"n[uú]mero|cantidad|contar|cuenta"), ("espaciales", "", r"arriba|abajo|dentro|fuera|encima|debajo|grande|peque"),
    ("emociones", "", r"emoci|alegr|trist|enfad|asust|miedo"), ("emparejar", "", r"empareja|asocia|relaciona"),
]


def sugerencias(items_pendientes: list[dict]) -> list[dict]:
    """Propone materiales según los ítems de la ACI no conseguidos (texto y competencia)."""
    salida, vistos = [], set()
    for it in items_pendientes:
        texto = sin_tildes(f"{it.get('texto', '')} {it.get('competencia', '')}".lower())
        for tipo, contenido, patron in SUGERENCIAS:
            if re.search(sin_tildes(patron), texto) and (tipo, contenido) not in vistos:
                vistos.add((tipo, contenido))
                salida.append({"tipo": tipo, "contenido": contenido, "motivo": it.get("texto", "")})
        if "vocabulario" in texto or "lexico" in texto:
            for campo in CAMPOS:
                if campo[:5] in texto and ("vocabulario", campo) not in vistos:
                    vistos.add(("vocabulario", campo))
                    salida.append({"tipo": "vocabulario", "contenido": campo, "motivo": it.get("texto", "")})
    return salida[:6]
