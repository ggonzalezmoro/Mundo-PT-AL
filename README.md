# Mundo PT-AL

Aplicación de escritorio para Windows que ayuda en el día a día del maestro de
**Pedagogía Terapéutica (PT)** y **Audición y Lenguaje (AL)** del
Colegio San Ignacio de Loyola.

Todo funciona **en el propio ordenador del maestro**: no hay nube, no hace falta
Internet y los datos de los alumnos nunca salen del equipo.

## Qué hace (versión 0.4)

| Módulo | Qué permite |
|---|---|
| **Alumnos y ACIs** | Crear alumnos y sus Adaptaciones Curriculares Individuales con el formato estándar del colegio: tabla de *tipos de adaptaciones* (significativa / no significativa / sin adaptación + nivel curricular) y la propuesta curricular con la jerarquía **Área › Subárea › Competencia › Ítem**, evaluada por trimestre con **NI · I · ED · ED+ · C**. |
| **Dictado por voz** | El maestro dicta «Área… Subárea… Competencia… Ítem…» y la aplicación lo convierte en la estructura de la ACI. El reconocimiento de voz es **sin conexión** (Vosk, modelo en español). También funciona con el dictado de Windows (**Windows + H**) o escribiendo. |
| **Word** | Exportar la ACI a `.docx` con el logo y los colores del colegio, e **importar** ACIs ya hechas en Word con ese formato. |
| **Revisión trimestral** | Duplicar la ACI para el trimestre siguiente conservando las evaluaciones; los ítems nuevos se pueden sombrear en amarillo (⭐). |
| **Perfiles** | Cada maestro tiene su perfil (PT, AL o PT y AL) con sus propios alumnos, ACIs, horario y agenda. Se elige al abrir la aplicación. |
| **Mi horario** | Configurar las franjas semanales del maestro (día, hora, PT/AL, alumnos, ítems por sesión) o **importarlas** desde una hoja de cálculo (`.xlsx` o `.csv`) con los días en columnas y las horas en filas. |
| **Agenda de sesiones** | Planificación automática: los ítems **no conseguidos** de la ACI vigente de cada alumno se reparten en sus sesiones, rotando para que todos se trabajen. Desde la agenda se marca lo trabajado y se evalúa; un ítem que pasa a **C** deja de planificarse. |
| **Informes a familias** | Informe descriptivo trimestral por alumno con el formato de «Observaciones y comentarios» de las ACIs: cómo se ha mostrado, actitud en las sesiones de PT y de AL, evolución en cada área (con un borrador hecho a partir de las evaluaciones de la ACI), cierre, despedida y firmas. Se exporta a Word y se incluye también al final de la ACI de ese trimestre. |
| **Alumnos en valoración (sin ACI)** | Para alumnos que vienen a las sesiones mientras Orientación los valora y no tienen ACI. En su ficha, *Seguimiento: En valoración* (o al crearlos o al importar el horario). En la agenda tienen «Frases rápidas» para las notas y desde su tarjeta en **Alumnos y ACIs** se les hace un **informe de observación**: motivo, organización de las sesiones (se rellena con el horario), comportamiento, atención, comprensión, expresión y habla, relación, regulación emocional, qué le ayuda y valoración. Las notas de la agenda del periodo salen redactadas y con el apartado sugerido. Se exporta a Word (los apartados vacíos no salen). Si más adelante tiene ACI, pasa solo a «Con ACI». |
| **Reuniones** | Notas de reuniones con familias, Orientación, profesores o terapeutas (con alumno opcional), con micrófono. Se escribe una idea por línea y cada línea pasa a **tareas pendientes** con el botón «➕ Tarea» o con **Ctrl + Enter**; la tarea hereda el alumno y queda enlazada a su reunión. Las reuniones aparecen también en el calendario de *Mi trabajo* y en la ficha del alumno. |
| **Tarjeta de cada alumno** | En **Alumnos y ACIs** cada alumno tiene accesos directos a su **ACI**, a su **informe final del trimestre** y a sus **notas de la junta de evaluación** (con su estado: sin empezar, empezado, con notas, pasada al informe). Arriba se elige el trimestre y hay accesos a la junta y a los informes de todos los alumnos a la vez. Por eso «Informes» y «Juntas de evaluación» ya no están en el panel de la izquierda. |
| **Juntas de evaluación** | Una por trimestre (1º, 2º, 3º). Durante la junta se apunta o se dicta 🎤 lo que se dice de cada alumno, una idea por línea, y se guarda solo. El botón **✨ Redactar para el informe** convierte esas notas en un borrador más profesional (reglas locales, sin internet: quita «la tutora dice que…», corrige abreviaturas y expresiones coloquiales y nunca da nada por *conseguido*, porque eso solo sale de los ítems con **C**) repartido por los apartados del informe: cómo se ha mostrado, actitud en PT/AL, cada área de la ACI, estrategias y orientaciones para casa. Se revisa y se pasa al informe a familias del trimestre (o al informe de observación si el alumno está en valoración): se añade al final de cada apartado sin borrar nada. |
| **Actualizaciones** | En *Ajustes › Actualizaciones* se comprueba si hay una versión nueva publicada en GitHub y se instala con un botón: el programa se cierra, se sustituye y se vuelve a abrir. Si otra copia tiene archivos en uso (p. ej. el servidor de material que abre Claude Desktop, «MundoPTAL.exe --mcp»), no se cierra: sus archivos se apartan con otro nombre, la copia sigue funcionando y pasa a la versión nueva cuando se reinicia; los restos se borran solos al abrir la app. Los datos no se tocan (antes se hace una copia de seguridad). Al abrir, avisa si hay versión nueva. |
| **Google Calendar (solo lectura)** | *Ajustes › Google Calendar*: se pega el enlace «Insertar», el ID del calendario o la dirección iCal (pública o secreta) y sus eventos aparecen en *Mi trabajo* y en la agenda del día, con una leyenda para mostrar u ocultar cada calendario. Nada de lo que se crea en la aplicación va a Google. Las direcciones públicas viajan al exportar los datos; las secretas se guardan en el Administrador de credenciales de Windows y hay que pegarlas de nuevo en otro ordenador. |
| **Material en Google Drive** | Para ordenadores sin Word ni PowerPoint (sin cuentas ni claves). «Abrir en Google» copia el archivo a «material mundo pt al» de Mi unidad si está instalado Google Drive para ordenadores (se sube solo) y abre la carpeta en Chrome; si no, abre Drive en Chrome y el Explorador con el archivo seleccionado para arrastrarlo. En *Ajustes › Google Drive* se puede pegar el enlace de la carpeta y volver a Word/PowerPoint. |
| **Usar con Claude Desktop** | Con Claude Desktop y una suscripción Pro (sin clave de la API), se le pide el material a Claude en lenguaje natural y Mundo PT-AL lo maqueta y lo guarda en la carpeta de material. Ver más abajo. |
| **Pasar datos a otro ordenador** | *Ajustes › Exportar mis datos* guarda un archivo `.db` en Documentos › Mundo PT-AL; en el otro ordenador, *Importar datos* lo carga (sustituye los datos de ese ordenador). No hay sincronización. |

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

