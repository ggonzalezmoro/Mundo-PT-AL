# Arquitectura

Objetivo: una aplicación **100 % local**, sencilla de instalar (copiar una carpeta)
y que no dependa de nada instalado en el equipo salvo Windows 10/11.

```
┌──────────────────────── MundoPTAL.exe (un único proceso) ────────────────────────┐
│                                                                                  │
│  Ventana nativa (pywebview + Edge WebView2, ya incluido en Windows 10/11)        │
│      │  HTML + CSS + JavaScript sin dependencias (mundoptal/static)              │
│      ▼                                                                           │
│  API local Flask en 127.0.0.1:<puerto libre>  (no accesible desde la red)        │
│      │                                                                           │
│      ├── store.py         Alumnos, ACIs, Área › Subárea › Competencia › Ítem     │
│      ├── dictado.py       Texto dictado → jerarquía de la ACI                    │
│      ├── voz.py           Micrófono → texto, sin conexión (Vosk, modelo español) │
│      ├── planificador.py  Horario del maestro y reparto de ítems pendientes      │
│      └── word.py          Exportar / importar ACIs en .docx (python-docx)        │
│      ▼                                                                           │
│  SQLite  %APPDATA%\MundoPTAL\mundo_ptal.db  (copias en …\copias)                 │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Decisiones

| Decisión | Motivo |
|---|---|
| **Python + PyInstaller** | Un solo `.exe` con todo dentro (Python, librerías, modelo de voz). El maestro no instala nada. |
| **SQLite** | Base de datos en un archivo, incluida en Python; sin servidor, rápida y fácil de copiar. |
| **Interfaz web en ventana nativa** | Interfaz moderna y fácil de evolucionar; si WebView2 faltara, se abre el navegador. |
| **Vosk (modelo `vosk-model-small-es-0.42`, ~40 MB)** | Reconocimiento de voz sin Internet: el audio no sale del ordenador (datos de menores). |
| **Analizador de dictado por palabras clave** | Determinista, explicable y sin conexión. El maestro ve una vista previa antes de guardar. |
| **Sin nube** | Requisito del proyecto y protección de datos de alumnos. |
| **Actualizaciones con GitHub Releases** | Sin servidores propios: la app consulta `api.github.com/repos/…/releases/latest`, descarga el `.zip`, y un `.bat` espera a que se cierre, copia los archivos (`robocopy /E`) y la vuelve a abrir. Solo se envía la petición de la versión, nunca datos. |
| **Exportar / importar datos** | Copia completa de la base SQLite (API `backup`). Al importar se valida, se migra al esquema actual y se guarda antes una copia del estado anterior. |

## Modelo de datos

- `usuarios` (perfil: nombre, especialidad PT/AL/PT-AL) 1─N `alumnos` y 1─N `franjas`. La interfaz envía la cabecera `X-Usuario`; con un único perfil se usa ese. Al crear el primer perfil hereda los alumnos y franjas anteriores (migración desde la v0.1, `schema_version` 2).
- `alumnos` 1─N `acis` (la más reciente es la **vigente**, la que usa la agenda).
- `acis` 1─N `adaptaciones` (tabla de tipos de adaptaciones).
- `acis` 1─N `areas` 1─N `subareas` 1─N `competencias` 1─N `items`.
  Una subárea con nombre vacío representa «competencias sin subárea» (p. ej. *El camino de las letras*).
  Cada área puede marcarse como AL, PT o ambas, para planificar solo en las sesiones de esa especialidad.
- `items` guarda `eval_1t`, `eval_2t`, `eval_3t` ∈ {NI, I, ED, ED+, C}. La evaluación vigente es la del trimestre de la ACI o, si está vacía, la del trimestre anterior.
- `informes` (alumno + trimestre + curso escolar, único) 1─N `informe_areas`: informe descriptivo para la familia (`mundoptal/informes.py`). Al crearlo se hace un borrador por área con la ACI del trimestre (C/ED+ conseguido, ED/I en proceso, NI a seguir trabajando). `schema_version` 3.
- `franjas` (horario semanal) N─N `alumnos`; `sesiones` (franja + alumno + fecha) N─N `items` (`sesion_items`).

## Planificación automática

Para cada día del rango, franja de tipo *sesión* y alumno de la franja:

1. Se toman los ítems de su ACI vigente cuya evaluación no es **C** (y del área adecuada a la especialidad de la franja).
2. Se ordenan por: veces ya programados → fecha de la última vez → nivel de logro (NI primero) → orden en la ACI.
3. Se eligen `items_por_sesion`, primero uno por competencia para variar la sesión.

Las sesiones realizadas o canceladas nunca se modifican; «Replanificar» solo rehace las pendientes.

## Próximos pasos posibles

- Instalador con acceso directo en el escritorio.
- Bancos de ítems por edad (AL, lectoescritura, funciones ejecutivas, ToM) para añadir con un clic.
- Informes de progreso por alumno y trimestre.
- Dictado de evaluaciones («ítem tal, conseguido»).
