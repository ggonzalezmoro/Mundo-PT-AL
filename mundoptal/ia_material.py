"""Crear material con Claude (por Internet), solo para este apartado.

Privacidad: a Claude solo se envía la petición de la maestra (con los nombres de los
alumnos sustituidos), el nivel, el formato y, si se elige un alumno, la lista de
objetivos de su ACI, sin su nombre ni datos personales. Nada más de la aplicación sale
del equipo.

La clave de la API se guarda en el Administrador de credenciales de Windows (keyring),
nunca en la base de datos, en los registros ni en los mensajes."""
from __future__ import annotations

import re

from .material import ACTIVIDADES, MaterialSpec, sin_tildes

MODELO = "claude-opus-5-5"
SERVICIO_CLAVE = "MundoPTAL"
USUARIO_CLAVE = "anthropic_api_key"
MAX_PAGINAS = 20

SISTEMA = f"""Eres una maestra experta en Pedagogía Terapéutica (PT) y Audición y Lenguaje (AL) en Educación Infantil \
(3 a 5 años) en España. Diseñas material imprimible y proyectable para alumnos con necesidades educativas especiales.

Devuelves solo la descripción del material; la aplicación lo maqueta con el estilo del colegio.

Cada página tiene UNA actividad de esta lista (campo «actividad»):
{chr(10).join(f'- {k}: {v}' for k, v in ACTIVIDADES.items())}

Cómo rellenar los campos:
- «enunciado»: una sola línea, corta y clara, en segunda persona («Rodea la letra A», «Une cada animal con su sombra»).
- «destacado»: la letra, número o palabra principal de la página (en «letra» y «repasar», por ejemplo «A a» o «3»); "" si no hay.
- «elementos»: lo que aparece en la página. «texto» corto (una palabra, sílaba, letra o frase muy breve).
- «pictograma»: UNA palabra clave sencilla en español y en singular para buscar el pictograma en ARASAAC \
(«perro», «manzana», «lavarse las manos»); "" si el elemento es solo una letra, número o sílaba.
- «unir»: «texto» a la izquierda y «pareja» a la derecha (la aplicación desordena la derecha). 3 a 5 parejas.
- «rodear» y «pregunta»: «correcto» = true en los elementos que son la respuesta. 4 a 9 elementos en «rodear», 2 a 4 en «pregunta».
- «completar»: «texto» con el hueco como ___ («___to», «el pe___o ladra») y «pareja» con la solución.
- «contar»: «cantidad» de 1 a 10 y «pictograma» del objeto a contar; «destacado» con el número mayor. 3 o 4 elementos.
- «clasificar»: «grupo» de cada elemento (2 o 3 grupos, 6 a 9 elementos).
- «secuencia»: 3 a 5 pasos EN ORDEN correcto (la aplicación los desordena).
- «tarjetas»: 4 elementos por página. «cuento»: 3 a 6 frases cortas, cada una con su pictograma.
- Los campos que no se usan: "" en texto, false en booleanos y 0 en números.

Criterios: actividades adecuadas a la edad y al nivel indicado, lenguaje sencillo, vocabulario cotidiano, \
progresión de fácil a difícil, variedad de actividades y nada que requiera leer textos largos. No incluyas nombres \
de alumnos ni datos personales. «instrucciones_maestra»: 2 o 3 frases con ideas para usar el material y adaptarlo."""


class ErrorIA(Exception):
    """Error con un mensaje para mostrar tal cual a la maestra."""


# ------------------------------------------------------------------ clave de la API (keyring)
def _keyring():
    import keyring
    try:  # En el ejecutable, la detección automática del almacén puede fallar: se fuerza el de Windows
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            from keyring.backends.Windows import WinVaultKeyring
            keyring.set_keyring(WinVaultKeyring())
    except Exception:
        pass
    return keyring


def leer_clave() -> str:
    try:
        return _keyring().get_password(SERVICIO_CLAVE, USUARIO_CLAVE) or ""
    except Exception:
        return ""


def guardar_clave(clave: str) -> None:
    clave = (clave or "").strip()
    if not re.match(r"^sk-ant-[A-Za-z0-9_\-]{20,}$", clave):
        raise ErrorIA("La clave no tiene el formato esperado (empieza por «sk-ant-»). Cópiala completa desde la consola de Claude.")
    _keyring().set_password(SERVICIO_CLAVE, USUARIO_CLAVE, clave)


def borrar_clave() -> None:
    try:
        _keyring().delete_password(SERVICIO_CLAVE, USUARIO_CLAVE)
    except Exception:
        pass


def hay_clave() -> bool:
    return bool(leer_clave())


def _cliente(clave: str | None = None):
    import anthropic
    clave = clave or leer_clave()
    if not clave:
        raise ErrorIA("Falta la clave de Claude. Añádela en Ajustes › Crear material con Claude.")
    return anthropic.Anthropic(api_key=clave, timeout=300.0, max_retries=2)


