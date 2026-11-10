# Mundo PT-AL

Aplicación de escritorio para Windows que ayuda en el día a día del maestro de
**Pedagogía Terapéutica (PT)** y **Audición y Lenguaje (AL)** del
Colegio San Ignacio de Loyola.

Todo funciona **en el propio ordenador del maestro**: no hay nube, no hace falta
Internet y los datos de los alumnos nunca salen del equipo.

## Qué hace (versión 0.2)

| Módulo | Qué permite |
|---|---|
| **Alumnos y ACIs** | Crear alumnos y sus Adaptaciones Curriculares Individuales con el formato estándar del colegio: tabla de *tipos de adaptaciones* (significativa / no significativa / sin adaptación + nivel curricular) y la propuesta curricular con la jerarquía **Área › Subárea › Competencia › Ítem**, evaluada por trimestre con **NI · I · ED · ED+ · C**. |
| **Dictado por voz** | El maestro dicta «Área… Subárea… Competencia… Ítem…» y la aplicación lo convierte en la estructura de la ACI. El reconocimiento de voz es **sin conexión** (Vosk, modelo en español). También funciona con el dictado de Windows (**Windows + H**) o escribiendo. |
| **Word** | Exportar la ACI a `.docx` con el logo y los colores del colegio, e **importar** ACIs ya hechas en Word con ese formato. |
| **Revisión trimestral** | Duplicar la ACI para el trimestre siguiente conservando las evaluaciones; los ítems nuevos se pueden sombrear en amarillo (⭐). |
| **Perfiles** | Cada maestro tiene su perfil (PT, AL o PT y AL) con sus propios alumnos, ACIs, horario y agenda. Se elige al abrir la aplicación. |
| **Mi horario** | Configurar las franjas semanales del maestro (día, hora, PT/AL, alumnos, ítems por sesión) o **importarlas** desde una hoja de cálculo (`.xlsx` o `.csv`) con los días en columnas y las horas en filas. |
| **Agenda de sesiones** | Planificación automática: los ítems **no conseguidos** de la ACI vigente de cada alumno se reparten en sus sesiones, rotando para que todos se trabajen. Desde la agenda se marca lo trabajado y se evalúa; un ítem que pasa a **C** deja de planificarse. |

## Uso diario

1. Descarga `MundoPTAL-windows.zip` (pestaña *Actions* o *Releases* del repositorio) y descomprímelo.
2. Ejecuta `MundoPTAL\MundoPTAL.exe`.

Los datos se guardan en `%APPDATA%\MundoPTAL\mundo_ptal.db`. Desde **Ajustes** se
pueden hacer copias de seguridad. Las ACIs exportadas a Word se guardan en
`Documentos\Mundo PT-AL`.

### Importar un horario

En **Mi horario › Importar horario** elige una hoja con este formato (una fila de
cabecera con LUNES…VIERNES y una fila por tramo horario):

| | LUNES | MARTES | … |
|---|---|---|---|
| 9:00-10:00 | ANA | LUIS / PEPE | … |
| 11:00-11:30 | PATIO | PATIO | … |

Los nombres separados por «/», «,» o «y» son alumnos de la misma sesión (se crean si
no existen). Patio, comedor, tiempo de trabajo, departamento, reuniones, etc. se
guardan como franjas «otro». Un «?» marca la sesión como *pendiente de confirmar*.

También desde la consola, sin abrir la ventana:

```
MundoPTAL.exe --perfil "Nombre Apellido" --especialidad PT/AL --importar-horario horario.csv [--reemplazar]
```

### Cómo dictar

Di la palabra clave y después el texto. Para separar ítems di «punto» o vuelve a decir «ítem».

> **Área** comunicación y representación de la realidad **punto**
> **Subárea** área preverbal **punto**
> **Competencia** desarrollar la atención **punto**
> **Ítem** mantiene la mirada en el objeto **ítem** señala el objeto que se le pide entre varias alternativas

Antes de añadir nada, la aplicación muestra cómo lo ha entendido. Si un área,
subárea o competencia ya existe con el mismo nombre, lo dictado se añade dentro.

## Para desarrolladores

Requisitos: Windows 10/11 y Python 3.11 o superior.

```bat
build.bat                  :: crea .venv, descarga el modelo de voz, pasa las pruebas y genera dist\MundoPTAL
ejecutar-desarrollo.bat    :: arranca la app desde el código
```

Otras opciones: `python -m mundoptal --navegador` (abre en el navegador) y
`python -m pytest -q tests`.

Cada `push` a `main` construye el ejecutable en GitHub Actions; al crear una
etiqueta `v*` se publica como *Release*.

Arquitectura: ver [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).