Los nombres separados por «/», «,», «y» o «e» son alumnos de la misma sesión. Patio,
comedor, tiempo de trabajo, departamento, pruebas de lenguaje, reuniones, etc. se
guardan como franjas «otro». Un «?» marca la sesión como *pendiente de confirmar*.

Antes de guardar se ve una **vista previa**: qué alumno de la aplicación es cada nombre
de la hoja («MARIO» puede ser Mario P. o Mario L.; «MARIO.L» busca un Mario cuyo
apellido empieza por L), cuáles son nuevos y si entran *en valoración, sin ACI*.
**Actualizar mi horario** cambia solo lo que es distinto y **conserva** las notas, la
asistencia y las observaciones de las sesiones ya hechas (las franjas que desaparecen
se archivan); se borran solo las sesiones futuras vacías. Después se planifica lo que
queda de semana.

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

## Crear material con Claude Desktop (sin clave de la API)

Mundo PT-AL incluye un pequeño servidor MCP local: Claude Desktop lo arranca y le pide
que maquete el material que diseña. Funciona con la suscripción Pro de Claude; no hace
falta ninguna clave de la API ni saldo.

1. Instala **Claude Desktop** (claude.ai/download) e inicia sesión con la cuenta Pro.
2. En Mundo PT-AL, *Ajustes › Usar con Claude Desktop* › **Configurar Claude Desktop**.
   Añade la entrada `mundo-ptal` a `%APPDATA%\Claude\claude_desktop_config.json`
   (antes guarda una copia del archivo y no borra las demás entradas). También está
   «Copiar configuración» para hacerlo a mano.