def _traducir_error(e: Exception) -> ErrorIA:
    import anthropic
    if isinstance(e, anthropic.AuthenticationError):
        return ErrorIA("La clave de Claude no es válida o se ha revocado. Revísala en Ajustes.")
    if isinstance(e, anthropic.PermissionDeniedError):
        return ErrorIA("La clave no tiene permiso para usar este modelo. Revisa tu cuenta en platform.claude.com.")
    if isinstance(e, anthropic.RateLimitError):
        return ErrorIA("Claude está recibiendo demasiadas peticiones o se ha agotado el saldo. Espera un minuto y vuelve a probar, "
                       "o revisa el saldo en platform.claude.com.")
    if isinstance(e, anthropic.APIConnectionError):  # incluye los tiempos de espera
        return ErrorIA("No hay conexión con Claude. Comprueba Internet; mientras tanto puedes usar las plantillas.")
    if isinstance(e, anthropic.APIStatusError):
        if e.status_code == 400 and "credit" in str(e).lower():
            return ErrorIA("No queda saldo en la cuenta de Claude. Añade saldo en platform.claude.com › Billing.")
        if e.status_code >= 500:
            return ErrorIA("Claude no está disponible ahora mismo. Vuelve a probar en unos minutos.")
        return ErrorIA(f"Claude ha devuelto un error ({e.status_code}). Vuelve a probar o usa las plantillas.")
    return ErrorIA(f"No se ha podido crear el material: {e}")


def probar_clave(clave: str | None = None) -> str:
    """Comprueba la clave consultando el modelo (no gasta tokens)."""
    try:
        m = _cliente(clave).models.retrieve(MODELO)
        return m.display_name or MODELO
    except ErrorIA:
        raise
    except Exception as e:  # noqa: BLE001 - se traduce a un mensaje claro
        raise _traducir_error(e) from None


# ------------------------------------------------------------------ privacidad
def anonimizar(texto: str, nombres: list[str]) -> tuple[str, list[str]]:
    """Sustituye en el texto los nombres (y apellidos) de los alumnos por «el alumno».
    Devuelve el texto y la lista de nombres que se han quitado."""
    piezas = set()
    for n in nombres:
        for p in re.split(r"\s+", (n or "").strip()):
            if len(p) >= 3:
                piezas.add(p)
    quitados = []
    resultado = texto or ""
    # De más larga a más corta para no dejar trozos («Martín Castro» antes que «Martín»)
    for completo in sorted({(n or "").strip() for n in nombres if n and n.strip()} | piezas, key=len, reverse=True):
        patron = re.compile(r"(?<![\wáéíóúüñ])" + _patron_sin_tildes(completo) + r"(?![\wáéíóúüñ])", re.I)
        if patron.search(resultado):
            quitados.append(completo)
            resultado = patron.sub("el alumno", resultado)
    resultado = re.sub(r"\b(el alumno)(\s+el alumno)+\b", r"\1", resultado)
    return resultado, quitados


def _patron_sin_tildes(palabra: str) -> str:
    equivalentes = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]", "n": "[nñ]"}
    return "".join(equivalentes.get(c, re.escape(c)) for c in sin_tildes(palabra.lower()))


# ------------------------------------------------------------------ petición a Claude
def peticion_usuario(peticion: str, nivel: str, formato: str, num: int, objetivos: list[str]) -> str:
    partes = [f"Petición de la maestra: {peticion.strip()}",
              f"Nivel: alumnos de {nivel} años (Educación Infantil), con necesidades educativas especiales.",
              f"Formato: {'fichas para imprimir (Word)' if formato == 'docx' else 'diapositivas para proyectar (PowerPoint)'}.",
              f"Número de páginas: exactamente {num}."]
    if objetivos:
        partes.append("Objetivos de su adaptación curricular que todavía está trabajando (úsalos para orientar el material):\n"
                       + "\n".join(f"- {o}" for o in objetivos[:25]))
    return "\n".join(partes)


def generar(peticion: str, nivel: str = "4", formato: str = "docx", num: int = 6, objetivos: list[str] | None = None,
            nombres_alumnos: list[str] | None = None, cliente=None) -> dict:
    """Pide el material a Claude. Devuelve {"spec": MaterialSpec, "anonimizados": [...]}.
    `cliente` permite usar un cliente falso en las pruebas (nunca se llama a la API en los tests)."""
    if not (peticion or "").strip():
        raise ErrorIA("Escribe qué material quieres crear.")
    num = max(1, min(int(num or 6), MAX_PAGINAS))
    nombres = nombres_alumnos or []
    texto, quitados = anonimizar(peticion, nombres)
    objetivos_limpios = [anonimizar(o, nombres)[0] for o in (objetivos or [])]
    cliente = cliente or _cliente()
    for intento in range(2):
        mensaje = peticion_usuario(texto, str(nivel), formato, num, objetivos_limpios)
        try:
            r = cliente.beta.messages.parse(
                model=MODELO,
                max_tokens=16000,
                system=SISTEMA,
                messages=[{"role": "user", "content": mensaje}],
                output_format=MaterialSpec,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except ErrorIA:
            raise
        except Exception as e:  # noqa: BLE001
            raise _traducir_error(e) from None
        if r.stop_reason == "refusal":
            raise ErrorIA("Claude no ha podido crear este material. Prueba a describirlo de otra forma.")
        if r.stop_reason == "max_tokens" and intento == 0 and num > 2:
            num = max(2, num // 2)  # reintento con menos páginas
            continue
        spec = r.parsed_output
        if spec is None or not spec.paginas:
            raise ErrorIA("Claude no ha devuelto un material válido. Vuelve a probar.")
        return {"spec": spec, "anonimizados": quitados}
    raise ErrorIA("El material era demasiado largo. Pide menos páginas.")