3. **Cierra Claude Desktop del todo** (también desde el icono junto al reloj) y ábrelo.
4. Pídele, por ejemplo: *«Hazme 6 fichas de vocales con animales para 4 años en Word»*.
   La primera vez pregunta si permites usar las herramientas de «mundo-ptal».
   El archivo aparece en Documentos › Mundo PT-AL › Material y en *Crear material*.

Herramientas: `listar_plantillas`, `esquema_material`, `crear_material`,
`crear_desde_plantilla`, `listar_materiales` y, solo si se activa en Ajustes (viene
desactivado), `listar_alumnos` y `objetivos_alumno`, que dan un alias («Alumno 1»…) y
los objetivos pendientes de la ACI, nunca nombres. Se usa el perfil con el que se
trabajó por última vez en la aplicación (o `--perfil <id o nombre>`). La base de datos
se abre en solo lectura; solo se registra el material creado.

Arranque a mano: `MundoPTAL.exe --mcp` o, desde el código, `python -m mundoptal.mcp_server`.
Si se cambia la aplicación de carpeta, hay que volver a pulsar «Configurar Claude Desktop».

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

### Crear material desde la línea de comandos

El apartado «Crear material» describe cada material con un **MaterialSpec** en JSON
(`mundoptal/material.py`): título, objetivo, instrucciones para la maestra y una lista
de páginas, cada una con una actividad de la lista cerrada (`letra`, `repasar`,
`rodear`, `unir`, `completar`, `contar`, `clasificar`, `secuencia`, `tarjetas`,
`pregunta`, `cuento`, `frase`), un enunciado, un `destacado` y sus elementos
(`texto`, `pictograma`, `pareja`, `correcto`, `grupo`, `cantidad`). Con ese JSON se
genera el archivo con el mismo estilo que en la aplicación, sin usar ninguna API:

```bat
.venv\Scripts\python.exe -m mundoptal.material --spec material.json --formato docx ^
    --salida "%USERPROFILE%\Documents\Mundo PT-AL\Material\ficha.docx" --cabecera "Nombre de la maestra"
```

Opciones: `--formato docx|pptx`, `--alumno` (nombre en la cabecera de las fichas),
`--logo` (otra imagen), `--sin-pictos` (no descarga pictogramas de ARASAAC; usa emoji
o un hueco). Para ver un ejemplo de JSON:
`python -c "from mundoptal import material; print(material.plantilla('rutinas', 'vestirse').model_dump_json(indent=2))"`.

### Publicar una versión nueva (para el botón «Actualizar»)

1. Sube `APP_VERSION` en `mundoptal/config.py` (por ejemplo `0.4.0` → `0.5.0`).
2. `git commit` y `git push` a `main`.
3. `git tag v0.5.0` y `git push origin v0.5.0`.

GitHub Actions comprueba que la etiqueta coincide con `APP_VERSION`, construye
el `.zip` y lo publica como *Release*. Las aplicaciones instaladas lo detectan
en *Ajustes › Actualizaciones*. El repositorio tiene que ser **público** para
que las aplicaciones puedan descargar la versión sin credenciales (por eso el
repositorio no debe contener nunca datos de alumnos).

Arquitectura: ver [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).
