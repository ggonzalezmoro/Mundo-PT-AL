/* Mundo PT-AL · interfaz (JavaScript sin dependencias externas, funciona sin Internet) */
"use strict";

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];
const vista = $("#vista");
const dialogo = $("#dialogo");
let INFO = { escala: ["NI", "I", "ED", "ED+", "C"], dias: ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"] };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const claseEval = (v) => (v ? "eval-" + v.replace("+", "p") : "");

// Perfil activo (cada maestro ve solo sus alumnos, su horario y su agenda)
let USUARIO = null;
const CLAVE_PERFIL = "mundoptal.usuario";
function leerPerfilGuardado() { try { return localStorage.getItem(CLAVE_PERFIL); } catch (e) { return null; } }
function guardarPerfil(id) { try { localStorage.setItem(CLAVE_PERFIL, String(id)); } catch (e) { /* sin almacenamiento */ } }

async function api(metodo, url, cuerpo) {
  const op = { method: metodo, headers: {} };
  if (USUARIO) op.headers["X-Usuario"] = String(USUARIO.id);
  if (cuerpo instanceof FormData) op.body = cuerpo;
  else if (cuerpo !== undefined) { op.body = JSON.stringify(cuerpo); op.headers["Content-Type"] = "application/json"; }
  const r = await fetch(url, op);
  const tipo = r.headers.get("Content-Type") || "";
  const datos = tipo.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((datos && datos.error) || "Error " + r.status);
  return datos;
}

function aviso(texto, error = false) {
  const t = document.createElement("div");
  t.className = "toast" + (error ? " error" : "");
  t.textContent = texto;
  const cont = $("#avisos");
  cont.appendChild(t);
  while (cont.children.length > 3) cont.firstChild.remove();
  setTimeout(() => t.remove(), error ? 6000 : 3000);
}

async function intentar(fn) {
  try { return await fn(); } catch (e) { aviso(e.message, true); throw e; }
}

function fechaISO(d) { return d.toISOString().slice(0, 10); }
function lunes(d) { const x = new Date(d); x.setHours(12); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; }
function sumarDias(iso, n) { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return fechaISO(d); }
const fechaES = (iso) => (iso ? iso.split("-").reverse().join("/") : "");
function fechaCorta(iso) { const [y, m, d] = iso.split("-"); return `${d}/${m}`; }
// Fecha de hoy en hora local (toISOString usa UTC y de madrugada daría el día anterior)
function hoyISO() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function lunesISO(iso) { return fechaISO(lunes(new Date(iso + "T12:00:00"))); }
function esFinde(iso) { const d = new Date(iso + "T12:00:00").getDay(); return d === 0 || d === 6; }
function diaLaborable(iso, paso) { let f = sumarDias(iso, paso); while (esFinde(f)) f = sumarDias(f, paso > 0 ? 1 : -1); return f; }
// Vista elegida (día/semana/mes) recordada por pantalla
function leerPref(clave, def) { try { return localStorage.getItem("mundoptal.vista." + clave) || def; } catch (e) { return def; } }
function guardarPref(clave, v) { try { localStorage.setItem("mundoptal.vista." + clave, v); } catch (e) { /* sin almacenamiento */ } }
// Selector segmentado «Día · Semana · Mes»: opciones = [[modo, etiqueta, enlace]]
function selectorVista(actual, opciones) {
  return `<div class="segmentado" role="tablist" aria-label="Cambiar vista">${opciones.map(([m, t, h]) =>
    `<a href="${h}" role="tab" aria-selected="${m === actual}" class="${m === actual ? "activo" : ""}">${t}</a>`).join("")}</div>`;
}

// ======================================================================= rutas
const rutas = [
  [/^#\/alumnos$/, vistaAlumnos, "alumnos"],
  [/^#\/alumno\/(\d+)$/, vistaAlumno, "alumnos"],
  [/^#\/aci\/(\d+)$/, vistaACI, "alumnos"],
  [/^#\/horario$/, vistaHorario, "horario"],
  [/^#\/agenda(?:\/(dia|semana))?(?:\/(\d{4}-\d{2}-\d{2}))?$/, vistaAgenda, "agenda"],
  [/^#\/ajustes$/, vistaAjustes, "ajustes"],
  [/^#\/perfiles$/, vistaPerfiles, "perfiles"],
  [/^#\/informes$/, vistaInformes, "alumnos"],
  [/^#\/informe\/(\d+)$/, vistaInforme, "alumnos"],
  [/^#\/observacion\/(\d+)$/, vistaObservacion, "alumnos"],
  [/^#\/trabajo(?:\/(dia|semana|mes))?(?:\/(\d{4}-\d{2}(?:-\d{2})?))?$/, vistaTrabajo, "trabajo"],
  [/^#\/material$/, vistaMaterial, "material"],
  [/^#\/reuniones$/, vistaReuniones, "reuniones"],
  [/^#\/reunion\/(\d+)$/, vistaReunion, "reuniones"],
  [/^#\/juntas(?:\/([123]))?(?:\/(\d+))?$/, vistaJuntas, "alumnos"],
];

async function enrutar() {
  const h = location.hash || "#/alumnos";
  // Sin perfil solo se puede elegir/crear perfil o ir a Ajustes (p. ej. para importar datos)
  if (!USUARIO && h !== "#/perfiles" && h !== "#/ajustes") {
    if (location.hash) aviso("Primero elige o crea tu perfil (o importa tus datos desde Ajustes).");
    location.hash = "#/perfiles";
    return;
  }
  for (const [re, fn, nav] of rutas) {
    const m = h.match(re);
    if (m) {
      $$("nav a").forEach((a) => a.classList.toggle("activo", a.dataset.nav === nav));
      try { await fn(...m.slice(1)); } catch (e) { vista.innerHTML = `<div class="vacio">${esc(e.message)}</div>`; }
      return;
    }
  }
  location.hash = "#/alumnos";
}
window.addEventListener("hashchange", () => { vista.scrollTop = 0; enrutar(); });

// ======================================================================= alumnos
// Igual que informes.trimestre_actual(): sep-dic 1º, ene-mar 2º, abr-ago 3º
function trimestreActual() { const m = new Date().getMonth() + 1; return m >= 9 ? 1 : m <= 3 ? 2 : 3; }

// Trimestre elegido en «Alumnos y ACIs» (null = el trimestre actual)
let TRIMESTRE_ALUMNOS = null;

async function vistaAlumnos() {
  const [alumnos, inf] = await Promise.all([api("GET", "/api/alumnos"), api("GET", "/api/informes")]);
  const trimestre = TRIMESTRE_ALUMNOS || inf.trimestre;
  const J = await api("GET", `/api/juntas?trimestre=${trimestre}`).catch(() => ({ alumnos: [] }));
  const extra = {
    trimestre, curso_escolar: inf.curso_escolar,
    informes: Object.fromEntries(inf.alumnos.map((a) => [a.id, a])),
    junta: Object.fromEntries((J.alumnos || []).map((a) => [a.alumno_id, a])),
  };
  const enValoracion = alumnos.filter((a) => a.seguimiento === "observacion");
  const conACI = alumnos.filter((a) => a.seguimiento !== "observacion");
  const tarjeta = (a) => tarjetaAlumno(a, extra);
  vista.innerHTML = `
    <div class="cabecera">
      <div><h1>Alumnos y ACIs</h1><p class="sub">Desde la tarjeta de cada alumno abres su ACI, su informe final del trimestre y sus notas de la junta de evaluación.</p></div>
      <div class="acciones">
        <label class="boton" for="importar">📄 Importar ACI desde Word</label>
        <input type="file" id="importar" accept=".docx" hidden>
        <button class="primario" id="nuevo">＋ Nuevo alumno</button>
      </div>
    </div>
    <form class="tarjeta" id="form-alumno" hidden>
      <h2>Nuevo alumno</h2>
      <div class="campos">
        <div><label>Nombre</label><input name="nombre" required placeholder="Nombre del alumno"></div>
        <div><label>Curso</label><input name="curso" placeholder="p. ej. 2º Curso del 2º Ciclo de Educación Infantil"></div>
        <div class="campo-ancho"><label>Observaciones</label><input name="observaciones" placeholder="Diagnóstico, apoyos, etc. (opcional)"></div>
        <div class="campo-ancho"><label class="check"><input type="checkbox" name="valoracion" id="nuevo-valoracion">
          En valoración, <strong>sin ACI</strong>: solo se hará un informe de observación de cómo se muestra en las sesiones</label></div>
      </div>
      <p class="acciones" style="margin:12px 0 0"><button class="primario" id="guardar-alumno">Guardar y crear ACI</button><button type="button" id="cancelar">Cancelar</button></p>
    </form>
    ${!alumnos.length ? `<div class="vacio">Todavía no hay alumnos. Pulsa «Nuevo alumno» o importa una ACI desde Word.</div>`
      : `<div class="todos-alumnos"><label for="tri-alumnos">Trimestre</label>
          <select id="tri-alumnos">${[1, 2, 3].map((t) => `<option value="${t}" ${t === trimestre ? "selected" : ""}>${t}º · ${esc(inf.curso_escolar)}</option>`).join("")}</select>
          <span class="muted" style="margin-left:12px">Todos los alumnos a la vez:</span>
          <a class="boton mini" href="#/juntas/${trimestre}">🧑‍🏫 Junta de evaluación del ${trimestre}º trimestre</a>
          <a class="boton mini" href="#/informes">📝 Informes de todos</a></div>
        <div class="rejilla">${conACI.map(tarjeta).join("")}</div>
        ${enValoracion.length ? `<h2 class="seccion-alumnos">En valoración, sin ACI (${enValoracion.length})</h2>
          <p class="muted">Alumnos que vienen a las sesiones mientras se les valora. No tienen ACI: de ellos se hace un <strong>informe de observación</strong>.</p>
          <div class="rejilla">${enValoracion.map(tarjeta).join("")}</div>` : ""}`}`;
  if ($("#tri-alumnos")) $("#tri-alumnos").onchange = (e) => { TRIMESTRE_ALUMNOS = +e.target.value; vistaAlumnos(); };
  $$("[data-crear-informe]").forEach((b) => b.onclick = () => crearInforme(b.dataset.crearInforme, trimestre, inf.curso_escolar));
  $$("[data-crear-obs]").forEach((b) => b.onclick = () => intentar(async () => {
    const r = await api("POST", `/api/alumnos/${b.dataset.crearObs}/observaciones`, {});
    location.hash = `#/observacion/${r.id}`;
  }));
  $$("[data-crear-aci]").forEach((b) => b.onclick = () => intentar(async () => {
    const r = await api("POST", `/api/alumnos/${b.dataset.crearAci}/acis`, {});
    location.hash = `#/aci/${r.id}`;
  }));
  $("#nuevo-valoracion").onchange = (e) => { $("#guardar-alumno").textContent = e.target.checked ? "Guardar alumno" : "Guardar y crear ACI"; };

  const form = $("#form-alumno");
  $("#nuevo").onclick = () => { form.hidden = false; form.nombre.focus(); };
  $("#cancelar").onclick = () => { form.hidden = true; };
  form.onsubmit = (e) => intentar(async () => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(form));
    const valoracion = !!datos.valoracion;
    delete datos.valoracion;
    datos.seguimiento = valoracion ? "observacion" : "aci";
    const { id } = await api("POST", "/api/alumnos", datos);
    if (valoracion) { location.hash = `#/alumno/${id}`; return; }
    const aci = await api("POST", `/api/alumnos/${id}/acis`, {});
    location.hash = `#/aci/${aci.id}`;
  });
  $("#importar").onchange = (e) => importarWord(e.target.files[0]);
}

function tarjetaAlumno(a, extra) {
  const obs = a.seguimiento === "observacion";
  const t = extra.trimestre;
  const inf = ((extra.informes[a.id] || {}).informes || []).find((x) => x.trimestre === t && x.curso_escolar === extra.curso_escolar);
  const ultObs = ((extra.informes[a.id] || {}).observaciones || [])[0];
  const ja = extra.junta[a.id] || {};
  const notasJunta = (ja.notas || "").trim();
  const acceso = (ico, titulo, estado, boton) => `<div class="acceso"><span class="ico">${ico}</span>
      <div class="acceso-texto"><strong>${titulo}</strong><span class="muted">${estado}</span></div>${boton}</div>`;
  const filaACI = obs
    ? acceso("🔍", "Informe de observación", ultObs ? `Del ${esc(fechaES(ultObs.fecha))}` : "Sin empezar",
        ultObs ? `<a class="boton mini primario" href="#/observacion/${ultObs.id}">Abrir</a>` : `<button class="mini" data-crear-obs="${a.id}">Crear</button>`)
    : acceso("📋", "ACI", a.aci_vigente_id ? `${a.num_acis} ACI${a.num_acis === 1 ? "" : "s"} · abre la vigente` : "Sin ACI todavía",
        a.aci_vigente_id ? `<a class="boton mini primario" href="#/aci/${a.aci_vigente_id}">Abrir</a>` : `<button class="mini" data-crear-aci="${a.id}">Crear</button>`);
  const filaInforme = obs ? "" : acceso("📝", `Informe final ${t}º trimestre`, inf ? `Empezado · ${esc(fechaES(inf.actualizado.slice(0, 10)))}` : "Sin empezar",
    inf ? `<a class="boton mini primario" href="#/informe/${inf.id}">Abrir</a>` : `<button class="mini" data-crear-informe="${a.id}">Crear</button>`);
  const filaJunta = acceso("🧑‍🏫", `Junta de evaluación ${t}º`,
    ja.pasado ? `Pasada al informe · ${esc(fechaES(ja.pasado.slice(0, 10)))}` : notasJunta ? "Con notas ✔" : "Sin notas",
    `<a class="boton mini ${notasJunta ? "primario" : ""}" href="#/juntas/${t}/${a.id}">${notasJunta ? "Abrir" : "Apuntar"}</a>`);
  return `<div class="tarjeta alumno ${obs ? "en-valoracion" : ""}">
    <div class="fila"><div class="avatar">${esc(a.nombre[0] || "?").toUpperCase()}</div>
      <div style="flex:1"><div class="nombre">${esc(a.nombre)}</div><div class="muted">${esc(a.curso || "Curso sin indicar")}</div></div>
      <a class="boton mini" href="#/alumno/${a.id}" title="Datos, asistencia, tutorías y todos sus documentos">Ficha</a></div>
    ${obs ? `<div><span class="chip valoracion">En valoración · sin ACI</span></div>` : ""}
    <div class="accesos">${filaACI}${filaInforme}${filaJunta}</div></div>`;
}

async function importarWord(archivo, alumnoId) {
  if (!archivo) return;
  const fd = new FormData();
  fd.append("archivo", archivo);
  if (alumnoId) fd.append("alumno_id", alumnoId);
  await intentar(async () => {
    const r = await api("POST", "/api/importar-word", fd);
    aviso("ACI importada correctamente");
    location.hash = `#/aci/${r.id}`;
  });
}

async function vistaAlumno(id) {
  const [a] = await Promise.all([api("GET", `/api/alumnos/${id}`), infoTrabajo()]);
  const obs = a.seguimiento === "observacion";
  const listaObs = a.observaciones_informes || [];
  const tarjetaObservaciones = `<div class="tarjeta"><h2>🔍 Informes de observación</h2>
      <p class="muted">Cómo se muestra en las sesiones (conducta, atención, comunicación, relación…). Usa tus notas de la agenda y se exporta a Word.</p>
      ${listaObs.length ? `<table class="tabla-adapt"><tr><th>Fecha</th><th>Periodo observado</th><th>Última modificación</th><th></th></tr>
        ${listaObs.map((x) => `<tr><td>${esc(fechaES(x.fecha))}</td><td>${esc(fechaES(x.desde))} – ${esc(fechaES(x.hasta))}</td><td>${esc(x.actualizado)}</td>
          <td><a class="boton mini" href="#/observacion/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">Sin informes de observación todavía.</div>`}
      <p style="margin:12px 0 0"><button class="${obs ? "primario" : ""}" id="nueva-observacion">🔍 Nuevo informe de observación</button></p></div>`;
  vista.innerHTML = `
    <div class="migas"><a href="#/alumnos">Alumnos</a> › ${esc(a.nombre)}</div>
    <div class="cabecera"><div><h1>${esc(a.nombre)}</h1><p class="sub">${esc(a.curso)}</p></div>
      <div class="acciones">
        <label class="boton" for="importar">📄 Importar ACI desde Word</label><input type="file" id="importar" accept=".docx" hidden>
        <button class="primario" id="nueva-aci">＋ Nueva ACI vacía</button></div></div>
    <div class="tarjeta"><h2>Datos del alumno</h2>
      <div class="campos">
        <div><label>Nombre</label><input data-tabla="alumnos" data-id="${a.id}" data-campo="nombre" value="${esc(a.nombre)}"></div>
        <div><label>Curso</label><input data-tabla="alumnos" data-id="${a.id}" data-campo="curso" value="${esc(a.curso)}"></div>
        <div><label>Seguimiento</label><select data-tabla="alumnos" data-id="${a.id}" data-campo="seguimiento" id="seguimiento">
          <option value="aci" ${obs ? "" : "selected"}>Con ACI</option>
          <option value="observacion" ${obs ? "selected" : ""}>En valoración, sin ACI (informe de observación)</option></select></div>
        <div class="campo-ancho"><label>Observaciones</label><textarea data-tabla="alumnos" data-id="${a.id}" data-campo="observaciones" rows="2">${esc(a.observaciones)}</textarea></div>
      </div>
      <p style="margin:12px 0 0"><button class="peligro" id="borrar-alumno">Borrar alumno y todas sus ACIs</button></p></div>
    ${obs ? tarjetaObservaciones : ""}
    <div class="tarjeta" id="asistencia"><h2>Asistencia a las sesiones</h2><p class="muted">Cargando…</p></div>
    <div class="tarjeta"><h2>Informes para la familia</h2>
      ${a.informes.length ? `<table class="tabla-adapt"><tr><th>Trimestre</th><th>Curso escolar</th><th>Última modificación</th><th></th></tr>
        ${a.informes.map((x) => `<tr><td>${x.trimestre}º trimestre</td><td>${esc(x.curso_escolar)}</td><td>${esc(x.actualizado)}</td>
          <td><a class="boton mini" href="#/informe/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">Sin informes todavía.</div>`}
      <p style="margin:12px 0 0"><button id="nuevo-informe">📝 Informe del trimestre actual</button>
        <a class="boton" href="#/juntas/${TRIMESTRE_ALUMNOS || trimestreActual()}/${a.id}" id="ir-junta">🧑‍🏫 Notas de la junta de evaluación</a></p></div>
    <div class="tarjeta"><h2>Tutorías y reuniones</h2>
      ${(a.citas || []).length ? `<ul class="lista-citas">${a.citas.map((c) => `<li>
          <button type="button" class="cita ${c.tipo} ${c.hecha ? "hecha" : ""}" data-cita-alumno="${c.id}">${esc(TRABAJO.tipos_cita[c.tipo] || "Cita")}</button>
          <strong>${fechaCorta(c.fecha)}/${c.fecha.slice(0, 4)}</strong>${c.hora_inicio ? " · " + c.hora_inicio : ""}${c.con_quien ? " · " + esc(c.con_quien) : ""}
          <a class="boton mini" href="#/reunion/${c.id}">📝 Notas y tareas</a>
          ${c.notas ? `<div class="muted notas-cita">${esc(c.notas)}</div>` : ""}</li>`).join("")}</ul>`
        : `<div class="vacio" style="padding:16px">Sin tutorías ni reuniones todavía.</div>`}
      <p style="margin:12px 0 0"><button id="nueva-tutoria">＋ Nueva tutoría o reunión</button></p></div>
    <div class="tarjeta"><h2>ACIs</h2>
      ${a.acis.length ? `<table class="tabla-adapt"><tr><th>Trimestre</th><th>Curso escolar</th><th>Curso</th><th>Última modificación</th><th></th></tr>
        ${a.acis.map((x, i) => `<tr><td>${x.trimestre}º trimestre ${i === 0 ? '<span class="chip">vigente</span>' : ""}</td><td>${esc(x.curso_escolar)}</td>
          <td>${esc(x.curso)}</td><td>${esc(x.actualizado)}</td><td><a class="boton mini" href="#/aci/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">${obs ? "Está en valoración y no tiene ACI. Si más adelante la necesita, créala aquí y pasará a «Con ACI»." : "Sin ACIs todavía."}</div>`}
      <p class="muted" style="margin-top:10px">La ACI más reciente es la vigente: es la que se usa para planificar las sesiones.</p></div>
    ${!obs && listaObs.length ? tarjetaObservaciones : ""}`;
  enlazarCampos(vista);
  pintarAsistencia(id);
  $("#seguimiento").addEventListener("change", () => setTimeout(() => vistaAlumno(id), 300));
  const nuevaObs = $("#nueva-observacion");
  if (nuevaObs) nuevaObs.onclick = () => intentar(async () => {
    const r = await api("POST", `/api/alumnos/${id}/observaciones`, {});
    location.hash = `#/observacion/${r.id}`;
  });
  $("#nueva-aci").onclick = () => intentar(async () => {
    const r = await api("POST", `/api/alumnos/${id}/acis`, {});
    location.hash = `#/aci/${r.id}`;
  });
  $("#importar").onchange = (e) => importarWord(e.target.files[0], id);
  $("#nuevo-informe").onclick = () => crearInforme(id);
  const alumnosCita = [{ id: a.id, nombre: a.nombre }];
  $("#nueva-tutoria").onclick = () => dialogoCita({ fecha: hoyISO(), alumno_id: a.id, tipo: "tutoria_familia" }, alumnosCita, () => vistaAlumno(id));
  $$("[data-cita-alumno]").forEach((b) => b.onclick = () =>
    dialogoCita(a.citas.find((c) => String(c.id) === b.dataset.citaAlumno), alumnosCita, () => vistaAlumno(id)));
  $("#borrar-alumno").onclick = () => intentar(async () => {
    if (!confirm(`¿Seguro que quieres borrar a ${a.nombre} y todas sus ACIs y sesiones? No se puede deshacer.`)) return;
    await api("DELETE", `/api/alumnos/${id}`);
    location.hash = "#/alumnos";
  });
}

// Guardado automático de cualquier campo con data-tabla/data-id/data-campo
function enlazarCampos(raiz) {
  $$("[data-campo]", raiz).forEach((el) => {
    el.addEventListener("change", () => intentar(async () => {
      let valor = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value;
      await api("PATCH", `/api/${el.dataset.tabla}/${el.dataset.id}`, { [el.dataset.campo]: valor });
      if (el.classList.contains("eval")) {
        el.className = "eval " + claseEval(valor);
        refrescarResumen();
      }
      if (el.dataset.recargar) recargarACI();
    }));
  });
}

// ======================================================================= ACI
let ACI = null;

async function vistaACI(id) {
  ACI = await api("GET", `/api/acis/${id}`);
  pintarACI();
}

async function recargarACI() {
  const y = vista.scrollTop;
  ACI = await api("GET", `/api/acis/${ACI.id}`);
  pintarACI();
  vista.scrollTop = y;
}

async function refrescarResumen() {
  const a = await api("GET", `/api/acis/${ACI.id}`);
  ACI.resumen = a.resumen;
  const r = $("#resumen");
  if (r) r.innerHTML = htmlResumen();
}

function htmlResumen() {
  const r = ACI.resumen;
  const colores = { "sin evaluar": "#e6e6e6", NI: "var(--ni-t)", I: "#e08a1e", ED: "#d6b500", "ED+": "#8cc63f", C: "var(--verde)" };
  const tramos = Object.entries(r.por_valor).filter(([, n]) => n)
    .map(([k, n]) => `<span title="${k}: ${n}" style="width:${(100 * n) / Math.max(1, r.total)}%;background:${colores[k]}"></span>`).join("");
  return `<div><strong style="font-size:20px;color:var(--verde)">${r.conseguidos}</strong> / ${r.total} ítems conseguidos
      · <strong>${r.pendientes}</strong> pendientes</div>
    <div class="barra">${tramos}</div>
    <div class="leyenda">${Object.entries(r.por_valor).map(([k, n]) => `<span><b style="background:${colores[k]};color:#fff">${k}</b> ${n}</span>`).join("")}</div>`;
}

function pintarACI() {
  const a = ACI;
  const tri = a.trimestre;
  vista.innerHTML = `
    <div class="migas"><a href="#/alumnos">Alumnos</a> › <a href="#/alumno/${a.alumno_id}">${esc(a.alumno_nombre)}</a> › ACI</div>
    <div class="cabecera">
      <div><h1>ACI de ${esc(a.alumno_nombre)}</h1><p class="sub">${tri}º trimestre ${a.curso_escolar ? "· Curso " + esc(a.curso_escolar) : ""}</p></div>
      <div class="acciones">
        <button class="lima" id="dictar">🎤 Dictar</button>
        <button id="word">📄 Exportar a Word</button>
        <button id="duplicar" title="Crea una copia para la revisión del siguiente trimestre">⧉ Revisión siguiente trimestre</button>
        <button class="peligro" id="borrar-aci">Borrar</button>
      </div>
    </div>

    <div class="tarjeta"><div class="resumen" id="resumen">${htmlResumen()}</div></div>

    <details class="tarjeta" ${a.areas.length ? "" : "open"}>
      <summary><h2 style="display:inline">Datos generales</h2></summary>
      <div class="campos" style="margin-top:12px">
        <div><label>Título del informe</label><input data-tabla="acis" data-id="${a.id}" data-campo="titulo" value="${esc(a.titulo)}"></div>
        <div><label>Curso del alumno</label><input data-tabla="acis" data-id="${a.id}" data-campo="curso" value="${esc(a.curso)}"></div>
        <div><label>Curso escolar</label><input data-tabla="acis" data-id="${a.id}" data-campo="curso_escolar" value="${esc(a.curso_escolar)}" placeholder="2026-2027"></div>
        <div><label>Trimestre actual</label><select data-tabla="acis" data-id="${a.id}" data-campo="trimestre" data-recargar="1">
          ${[1, 2, 3].map((t) => `<option value="${t}" ${t === tri ? "selected" : ""}>${t}º trimestre</option>`).join("")}</select></div>
        <div><label>Área/materia de la adaptación</label><input data-tabla="acis" data-id="${a.id}" data-campo="materia" value="${esc(a.materia)}"></div>
        <div><label>Prof. responsable de área</label><input data-tabla="acis" data-id="${a.id}" data-campo="prof_area" value="${esc(a.prof_area)}"></div>
        <div><label>Prof. AL / PT</label><input data-tabla="acis" data-id="${a.id}" data-campo="prof_ptal" value="${esc(a.prof_ptal)}"></div>
        <div class="campo-ancho"><label>Observaciones y comentarios</label><textarea rows="3" data-tabla="acis" data-id="${a.id}" data-campo="observaciones">${esc(a.observaciones)}</textarea></div>
      </div>
    </details>

    <details class="tarjeta" open>
      <summary><h2 style="display:inline">Tipos de adaptaciones</h2></summary>
      <table class="tabla-adapt" style="margin-top:12px">
        <tr><th>Área</th><th>Adaptación significativa</th><th>Adaptación no significativa</th><th>No tiene adaptación</th><th>Nivel curricular</th><th></th></tr>
        ${a.adaptaciones.map((ad) => `<tr>
          <td style="width:34%"><input data-tabla="adaptaciones" data-id="${ad.id}" data-campo="area" value="${esc(ad.area)}"></td>
          ${["significativa", "no_significativa", "ninguna"].map((t) => `<td class="marca-x ${ad.tipo === t ? "si" : ""}" data-adapt="${ad.id}" data-tipo="${t}">${ad.tipo === t ? "X" : ""}</td>`).join("")}
          <td class="nivel"><input data-tabla="adaptaciones" data-id="${ad.id}" data-campo="nivel_curricular" value="${esc(ad.nivel_curricular)}" placeholder="p. ej. 1º de infantil / 2º ciclo"></td>
          <td><button class="icono" data-borrar="adaptaciones" data-id="${ad.id}" title="Quitar fila">✕</button></td></tr>`).join("")}
      </table>
      <p style="margin:8px 0 0"><button class="mini" id="add-adapt">＋ Añadir área a la tabla</button></p>
      <p class="muted" style="margin:10px 0 0;font-size:12px">Indicadores de evaluación:
        ${INFO.escala.map((k) => `<b>${k}</b>: ${esc((INFO.escala_texto || {})[k] || "")}`).join(" · ")}</p>
    </details>

    <h2 style="margin-top:22px">Propuesta curricular adaptada</h2>
    <div id="areas">${a.areas.map((ar, i) => htmlArea(ar, i, tri)).join("") ||
      `<div class="vacio">Aún no hay áreas. Pulsa «🎤 Dictar» para crearlas con la voz o añade una a mano.</div>`}</div>
    <p><button class="primario" id="add-area">＋ Añadir área</button></p>`;

  enlazarCampos(vista);
  $("#dictar").onclick = () => abrirDictado();
  $("#word").onclick = () => exportarWord();
  $("#duplicar").onclick = () => intentar(async () => {
    if (!confirm("Se creará una copia de esta ACI para el trimestre siguiente (con las evaluaciones actuales). ¿Continuar?")) return;
    const r = await api("POST", `/api/acis/${a.id}/duplicar`, { siguiente_trimestre: true });
    aviso("Nueva revisión creada");
    location.hash = `#/aci/${r.id}`;
  });
  $("#borrar-aci").onclick = () => intentar(async () => {
    if (!confirm("¿Borrar esta ACI completa? No se puede deshacer.")) return;
    await api("DELETE", `/api/acis/${a.id}`);
    location.hash = `#/alumno/${a.alumno_id}`;
  });
  $("#add-adapt").onclick = () => intentar(async () => { await api("POST", `/api/adaptaciones/${a.id}/hijos`, { area: "" }); recargarACI(); });
  $("#add-area").onclick = () => intentar(async () => {
    const r = await api("POST", `/api/areas/${a.id}/hijos`, { nombre: "Nueva área" });
    await api("POST", `/api/subareas/${r.id}/hijos`, { nombre: "" });
    await recargarACI();
    const inp = $(`[data-tabla=areas][data-id="${r.id}"]`); if (inp) { inp.focus(); inp.select(); }
  });
  $$(".marca-x").forEach((td) => td.onclick = () => intentar(async () => {
    const actual = td.classList.contains("si");
    await api("PATCH", `/api/adaptaciones/${td.dataset.adapt}`, { tipo: actual ? "" : td.dataset.tipo });
    recargarACI();
  }));
  $$("[data-borrar]").forEach((b) => b.onclick = () => intentar(async () => {
    const tabla = b.dataset.borrar;
    const nombres = { areas: "el área y todo su contenido", subareas: "la subárea y sus competencias", competencias: "la competencia y sus ítems", items: "el ítem", adaptaciones: "la fila" };
    if (tabla !== "items" && tabla !== "adaptaciones" && !confirm(`¿Borrar ${nombres[tabla]}?`)) return;
    await api("DELETE", `/api/${tabla}/${b.dataset.id}`);
    recargarACI();
  }));
  $$("[data-mover]").forEach((b) => b.onclick = () => intentar(async () => {
    await api("POST", `/api/${b.dataset.mover}/${b.dataset.id}/mover`, { direccion: +b.dataset.dir });
    recargarACI();
  }));
  $$("[data-crear]").forEach((b) => b.onclick = () => intentar(async () => {
    const tabla = b.dataset.crear;
    const datos = tabla === "items" ? { texto: "" } : { nombre: "" };
    const r = await api("POST", `/api/${tabla}/${b.dataset.padre}/hijos`, datos);
    await recargarACI();
    const el = $(`[data-tabla="${tabla}"][data-id="${r.id}"]`); if (el) el.focus();
  }));
  $$(".estrella").forEach((b) => b.onclick = () => intentar(async () => {
    const on = !b.classList.contains("on");
    await api("PATCH", `/api/items/${b.dataset.id}`, { destacado: on ? 1 : 0 });
    b.classList.toggle("on", on);
    b.closest(".item").classList.toggle("destacado", on);
  }));
  // Ajustar altura de los textos de los ítems
  $$(".item textarea").forEach(autoAltura);
}

function autoAltura(t) {
  const f = () => { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; };
  t.addEventListener("input", f); requestAnimationFrame(f);
}

function botonesOrden(tabla, id) {
  return `<button class="icono" data-mover="${tabla}" data-id="${id}" data-dir="-1" title="Subir">▲</button>
          <button class="icono" data-mover="${tabla}" data-id="${id}" data-dir="1" title="Bajar">▼</button>
          <button class="icono" data-borrar="${tabla}" data-id="${id}" title="Borrar">✕</button>`;
}

function htmlArea(area, i, tri) {
  let nSub = 0;
  return `<section class="area">
    <div class="area-cab">
      <input class="nombre-area" data-tabla="areas" data-id="${area.id}" data-campo="nombre" value="${esc(area.nombre)}" placeholder="Nombre del área">
      <select data-tabla="areas" data-id="${area.id}" data-campo="especialidad" title="Especialidad con la que se trabaja (para la agenda)">
        ${[["", "PT y AL"], ["AL", "Solo AL"], ["PT", "Solo PT"]].map(([v, t]) => `<option value="${v}" ${area.especialidad === v ? "selected" : ""}>${t}</option>`).join("")}
      </select>
      ${botonesOrden("areas", area.id)}
    </div>
    <div class="fila-tri cab-tri"><div></div><div>TRIMESTRES</div>${[1, 2, 3].map((t) => `<div class="tri ${t === tri ? "actual" : ""}">${t}T</div>`).join("")}<div></div></div>
    ${area.subareas.map((s) => { if (s.nombre) nSub++; return htmlSub(s, s.nombre ? nSub : null, tri); }).join("")}
    <div class="anadir">
      <button data-crear="subareas" data-padre="${area.id}">＋ Subárea</button>
    </div>
  </section>`;
}

function htmlSub(s, n, tri) {
  return `<div class="sub-cab ${s.nombre ? "" : "sin-nombre"}">
      ${n ? `<strong>${n}.</strong>` : ""}
      <input data-tabla="subareas" data-id="${s.id}" data-campo="nombre" value="${esc(s.nombre)}" placeholder="(competencias sin subárea · escribe aquí para darle nombre)">
      ${botonesOrden("subareas", s.id)}
    </div>
    ${s.competencias.map((c, i) => htmlComp(c, n ? `${n}.${i + 1}` : `${i + 1}`, tri)).join("")}
    <div class="anadir"><button data-crear="competencias" data-padre="${s.id}">＋ Competencia</button></div>`;
}

function htmlComp(c, num, tri) {
  return `<div class="comp-cab"><div class="num">${num}</div>
      <div class="titulo"><span>Competencias y saberes:</span>
        <input data-tabla="competencias" data-id="${c.id}" data-campo="nombre" value="${esc(c.nombre)}" placeholder="Nombre de la competencia"></div>
      <div class="herr">${botonesOrden("competencias", c.id)}</div></div>
    ${c.items.map((it) => htmlItem(it, tri)).join("")}
    <div class="anadir" style="padding-left:62px"><button data-crear="items" data-padre="${c.id}">＋ Ítem</button></div>`;
}

function htmlItem(it, tri) {
  const sel = (t) => {
    const v = it[`eval_${t}t`];
    return `<div class="tri ${t === tri ? "actual" : ""}"><select class="eval ${claseEval(v)}" data-tabla="items" data-id="${it.id}" data-campo="eval_${t}t" title="${t}º trimestre">
      <option value=""></option>${INFO.escala.map((k) => `<option ${k === v ? "selected" : ""}>${k}</option>`).join("")}</select></div>`;
  };
  return `<div class="fila-tri item ${it.destacado ? "destacado" : ""}">
    <div></div>
    <div class="texto"><textarea rows="1" data-tabla="items" data-id="${it.id}" data-campo="texto" placeholder="Describe el ítem">${esc(it.texto)}</textarea>
      <textarea rows="1" class="nota" data-tabla="items" data-id="${it.id}" data-campo="nota" placeholder="Observación (opcional)">${esc(it.nota || "")}</textarea></div>
    ${sel(1)}${sel(2)}${sel(3)}
    <div class="herr"><button class="icono estrella ${it.destacado ? "on" : ""}" data-id="${it.id}" title="Sombrear en amarillo (ítem nuevo en esta revisión)">⭐</button>${botonesOrden("items", it.id)}</div>
  </div>`;
}

async function exportarWord() {
  await intentar(async () => {
    if (window.pywebview) {
      const r = await api("GET", `/api/acis/${ACI.id}/word?guardar=1`);
      aviso("Guardado en " + r.ruta);
    } else {
      location.href = `/api/acis/${ACI.id}/word`;
    }
  });
}

// ======================================================================= micrófono para cualquier cuadro de texto
// Botón 🎤 que dicta (sin conexión, con Vosk) dentro del cuadro indicado. Si el dictado
// sin conexión no está disponible, recuerda que se puede usar Windows + H.
let VOZ_DISPONIBLE = null;
let microActivo = null;
function botonMicro(destinoId) {
  return `<button type="button" class="mini micro" data-micro="${destinoId}" title="Dictar con el micrófono">🎤</button>`;
}
function enlazarMicros(raiz) {
  raiz.querySelectorAll("[data-micro]").forEach((b) => b.onclick = () => intentar(async () => {
    const ta = document.getElementById(b.dataset.micro);
    if (!ta) return;
    if (microActivo) { const era = microActivo.boton; await pararMicro(); if (era === b) return; }
    if (VOZ_DISPONIBLE === null) VOZ_DISPONIBLE = await api("GET", "/api/voz").catch(() => ({ disponible: false, motivo: "" }));
    if (!VOZ_DISPONIBLE.disponible) {
      ta.focus();
      aviso("Dictado sin conexión no disponible. Pulsa Windows + H para dictar en el cuadro.");
      return;
    }
    const lineas = "microLineas" in ta.dataset;  // notas por líneas: cada dictado en una línea nueva
    const base = lineas ? ta.value.replace(/\s+$/, "") : ta.value.trim();
    const sep = lineas && base ? "\n" : " ";
    await api("POST", "/api/voz/iniciar");
    b.classList.add("grabando");
    b.textContent = "⏹";
    const sondeoMicro = setInterval(async () => {
      const e = await api("GET", "/api/voz").catch(() => null);
      if (!e) return;
      const dicho = [e.texto, e.parcial].filter(Boolean).join(" ");
      ta.value = dicho ? [base, dicho].filter(Boolean).join(sep) : base;
      if (e.error) aviso(e.error, true);
      if (!e.grabando) await pararMicro();
    }, 600);
    microActivo = { boton: b, ta, base, sep, sondeo: sondeoMicro };
  }));
}
async function pararMicro() {
  if (!microActivo) return;
  const { boton, ta, base, sep, sondeo: s } = microActivo;
  microActivo = null;
  clearInterval(s);
  const e = await api("POST", "/api/voz/detener").catch(() => null);
  boton.classList.remove("grabando");
  boton.textContent = "🎤";
  if (e) ta.value = [base, e.texto].filter(Boolean).join(sep || " ");
  ta.dispatchEvent(new Event("change"));
}
window.addEventListener("hashchange", () => { pararMicro(); });

// ======================================================================= dictado
let sondeo = null;

function opcionesDestino() {
  const ops = [`<option value="">— Ninguno (crear «Nueva área») —</option>`];
  for (const a of ACI.areas) {
    ops.push(`<option value='${JSON.stringify({ area_id: a.id })}'>Área: ${esc(a.nombre)}</option>`);
    for (const s of a.subareas) {
      if (s.nombre) ops.push(`<option value='${JSON.stringify({ area_id: a.id, subarea_id: s.id })}'>&nbsp;&nbsp;Subárea: ${esc(s.nombre)}</option>`);
      for (const c of s.competencias)
        ops.push(`<option value='${JSON.stringify({ area_id: a.id, subarea_id: s.id, competencia_id: c.id })}'>&nbsp;&nbsp;&nbsp;&nbsp;Competencia: ${esc(c.nombre || "(sin nombre)")}</option>`);
    }
  }
  return ops.join("");
}

async function abrirDictado() {
  const voz = await api("GET", "/api/voz").catch(() => ({ disponible: false, motivo: "" }));
  dialogo.innerHTML = `
    <div class="dlg-cab"><h2>🎤 Dictar contenido de la ACI</h2><button id="cerrar">Cerrar</button></div>
    <div class="dlg-cuerpo">
      <div class="ayuda">Di la palabra clave y después el texto. Para separar ítems di «punto» o vuelve a decir «ítem».<br>
        <code>Área</code> comunicación y representación de la realidad <code>punto</code>
        <code>Subárea</code> área preverbal <code>punto</code>
        <code>Competencia</code> desarrollar la atención <code>punto</code>
        <code>Ítem</code> mantiene la mirada en el objeto <code>ítem</code> señala el objeto que se le pide…</div>
      <div class="dictado-zona">
        <button class="mic" id="mic" title="${voz.disponible ? "Empezar / parar el dictado" : esc(voz.motivo)}" ${voz.disponible ? "" : "disabled"}>🎤</button>
        <div style="flex:1">
          <textarea id="texto-dictado" placeholder="Pulsa el micrófono y habla, o escribe aquí. También puedes usar el dictado de Windows: haz clic aquí y pulsa la tecla Windows + H."></textarea>
          <div class="parcial" id="parcial">${voz.disponible ? "" : "Dictado sin conexión no disponible: " + esc(voz.motivo) + " Usa Windows + H para dictar en el cuadro."}</div>
        </div>
      </div>
      <div class="campos" style="margin-top:10px">
        <div class="campo-ancho"><label>Si dictas sin decir el área, subárea o competencia, añadir en:</label>
          <select id="destino">${opcionesDestino()}</select></div>
      </div>
      <div id="vista-previa"></div>
    </div>
    <div class="dlg-pie">
      <button id="analizar">Revisar lo dictado</button>
      <button class="primario" id="aplicar" disabled>Añadir a la ACI</button>
    </div>`;
  dialogo.showModal();
  const ta = $("#texto-dictado");
  let analisis = null;
  const cerrar = async () => { await pararVoz(); dialogo.close(); };
  $("#cerrar").onclick = cerrar;
  dialogo.oncancel = (e) => { e.preventDefault(); cerrar(); };
  ta.oninput = () => { $("#aplicar").disabled = true; };

  $("#mic").onclick = () => intentar(async () => {
    const mic = $("#mic");
    if (mic.classList.contains("grabando")) { await pararVoz(); return; }
    const base = ta.value.trim();
    await api("POST", "/api/voz/iniciar");
    mic.classList.add("grabando");
    sondeo = setInterval(async () => {
      const e = await api("GET", "/api/voz");
      ta.value = [base, e.texto].filter(Boolean).join(" ");
      $("#parcial").textContent = e.error || e.parcial || "Escuchando…";
      if (!e.grabando) await pararVoz();
    }, 600);
  });

  async function pararVoz() {
    if (!sondeo) return;
    clearInterval(sondeo); sondeo = null;
    const mic = $("#mic");
    const e = await api("POST", "/api/voz/detener").catch(() => null);
    if (mic) mic.classList.remove("grabando");
    if (e && e.texto && !ta.value.includes(e.texto)) ta.value = (ta.value + " " + e.texto).trim();
    const p = $("#parcial"); if (p) p.textContent = e && e.error ? e.error : "";
    if (ta.value.trim()) $("#analizar").click();
  }

  $("#analizar").onclick = () => intentar(async () => {
    analisis = await api("POST", "/api/dictado/analizar", { texto: ta.value });
    $("#vista-previa").innerHTML = htmlVistaPrevia(analisis);
    $("#aplicar").disabled = !analisis.areas.length;
  });
  $("#aplicar").onclick = () => intentar(async () => {
    if (!analisis) return;
    const destino = $("#destino").value ? JSON.parse($("#destino").value) : null;
    const r = await api("POST", `/api/acis/${ACI.id}/dictado`, { areas: analisis.areas, contexto: destino });
    dialogo.close();
    aviso(`Añadido: ${r.areas} áreas, ${r.subareas} subáreas, ${r.competencias} competencias y ${r.items} ítems nuevos`);
    recargarACI();
  });
}

function htmlVistaPrevia(an) {
  if (!an.areas.length) return `<div class="aviso">No se ha reconocido ningún contenido. Revisa que el texto empiece por «área», «subárea», «competencia» o «ítem».</div>`;
  const t = an.totales;
  const li = (etq, clase, txt, hijos = "") => `<li><span class="etq">${etq}</span><span class="${clase}">${esc(txt)}</span>${hijos}</li>`;
  const arbol = an.areas.map((a) => li("Área", "n-area", a.nombre || "(la seleccionada)", `<ul>${a.subareas.map((s) =>
    li("Subárea", "n-sub", s.nombre || "(sin subárea)", `<ul>${s.competencias.map((c) =>
      li("Competencia", "n-comp", c.nombre || "(la seleccionada)", `<ul>${c.items.map((i) => `<li class="n-item">${esc(i)}</li>`).join("")}</ul>`)).join("")}</ul>`)).join("")}</ul>`)).join("");
  return `<div class="arbol"><p style="margin:0 0 8px"><strong>Se ha entendido:</strong> ${t.areas} áreas, ${t.subareas} subáreas, ${t.competencias} competencias y ${t.items} ítems.
      Si un área, subárea o competencia ya existe con el mismo nombre, se añadirá dentro de ella.</p><ul>${arbol}</ul></div>
    ${an.avisos.map((a) => `<div class="aviso">⚠️ ${esc(a)}</div>`).join("")}`;
}

// ======================================================================= horario
async function vistaHorario() {
  const [franjas, alumnos] = await Promise.all([api("GET", "/api/franjas"), api("GET", "/api/alumnos")]);
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Mi horario semanal</h1>
      <p class="sub">Configura tus sesiones. En cada sesión, los ítems pendientes de la ACI de cada alumno se reparten automáticamente en la agenda.</p></div>
      <div class="acciones">
        <label class="boton" for="importar-horario" title="Hoja de cálculo con los días en columnas y las horas en filas">📊 Importar horario (Excel o CSV)</label>
        <input type="file" id="importar-horario" accept=".xlsx,.csv" hidden>
        <button class="primario" id="nueva-franja">＋ Añadir franja</button></div></div>
    <div class="semana">${INFO.dias.map((d, i) => `<div class="dia"><h3>${d}</h3><div class="bloques">
      ${franjas.filter((f) => f.dia === i).map((f) => `<div class="franja ${f.tipo === "otro" ? "otro" : ""}" data-franja="${f.id}">
        <div class="hora">${f.inicio}–${f.fin} ${f.tipo === "sesion" ? `<span class="chip">${f.especialidad}</span>` : ""}</div>
        <div class="quien">${esc(f.etiqueta || (f.tipo === "sesion" ? "" : "Otra tarea"))}</div>
        ${f.tipo === "sesion" ? `<div class="quien"><strong>${f.alumnos.map((a) => esc(a.nombre)).join(", ") || '<span class="muted">sin alumnos</span>'}</strong></div>
          <div class="muted" style="font-size:11px">${f.items_por_sesion} ítems por sesión</div>` : ""}
      </div>`).join("") || '<div class="muted" style="text-align:center;padding:20px 0">Libre</div>'}
    </div></div>`).join("")}</div>`;
  $("#nueva-franja").onclick = () => formFranja(null, alumnos);
  $("#importar-horario").onchange = (e) => {
    const archivo = e.target.files[0];
    e.target.value = "";
    if (archivo) dialogoImportarHorario(archivo, franjas.length > 0);
  };
  $$("[data-franja]").forEach((el) => el.onclick = () => formFranja(franjas.find((f) => f.id === +el.dataset.franja), alumnos));
}

// Vista previa al importar: qué alumno de la app es cada nombre del horario y qué va a cambiar
async function dialogoImportarHorario(archivo, hayHorario) {
  const fd = new FormData();
  fd.append("archivo", archivo);
  const p = await intentar(() => api("POST", "/api/horario/analizar", fd));
  const opciones = (n) => `<option value="nuevo" ${n.alumno_id ? "" : "selected"}>＋ Alumno nuevo</option>
    ${p.alumnos.map((a) => `<option value="${a.id}" ${a.id === n.alumno_id ? "selected" : ""}>${esc(a.nombre)}</option>`).join("")}`;
  const c = p.cambios;
  dialogo.innerHTML = `<form method="dialog" id="fimp">
    <div class="dlg-cab"><h2>Importar horario</h2><button type="button" id="cerrar">Cerrar</button></div>
    <div class="dlg-cuerpo">
      <p>He leído <strong>${p.franjas.length} franjas</strong>. Comprueba quién es cada alumno del horario:</p>
      <table class="tabla-adapt"><tr><th>En el horario</th><th>Sesiones</th><th>Alumno en la app</th><th>Si es nuevo</th></tr>
        ${p.nombres.map((n, i) => `<tr><td><strong>${esc(n.texto)}</strong>${n.dudoso ? ' <span class="chip pendientes" title="Hay varios alumnos que encajan: comprueba que es el correcto">¿seguro?</span>' : ""}</td>
          <td>${n.sesiones}</td><td><select data-nombre="${i}">${opciones(n)}</select></td>
          <td><label class="check" data-valoracion-de="${i}" ${n.alumno_id ? "hidden" : ""}><input type="checkbox" data-valoracion="${i}" checked> En valoración, sin ACI</label></td></tr>`).join("")}</table>
      ${hayHorario ? `<div class="aviso" style="margin-top:12px">Al <strong>actualizar</strong> tu horario: ${c.nuevas} franjas nuevas, ${c.cambiadas} cambian, ${c.iguales} siguen igual y ${c.retiradas} se quitan.
        Las notas, la asistencia y las observaciones de las sesiones ya hechas <strong>se conservan</strong>; solo se quitan las sesiones futuras vacías de lo que cambia.</div>` : ""}
    </div>
    <div class="dlg-pie">${hayHorario ? `<button type="button" id="solo-anadir" style="margin-right:auto" title="No toca tu horario actual: solo añade las franjas que no se solapan">Solo añadir franjas</button>` : ""}
      <button class="primario" id="aplicar-horario">${hayHorario ? "Actualizar mi horario" : "Importar horario"}</button></div></form>`;
  dialogo.showModal();
  $("#cerrar").onclick = () => dialogo.close();
  $$("[data-nombre]").forEach((sel) => sel.onchange = () => { $(`[data-valoracion-de="${sel.dataset.nombre}"]`).hidden = sel.value !== "nuevo"; });
  const aplicar = (reemplazar) => intentar(async () => {
    const asignacion = {}, valoracion = [];
    p.nombres.forEach((n, i) => {
      const v = $(`[data-nombre="${i}"]`).value;
      asignacion[n.texto] = v === "nuevo" ? "nuevo" : +v;
      if (v === "nuevo" && $(`[data-valoracion="${i}"]`).checked) valoracion.push(n.texto);
    });
    const fd2 = new FormData();
    fd2.append("archivo", archivo);
    fd2.append("reemplazar", reemplazar ? "1" : "0");
    fd2.append("asignacion", JSON.stringify(asignacion));
    fd2.append("en_valoracion", JSON.stringify(valoracion));
    const r = await api("POST", "/api/horario/importar", fd2);
    dialogo.close();
    let txt = `Horario guardado: ${r.franjas} franjas`;
    if (r.retiradas) txt += `, ${r.retiradas} quitadas`;
    if (r.alumnos_nuevos.length) txt += `. Alumnos nuevos: ${r.alumnos_nuevos.join(", ")}`;
    if (r.omitidas.length) txt += `. Omitidas por solaparse: ${r.omitidas.length}`;
    if (r.planificadas) txt += `. ${r.planificadas} sesiones nuevas esta semana`;
    aviso(txt);
    vistaHorario();
  });
  $("#fimp").onsubmit = (e) => { e.preventDefault(); aplicar(hayHorario); };
  if (hayHorario) $("#solo-anadir").onclick = () => aplicar(false);
}

function formFranja(f, alumnos) {
  const v = f || { dia: 0, inicio: "09:00", fin: "09:45", tipo: "sesion", etiqueta: "", especialidad: "PT/AL", items_por_sesion: 3, alumnos: [] };
  const elegidos = new Set(v.alumnos.map((a) => a.id));
  dialogo.innerHTML = `<form method="dialog" id="ff">
    <div class="dlg-cab"><h2>${f ? "Editar franja" : "Nueva franja"}</h2><button type="button" id="cerrar">Cerrar</button></div>
    <div class="dlg-cuerpo"><div class="campos">
      <div><label>Día</label><select name="dia">${INFO.dias.map((d, i) => `<option value="${i}" ${i === v.dia ? "selected" : ""}>${d}</option>`).join("")}</select></div>
      <div><label>Inicio</label><input type="time" name="inicio" value="${v.inicio}" required></div>
      <div><label>Fin</label><input type="time" name="fin" value="${v.fin}" required></div>
      <div><label>Tipo</label><select name="tipo"><option value="sesion" ${v.tipo === "sesion" ? "selected" : ""}>Sesión con alumnos</option>
        <option value="otro" ${v.tipo === "otro" ? "selected" : ""}>Otra tarea (coordinación, recreo…)</option></select></div>
      <div><label>Especialidad</label><select name="especialidad">${["PT/AL", "AL", "PT"].map((e) => `<option ${e === v.especialidad ? "selected" : ""}>${e}</option>`).join("")}</select></div>
      <div><label>Ítems a trabajar por sesión</label><input type="number" name="items_por_sesion" min="1" max="10" value="${v.items_por_sesion}"></div>
      <div class="campo-ancho"><label>Descripción (opcional)</label><input name="etiqueta" value="${esc(v.etiqueta)}" placeholder="p. ej. Aula 3 años B, apoyo dentro del aula"></div>
      <div class="campo-ancho"><label>Alumnos de la sesión</label>
        <div class="lista-alumnos">${alumnos.map((a) => `<label><input type="checkbox" name="alumnos" value="${a.id}" ${elegidos.has(a.id) ? "checked" : ""}>${esc(a.nombre)}</label>`).join("") || '<span class="muted">Primero crea algún alumno.</span>'}</div></div>
    </div></div>
    <div class="dlg-pie">${f ? '<button type="button" class="peligro" id="borrar-franja" style="margin-right:auto">Borrar franja</button>' : ""}
      <button class="primario" id="guardar-franja">Guardar</button></div></form>`;
  dialogo.showModal();
  $("#cerrar").onclick = () => dialogo.close();
  if (f) $("#borrar-franja").onclick = () => intentar(async () => {
    if (!confirm("¿Quitar esta franja del horario? Se borran sus sesiones futuras vacías; las sesiones ya hechas y sus notas se conservan.")) return;
    await api("DELETE", `/api/franjas/${f.id}`); dialogo.close(); aviso("Franja quitada del horario"); vistaHorario();
  });
  $("#ff").onsubmit = (e) => {
    e.preventDefault();
    intentar(async () => {
      const fd = new FormData(e.target);
      const datos = Object.fromEntries(fd);
      datos.alumnos = fd.getAll("alumnos").map(Number);
      datos.dia = +datos.dia; datos.items_por_sesion = +datos.items_por_sesion;
      if (f) await api("PUT", `/api/franjas/${f.id}`, datos); else await api("POST", "/api/franjas", datos);
      dialogo.close(); aviso("Horario guardado"); vistaHorario();
    });
  };
}

// ======================================================================= agenda
// Vista «semana» (lunes a viernes) o «dia» (línea de tiempo con sesiones y citas)
async function vistaAgenda(modo, fecha) {
  modo = modo || leerPref("agenda", "semana");
  guardarPref("agenda", modo);
  const hoy = hoyISO();
  if (modo === "dia") return vistaAgendaDia(fecha || (esFinde(hoy) ? diaLaborable(hoy, 1) : hoy));
  const desde = lunesISO(fecha || hoy);
  const hasta = sumarDias(desde, 4);
  const ag = await api("GET", `/api/agenda?desde=${desde}&hasta=${hasta}`);
  const porDia = INFO.dias.map((_, i) => ag.sesiones.filter((s) => s.fecha === sumarDias(desde, i)));
  const diaRef = hoy >= desde && hoy <= hasta ? hoy : desde;
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Agenda de sesiones</h1>
      <p class="sub">Semana del ${fechaCorta(desde)} al ${fechaCorta(hasta)}. Los ítems no conseguidos se reparten solos en tus sesiones.</p></div>
      <div class="acciones">
        ${selectorAgenda("semana", diaRef)}
        <div class="nav-fechas"><a class="boton" href="#/agenda/semana/${sumarDias(desde, -7)}" title="Semana anterior">◀</a>
          <a class="boton" href="#/agenda/semana/${lunesISO(hoy)}">Hoy</a>
          <a class="boton" href="#/agenda/semana/${sumarDias(desde, 7)}" title="Semana siguiente">▶</a></div>
        <button class="primario" id="planificar">⚡ Planificar semana</button>
        <button id="replanificar" title="Vuelve a repartir los ítems de las sesiones aún no realizadas">↻ Replanificar</button>
      </div></div>
    <div id="avisos-agenda"></div>
    ${ag.sesiones.length ? "" : `<div class="vacio" style="margin-bottom:14px">No hay sesiones planificadas esta semana. Configura <a href="#/horario">tu horario</a> y pulsa «Planificar semana».</div>`}
    <div class="semana">${INFO.dias.map((d, i) => { const f = sumarDias(desde, i); return `<div class="dia ${f === hoy ? "hoy" : ""}">
      <h3><a class="abrir-dia" href="#/agenda/dia/${f}" title="Ver este día en grande">${d} <small>${fechaCorta(f)}</small></a></h3>
      <div class="bloques">${porDia[i].map(htmlSesion).join("") || '<div class="muted" style="text-align:center;padding:20px 0">—</div>'}</div></div>`; }).join("")}</div>`;
  enlazarPlanificar(desde, hasta, () => vistaAgenda("semana", desde));
  pintarAvisos($("#avisos-agenda"));
  enlazarSesiones(() => vistaAgenda("semana", desde));
}

function selectorAgenda(actual, dia) {
  return selectorVista(actual, [["dia", "Día", `#/agenda/dia/${esFinde(dia) ? diaLaborable(dia, 1) : dia}`],
    ["semana", "Semana", `#/agenda/semana/${lunesISO(dia)}`]]);
}

function enlazarPlanificar(desde, hasta, recargar) {
  const plan = (re) => intentar(async () => {
    const r = await api("POST", "/api/planificar", { desde, hasta, replanificar: re });
    let txt = `Planificadas ${r.sesiones} sesiones nuevas con ${r.items} ítems`;
    if (r.sin_pendientes.length) txt += `. Sin ítems pendientes: ${r.sin_pendientes.join(", ")}`;
    aviso(txt);
    recargar();
  });
  $("#planificar").onclick = () => plan(false);
  $("#replanificar").onclick = () => { if (confirm("Se volverán a repartir los ítems de las sesiones no realizadas de esta semana. ¿Continuar?")) plan(true); };
}

// Botones y campos de las tarjetas de sesión (vista semana y vista día)
function enlazarSesiones(recargar) {
  $$("[data-sesion-estado]").forEach((b) => b.onclick = () => intentar(async () => {
    await api("PATCH", `/api/sesiones/${b.dataset.id}`, { estado: b.dataset.sesionEstado });
    recargar();
  }));
  $$("[data-falta]").forEach((b) => b.onclick = () => intentar(async () => {
    const motivo = prompt("El alumno no ha venido. Motivo (opcional): enfermedad, cita médica…", "");
    if (motivo === null) return;
    await api("PATCH", `/api/sesiones/${b.dataset.falta}`, { falta: true, motivo });
    recargar();
  }));
  $$("[data-trabajado]").forEach((c) => c.onchange = () => intentar(() =>
    api("PATCH", `/api/sesiones/${c.dataset.sesion}/items/${c.dataset.item}`, { trabajado: c.checked })));
  $$("[data-evaluar]").forEach((s) => s.onchange = () => intentar(async () => {
    await api("PATCH", `/api/sesiones/${s.dataset.sesion}/items/${s.dataset.item}`, { evaluacion: s.value });
    s.className = claseEval(s.value);
    if (s.value === "C") aviso("¡Ítem conseguido! Ya no se volverá a planificar.");
  }));
  $$("[data-quitar]").forEach((b) => b.onclick = () => intentar(async () => {
    await api("DELETE", `/api/sesiones/${b.dataset.sesion}/items/${b.dataset.item}`);
    recargar();
  }));
  $$("[data-notas]").forEach((t) => t.onchange = () => intentar(() => api("PATCH", `/api/sesiones/${t.dataset.notas}`, { notas: t.value })));
  $$("[data-notas-frase]").forEach((caja) => caja.querySelectorAll(".frase").forEach((b) => b.onclick = () => {
    const ta = $("#notas-" + caja.dataset.notasFrase);
    const base = ta.value.trim().replace(/[.,;]$/, "");
    ta.value = base ? `${base}. ${b.textContent}` : b.textContent;
    ta.dispatchEvent(new Event("change"));
  }));
  $$("[data-obs-item]").forEach((t) => t.onchange = () => intentar(() =>
    api("PATCH", `/api/sesiones/${t.dataset.sesion}/items/${t.dataset.item}`, { observacion: t.value })));
  enlazarMicros(vista);
}

// Día en grande: sesiones y citas de Mi trabajo intercaladas por hora, y tareas que vencen ese día
async function vistaAgendaDia(dia) {
  await infoTrabajo();
  const [ag, ci, alumnos, tareas, evs] = await Promise.all([
    api("GET", `/api/agenda?desde=${dia}&hasta=${dia}`), api("GET", `/api/citas?desde=${dia}&hasta=${dia}`),
    api("GET", "/api/alumnos"), api("GET", "/api/tareas"),
    api("GET", `/api/eventos-externos?desde=${dia}&hasta=${dia}`).catch(() => [])]);
  const cals = await api("GET", "/api/calendarios").catch(() => []);
  const hoy = hoyISO();
  const recargar = () => vistaAgendaDia(dia);
  const vencen = tareas.filter((t) => !t.hecha && t.fecha_limite === dia);
  const eventos = ordenarPorHora([...ag.sesiones.map((s) => ({ hora: s.inicio, sesion: s })),
    ...ci.citas.map((c) => ({ hora: c.hora_inicio, cita: c })),
    ...evs.filter((e) => !e.todo_el_dia && e.inicio.slice(0, 10) === dia).map((e) => ({ hora: horaEv(e), externo: e }))]);
  const lunesDia = lunesISO(dia);
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Agenda de sesiones</h1>
      <p class="sub titulo-dia">${mayus(fechaLarga(dia))}${dia === hoy ? ' <span class="chip">hoy</span>' : ""}</p></div>
      <div class="acciones">
        ${selectorAgenda("dia", dia)}
        <div class="nav-fechas"><a class="boton" href="#/agenda/dia/${diaLaborable(dia, -1)}" title="Día anterior">◀</a>
          <a class="boton" href="#/agenda/dia/${esFinde(hoy) ? diaLaborable(hoy, 1) : hoy}">Hoy</a>
          <a class="boton" href="#/agenda/dia/${diaLaborable(dia, 1)}" title="Día siguiente">▶</a></div>
        <button class="primario" id="planificar" title="Planifica la semana de este día">⚡ Planificar semana</button>
        <button id="replanificar" title="Vuelve a repartir los ítems de las sesiones aún no realizadas">↻ Replanificar</button>
      </div></div>
    <div id="avisos-agenda"></div>
    ${htmlEstadoCalendarios(cals)}
    ${htmlFranjaTodoElDia(evs)}
    ${htmlTareasDelDia(vencen)}
    <div class="dia-detalle">
      ${eventos.length ? `<div class="linea-tiempo">${eventos.map((e) => `<div class="lt-fila">
          <div class="lt-hora">${e.hora || "—"}</div>
          <div class="lt-cont">${e.sesion ? htmlSesion(e.sesion) : htmlEntrada(e)}</div></div>`).join("")}</div>`
        : `<div class="vacio">No tienes nada este día 🌿<br><span class="muted">Si debería haber sesiones, pulsa «Planificar semana».</span></div>`}
      <p style="margin-top:12px"><button id="cita-dia">＋ Añadir una cita este día</button></p></div>`;
  enlazarPlanificar(lunesDia, sumarDias(lunesDia, 4), recargar);
  pintarAvisos($("#avisos-agenda"));
  enlazarSesiones(recargar);
  enlazarCitasYTareas(ci.citas, alumnos, recargar);
  enlazarEventos(evs);
  enlazarLeyendaCal(cals, recargar);
  if ($("#actualizar-cal")) $("#actualizar-cal").onclick = () => intentar(async () => { await actualizarCalendarios(0); recargar(); });
  $("#cita-dia").onclick = () => dialogoCita({ fecha: dia }, alumnos, recargar);
}

function ordenarPorHora(eventos) {
  return eventos.sort((a, b) => (a.hora || "99:99").localeCompare(b.hora || "99:99"));
}
const mayus = (s) => s ? s[0].toUpperCase() + s.slice(1) : s;

function htmlCitaTarjeta(c) {
  const tipo = TRABAJO ? TRABAJO.tipos_cita[c.tipo] : c.tipo;
  return `<button type="button" class="cita-tarjeta ${c.tipo} ${c.hecha ? "hecha" : ""}" data-cita="${c.id}" title="Pulsa para ver o cambiar la cita">
    <span class="ct-tipo">${esc(tipo)}${c.hecha ? " · hecha" : ""}</span>
    <span class="ct-hora">${c.hora_inicio || "Sin hora"}${c.hora_fin ? "–" + c.hora_fin : ""}</span>
    ${[c.alumno, c.con_quien].filter(Boolean).length ? `<span class="ct-quien">${esc([c.alumno, c.con_quien].filter(Boolean).join(" · "))}</span>` : ""}
    ${c.lugar ? `<span class="ct-lugar">📍 ${esc(c.lugar)}</span>` : ""}
    ${c.notas ? `<span class="ct-notas">${esc(c.notas)}</span>` : ""}</button>`;
}

function htmlTareasDelDia(tareas) {
  if (!tareas.length) return "";
  const cats = TRABAJO ? TRABAJO.categorias : {};
  return `<div class="tareas-dia"><strong>📌 ${tareas.length === 1 ? "Tarea que vence este día" : "Tareas que vencen este día"}</strong>
    <ul>${tareas.map((t) => `<li><label><input type="checkbox" data-tarea-dia="${t.id}"> ${esc(t.texto)}</label>
      <span class="cat ${t.categoria}">${esc(cats[t.categoria] || t.categoria)}</span>${t.alumno ? ` <span class="muted">👧 ${esc(t.alumno)}</span>` : ""}</li>`).join("")}</ul></div>`;
}

// Clic en citas (abre el diálogo) y tic en las tareas del día
function enlazarCitasYTareas(citas, alumnos, recargar) {
  $$("[data-cita]").forEach((b) => b.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const c = citas.find((x) => String(x.id) === b.dataset.cita);
    if (c) dialogoCita(c, alumnos, recargar);
  });
  $$("[data-tarea-dia]").forEach((c) => c.onchange = () => intentar(async () => {
    await api("PATCH", `/api/tareas/${c.dataset.tareaDia}`, { hecha: c.checked });
    aviso("¡Tarea hecha! ✔");
    recargar();
  }));
}

// Frases rápidas para las notas de los alumnos en valoración (sin ACI)
const FRASES_OBS_SESION = ["Viene contento/a", "Le cuesta separarse del aula", "Atiende bien", "Se distrae con facilidad",
  "Necesita que le redirija", "Sigue órdenes sencillas", "No comprende la orden", "Se comunica con gestos",
  "Usa palabras sueltas", "Hace frases cortas", "Habla poco inteligible", "Juega con los compañeros",
  "Prefiere jugar solo/a", "Respeta el turno", "Se frustra", "Le ayuda el apoyo visual"];

function htmlSesion(s) {
  const obs = s.seguimiento === "observacion" || !s.aci_id;
  return `<div class="sesion ${s.estado}">
    <div class="cab-ses"><span class="franja" style="padding:0;background:none;border:none;cursor:default"><span class="hora">${s.inicio}–${s.fin}</span></span>
      ${s.aci_id ? `<a href="#/aci/${s.aci_id}" title="Abrir ACI">${esc(s.alumno)}</a>` : `<a href="#/alumno/${s.alumno_id}" title="Abrir ficha">${esc(s.alumno)}</a>`}<span class="chip">${s.especialidad}</span>
      ${s.seguimiento === "observacion" ? '<span class="chip valoracion" title="Sin ACI: tus notas irán a su informe de observación">En valoración</span>' : ""}</div>
    ${s.items.length ? `<ul>${s.items.map((it) => `<li>
      <input type="checkbox" title="Trabajado en la sesión" data-trabajado data-sesion="${s.id}" data-item="${it.id}" ${it.trabajado ? "checked" : ""}>
      <div>${esc(it.texto)}<div class="ctx">${esc(it.subarea || it.area)} · ${esc(it.competencia)}</div>
        <div class="pie-item"><select title="Evaluación del trimestre actual" class="${claseEval(it.evaluacion)}" data-evaluar data-sesion="${s.id}" data-item="${it.id}">
        <option value=""></option>${INFO.escala.map((k) => `<option ${k === it.evaluacion ? "selected" : ""}>${k}</option>`).join("")}</select>
        <button class="icono" title="Quitar de esta sesión" data-quitar data-sesion="${s.id}" data-item="${it.id}">✕ quitar</button></div>
        <div class="obs-item"><textarea rows="1" class="nota" placeholder="Observación rápida (luego se redacta en el informe)" id="obs-${s.id}-${it.id}"
          data-obs-item data-sesion="${s.id}" data-item="${it.id}">${esc(it.observacion || "")}</textarea>${botonMicro(`obs-${s.id}-${it.id}`)}</div></div></li>`).join("")}</ul>`
      : obs ? `<p class="muted" style="font-size:12px">Sin ACI: apunta cómo se ha mostrado en la sesión; luego lo usarás en su informe de observación.</p>`
      : `<p class="muted" style="font-size:12px">Sin ítems pendientes asignados.</p>`}
    <div class="notas-sesion"><textarea rows="2" placeholder="Notas de la sesión (escríbelas o díctalas rápido; luego se redactan en el informe)" data-notas="${s.id}" id="notas-${s.id}" style="font-size:12px">${esc(s.notas)}</textarea>
      ${botonMicro("notas-" + s.id)}</div>
    ${obs ? `<details class="frases-sesion"><summary class="muted" style="font-size:12px">Frases rápidas</summary>
      <div class="frases" data-notas-frase="${s.id}">${FRASES_OBS_SESION.map((f) => `<button type="button" class="mini frase">${esc(f)}</button>`).join("")}</div></details>` : ""}
    <div class="estado" style="margin-top:6px">
      ${s.estado !== "realizada" ? `<button class="mini" data-sesion-estado="realizada" data-id="${s.id}">✔ Realizada</button>` : `<span class="chip">Realizada</span>`}
      ${s.estado !== "cancelada" ? `<button class="mini" data-falta="${s.id}" title="El alumno no ha venido: queda registrado como falta">🚫 No ha venido</button>
        <button class="mini" data-sesion-estado="cancelada" data-id="${s.id}" title="La sesión no se hace por otro motivo (excursión, festivo…)">Cancelar</button>`
        : s.falta ? `<span class="chip falta">No vino${s.motivo ? ": " + esc(s.motivo) : ""}</span>` : `<span class="chip">Cancelada</span>`}
      ${s.estado !== "planificada" ? `<button class="mini" data-sesion-estado="planificada" data-id="${s.id}">Deshacer</button>` : ""}
    </div></div>`;
}

// ======================================================================= perfiles
const NOMBRE_ESP = { PT: "Pedagogía Terapéutica", AL: "Audición y Lenguaje", "PT/AL": "PT y AL" };

function pintarPerfilLateral() {
  const el = $("#perfil");
  if (!el) return;
  el.innerHTML = USUARIO
    ? `<div class="avatar-perfil">${esc(USUARIO.nombre[0] || "?").toUpperCase()}</div>
       <div><strong>${esc(USUARIO.nombre)}</strong><span>${esc(NOMBRE_ESP[USUARIO.especialidad] || USUARIO.especialidad)}</span>
       <a href="#/perfiles">Cambiar de perfil</a></div>`
    : `<div><a href="#/perfiles">Elige tu perfil</a></div>`;
}

function elegirPerfil(u) {
  USUARIO = u;
  guardarPerfil(u.id);
  pintarPerfilLateral();
  actualizarCalendarios(30);
}

async function vistaPerfiles() {
  const usuarios = await api("GET", "/api/usuarios");
  const opciones = (actual) => Object.entries(NOMBRE_ESP).map(([k, t]) => `<option value="${k}" ${k === actual ? "selected" : ""}>${t}</option>`).join("");
  vista.innerHTML = `
    <div class="cabecera"><div><h1>${usuarios.length ? "¿Quién eres?" : "Bienvenida a Mundo PT-AL"}</h1>
      <p class="sub">${usuarios.length ? "Cada maestro tiene su propio perfil con sus alumnos, sus ACIs, su horario y su agenda."
        : "Crea tu perfil para empezar. Más adelante podrán añadirse otros maestros en este mismo ordenador."}</p></div></div>
    ${usuarios.length ? `<div class="rejilla">${usuarios.map((u) => `<div class="tarjeta alumno perfil-tarjeta ${USUARIO && USUARIO.id === u.id ? "actual" : ""}">
      <div class="fila"><div class="avatar">${esc(u.nombre[0] || "?").toUpperCase()}</div>
        <div><div class="nombre">${esc(u.nombre)}</div><div class="muted">${esc(NOMBRE_ESP[u.especialidad] || u.especialidad)} · ${u.num_alumnos} alumnos</div></div></div>
      <div class="botones"><button class="primario" data-entrar="${u.id}">${USUARIO && USUARIO.id === u.id ? "Continuar" : "Entrar"}</button></div></div>`).join("")}</div>` : ""}
    ${USUARIO ? `<form class="tarjeta" id="form-editar" style="margin-top:16px"><h2>Mi perfil</h2><div class="campos">
      <div><label>Nombre</label><input name="nombre" value="${esc(USUARIO.nombre)}" required></div>
      <div><label>Especialidad</label><select name="especialidad">${opciones(USUARIO.especialidad)}</select></div>
      </div><p style="margin:12px 0 0"><button>Guardar cambios</button></p></form>` : ""}
    <form class="tarjeta" id="form-perfil" style="margin-top:16px"><h2>${usuarios.length ? "Añadir otro perfil" : "Crear mi perfil"}</h2>
      <div class="campos">
        <div><label>Nombre</label><input name="nombre" required placeholder="p. ej. Fátima Rodríguez García"></div>
        <div><label>Especialidad</label><select name="especialidad">${opciones("PT/AL")}</select></div>
      </div>
      <p style="margin:12px 0 0"><button class="primario">Crear perfil</button></p></form>
    ${usuarios.length ? "" : `<div class="tarjeta" style="margin-top:16px"><h2>¿Ya usabas Mundo PT-AL en otro ordenador?</h2>
      <p>Si te han pasado un archivo de datos (.db), cárgalo aquí y tendrás tu perfil con tus alumnos, ACIs, horario e informes.</p>
      <p><label class="boton primario" for="importar-datos">📥 Importar datos de otro ordenador</label>
        <input type="file" id="importar-datos" accept=".db" hidden></p></div>`}`;
  const imp = $("#importar-datos");
  if (imp) imp.onchange = (e) => importarDatos(e);
  $$("[data-entrar]").forEach((b) => b.onclick = () => {
    elegirPerfil(usuarios.find((u) => u.id === +b.dataset.entrar));
    location.hash = "#/alumnos";
  });
  $("#form-perfil").onsubmit = (e) => intentar(async () => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(e.target));
    const { id } = await api("POST", "/api/usuarios", datos);
    elegirPerfil({ id, ...datos });
    aviso("Perfil creado");
    location.hash = "#/alumnos";
  });
  const fe = $("#form-editar");
  if (fe) fe.onsubmit = (e) => intentar(async () => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(fe));
    await api("PATCH", `/api/usuarios/${USUARIO.id}`, datos);
    elegirPerfil({ ...USUARIO, ...datos });
    aviso("Perfil guardado");
    vistaPerfiles();
  });
}

// ======================================================================= informes a familias
async function crearInforme(alumnoId, trimestre, cursoEscolar) {
  await intentar(async () => {
    const r = await api("POST", `/api/alumnos/${alumnoId}/informes`, { trimestre, curso_escolar: cursoEscolar });
    location.hash = `#/informe/${r.id}`;
  });
}

async function vistaInformes() {
  const d = await api("GET", "/api/informes");
  let trimestre = d.trimestre;
  const pintar = () => {
    const tarjetaObs = (a) => {
      const ult = (a.observaciones || [])[0];
      return `<div class="tarjeta alumno en-valoracion">
        <div class="fila"><div class="avatar">${esc(a.nombre[0] || "?").toUpperCase()}</div>
          <div><div class="nombre">${esc(a.nombre)}</div><div class="muted">${esc(a.curso || "Curso sin indicar")}</div></div></div>
        <div>${ult ? `<span class="chip valoracion">Observación · ${esc(fechaES(ult.fecha))}</span>` : `<span class="muted">Sin informe de observación</span>`}</div>
        <div class="botones">${ult ? `<a class="boton primario" href="#/observacion/${ult.id}">Abrir informe</a>` : ""}
          <button class="${ult ? "" : "primario"}" data-crear-obs="${a.id}">${ult ? "＋ Otro" : "Crear informe de observación"}</button></div></div>`;
    };
    const enValoracion = d.alumnos.filter((a) => a.seguimiento === "observacion");
    const filas = d.alumnos.filter((a) => a.seguimiento !== "observacion").map((a) => {
      const inf = a.informes.find((x) => x.trimestre === trimestre && x.curso_escolar === d.curso_escolar);
      return `<div class="tarjeta alumno">
        <div class="fila"><div class="avatar">${esc(a.nombre[0] || "?").toUpperCase()}</div>
          <div><div class="nombre">${esc(a.nombre)}</div><div class="muted">${esc(a.curso || "Curso sin indicar")}</div></div></div>
        <div>${inf ? `<span class="chip">Empezado · ${esc(inf.actualizado.slice(0, 10))}</span>` : `<span class="muted">Sin informe</span>`}</div>
        <div class="botones">${inf ? `<a class="boton primario" href="#/informe/${inf.id}">Abrir informe</a>`
          : `<button class="primario" data-crear="${a.id}">Crear informe</button>`}</div></div>`;
    }).join("");
    vista.innerHTML = `
      <div class="migas"><a href="#/alumnos">Alumnos</a> › Informes de todos</div>
      <div class="cabecera"><div><h1>Informes</h1>
        <p class="sub">Informe descriptivo de cómo ha ido el trimestre («Observaciones y comentarios»): cómo se ha mostrado, actitud en las sesiones de PT y AL y evolución en cada área.
        Se prepara un borrador con la ACI, lo completas y lo exportas a Word.
        Lo que apuntes en <a href="#/juntas">Juntas de evaluación</a> se puede redactar y añadir aquí con un botón.</p></div>
        <div class="acciones"><label for="tri" style="align-self:center">Trimestre</label>
          <select id="tri">${[1, 2, 3].map((t) => `<option value="${t}" ${t === trimestre ? "selected" : ""}>${t}º · ${esc(d.curso_escolar)}</option>`).join("")}</select></div></div>
      ${d.alumnos.length ? `<div class="rejilla">${filas}</div>` : `<div class="vacio">Todavía no tienes alumnos en tu perfil.</div>`}
      ${enValoracion.length ? `<h2 class="seccion-alumnos">🔍 Informes de observación · alumnos en valoración, sin ACI</h2>
        <p class="muted">Cómo se muestran en las sesiones (conducta, atención, comunicación, relación…), con tus notas de la agenda. Se exporta a Word.</p>
        <div class="rejilla">${enValoracion.map(tarjetaObs).join("")}</div>` : ""}`;
    $("#tri").onchange = (e) => { trimestre = +e.target.value; pintar(); };
    $$("[data-crear-obs]").forEach((b) => b.onclick = () => intentar(async () => {
      const r = await api("POST", `/api/alumnos/${b.dataset.crearObs}/observaciones`, {});
      location.hash = `#/observacion/${r.id}`;
    }));
    $$("[data-crear]").forEach((b) => b.onclick = () => crearInforme(b.dataset.crear, trimestre, d.curso_escolar));
  };
  pintar();
}

function frasesBoton(clave, campo) {
  return `<div class="frases" data-para="${campo}">${(INFORME.frases[clave] || []).map((f) => `<button type="button" class="mini frase">${esc(f)}</button>`).join("")}</div>`;
}

function bloqueTexto(titulo, campo, ayuda, frases) {
  return `<div class="tarjeta"><h2>${titulo}</h2>${ayuda ? `<p class="muted">${ayuda}</p>` : ""}
    <div class="notas-sesion"><textarea rows="4" data-tabla="informes" data-id="${INFORME.id}" data-campo="${campo}" id="campo-${campo}">${esc(INFORME[campo])}</textarea>
      ${botonMicro("campo-" + campo)}</div>
    ${frases ? frasesBoton(frases, campo) : ""}</div>`;
}

let INFORME = null;
async function vistaInforme(id) {
  INFORME = await api("GET", `/api/informes/${id}`);
  const I = INFORME;
  const esp = (USUARIO && USUARIO.especialidad) || "PT/AL";
  vista.innerHTML = `
    <div class="migas"><a href="#/alumnos">Alumnos</a> › <a href="#/alumno/${I.alumno_id}">${esc(I.alumno_nombre)}</a> › ${I.trimestre}º trimestre</div>
    <div class="cabecera"><div><h1>Informe para la familia · ${esc(I.alumno_nombre)}</h1>
      <p class="sub">${I.trimestre}º trimestre · Curso ${esc(I.curso_escolar)}. Se guarda solo al escribir. Para dictar, pulsa 🎤 junto al cuadro (o haz clic en él y pulsa <strong>Windows + H</strong>).</p></div>
      <div class="acciones"><button class="primario" id="word-informe">📄 Exportar a Word</button></div></div>
    <div class="tarjeta"><p class="muted" style="margin-top:0">Se redacta como el apartado «Observaciones y comentarios» de la ACI: un texto seguido para la familia.
      Al exportar la ACI de este trimestre, este texto se incluye también al final de la ACI.</p><div class="campos">
      <div><label>Curso</label><input data-tabla="informes" data-id="${I.id}" data-campo="curso" value="${esc(I.curso)}"></div>
      <div><label>Prof. responsable de área (tutor/a)</label><input data-tabla="informes" data-id="${I.id}" data-campo="prof_area" value="${esc(I.prof_area)}"></div>
      <div><label>Prof. AL/PT</label><input data-tabla="informes" data-id="${I.id}" data-campo="maestra" value="${esc(I.maestra)}"></div></div></div>
    <div class="tarjeta" id="tarjeta-notas"><h2>📝 Tus notas de la agenda</h2><p class="muted">Cargando las notas de las sesiones de este trimestre…</p></div>
    ${bloqueTexto("Cómo se ha mostrado este trimestre", "social", "Ánimo, relación con compañeros y adultos, gestión de emociones…", "social")}
    ${esp !== "AL" ? bloqueTexto("Actitud en las sesiones de PT", "actitud_pt", "", "actitud") : ""}
    ${esp !== "PT" ? bloqueTexto("Actitud en las sesiones de AL", "actitud_al", "", "actitud") : ""}
    <div class="tarjeta"><div class="cabecera" style="margin:0 0 8px"><div><h2 style="margin:0">Evolución en las distintas áreas</h2>
      <p class="muted">Borrador redactado a partir de la ACI: cuenta con frases lo que ha conseguido y resume por temas lo que todavía se está trabajando (la lista completa ya está en la ACI). Añade lo que no esté en la ACI: anécdotas, cómo se expresa, cómo se relaciona… (el título del área no aparece en el Word).</p></div>
      <div class="acciones"><button id="rehacer">↻ Rehacer borrador desde la ACI</button><button id="nueva-area">＋ Añadir área</button></div></div>
      ${I.areas.length ? I.areas.map((a) => `<div class="area-informe">
        <div class="fila" style="gap:8px"><input class="titulo-area" data-tabla="informe_areas" data-id="${a.id}" data-campo="area" value="${esc(a.area)}">
          <button class="mini peligro" data-borrar-area="${a.id}" title="Quitar esta área del informe">✕</button></div>
        <textarea rows="5" data-tabla="informe_areas" data-id="${a.id}" data-campo="texto" id="campo-area-${a.id}">${esc(a.texto)}</textarea>
        <details class="frases-ambito"><summary class="muted">Frases de ayuda: lo que se ha trabajado</summary>
          ${Object.entries(I.frases_ambitos || {}).map(([ambito, lista]) => `<p class="muted" style="margin:6px 0 2px"><strong>${esc(ambito)}</strong></p>
            <div class="frases" data-para="area-${a.id}">${lista.map((f) => `<button type="button" class="mini frase">${esc(f)}</button>`).join("")}</div>`).join("")}
        </details></div>`).join("")
        : `<div class="vacio">No hay áreas. Pulsa «Rehacer borrador desde la ACI» o «Añadir área».</div>`}</div>
    ${bloqueTexto("Estrategias y apoyos que han funcionado", "estrategias", "Opcional: qué le ha ayudado a avanzar (apoyos visuales, refuerzo, materiales motivadores, guía del adulto…).", "estrategias")}
    ${bloqueTexto("Orientaciones para casa", "orientaciones", "Opcional: sugerencias sencillas para seguir avanzando en casa.", "orientaciones")}
    ${bloqueTexto("Cierre", "valoracion", "Unas palabras finales y agradecimiento a la familia. Incluye frases para despedir la etapa de Infantil.", "cierre")}
    <div class="tarjeta"><h2>Despedida</h2><input style="width:100%" data-tabla="informes" data-id="${I.id}" data-campo="despedida" id="campo-despedida" value="${esc(I.despedida)}">
      ${frasesBoton("despedida", "despedida")}</div>`;
  enlazarCampos(vista);
  enlazarMicros(vista);
  pintarNotasInforme(I, esp);
  $$(".frases").forEach((caja) => caja.querySelectorAll(".frase").forEach((b) => b.onclick = () => {
    const ta = $("#campo-" + caja.dataset.para);
    // En la despedida (una sola línea) la frase sustituye; en los cuadros de texto se añade al final
    ta.value = ta.tagName === "INPUT" ? b.textContent : (ta.value.trim() ? ta.value.trim() + " " : "") + b.textContent;
    ta.dispatchEvent(new Event("change"));
  }));
  $("#word-informe").onclick = () => intentar(async () => {
    if (window.pywebview) {
      const r = await api("GET", `/api/informes/${I.id}/word?guardar=1`);
      aviso("Guardado en " + r.ruta);
    } else {
      location.href = `/api/informes/${I.id}/word`;
    }
  });
  $("#rehacer").onclick = () => intentar(async () => {
    if (I.areas.length && !confirm("Se sustituirá el texto de todas las áreas por un borrador nuevo hecho con la ACI. ¿Seguir?")) return;
    await api("POST", `/api/informes/${I.id}/rehacer`);
    vistaInforme(I.id);
  });
  $("#nueva-area").onclick = () => intentar(async () => {
    const nombre = prompt("Nombre del área", "");
    if (nombre === null) return;
    await api("POST", `/api/informes/${I.id}/areas`, { area: nombre });
    vistaInforme(I.id);
  });
  $$("[data-borrar-area]").forEach((b) => b.onclick = () => intentar(async () => {
    if (!confirm("¿Quitar esta área del informe?")) return;
    await api("DELETE", `/api/informe_areas/${b.dataset.borrarArea}`);
    vistaInforme(I.id);
  }));
}

// ======================================================================= informe de observación (sin ACI)
let OBS = null;
async function vistaObservacion(id) {
  OBS = await api("GET", `/api/observaciones/${id}`);
  const O = OBS;
  const campo = (c, etiqueta, tipo = "text") => `<div><label>${etiqueta}</label><input type="${tipo}" data-tabla="informes_observacion" data-id="${O.id}" data-campo="${c}" value="${esc(O[c])}"></div>`;
  vista.innerHTML = `
    <div class="migas"><a href="#/alumnos">Alumnos</a> › <a href="#/alumno/${O.alumno_id}">${esc(O.alumno_nombre)}</a> › Informe de observación</div>
    <div class="cabecera"><div><h1>🔍 Informe de observación · ${esc(O.alumno_nombre)}</h1>
      <p class="sub">Cómo se muestra en las sesiones. Se guarda solo al escribir. Para dictar, pulsa 🎤 junto al cuadro (o <strong>Windows + H</strong>). Los apartados vacíos no salen en el Word.</p></div>
      <div class="acciones"><button class="primario" id="word-obs">📄 Exportar a Word</button></div></div>
    <div class="tarjeta"><div class="campos">
      <div class="campo-ancho"><label>Título</label><input data-tabla="informes_observacion" data-id="${O.id}" data-campo="titulo" value="${esc(O.titulo)}"></div>
      ${campo("curso", "Curso")}${campo("curso_escolar", "Curso escolar")}${campo("fecha", "Fecha del informe", "date")}
      ${campo("desde", "Observado desde", "date")}${campo("hasta", "Hasta (vacío = hasta hoy)", "date")}
      ${campo("destinatario", "Dirigido a (opcional)")}${campo("maestra", "Prof. AL/PT")}</div>
      <p class="muted" style="margin:8px 0 0">El periodo marca qué notas de la agenda se usan abajo y cuántas sesiones constan en el Word.</p></div>
    <div class="tarjeta" id="tarjeta-notas-obs"><h2>📝 Tus notas de la agenda</h2><p class="muted">Cargando…</p></div>
    ${O.apartados.map((ap) => `<div class="tarjeta apartado-obs">
      <div class="fila" style="gap:8px"><input class="titulo-area" data-tabla="observacion_apartados" data-id="${ap.id}" data-campo="titulo" value="${esc(ap.titulo)}">
        ${ap.clave === "contexto" ? `<button class="mini" id="rellenar-contexto" title="Volver a escribir los días y horas según tu horario">↻ Con mi horario</button>` : ""}
        <button class="mini peligro" data-borrar-apartado="${ap.id}" title="Quitar este apartado">✕</button></div>
      ${O.ayudas[ap.clave] ? `<p class="muted" style="margin:4px 0">${esc(O.ayudas[ap.clave])}</p>` : ""}
      <div class="notas-sesion"><textarea rows="4" data-tabla="observacion_apartados" data-id="${ap.id}" data-campo="texto" id="campo-obs-${ap.id}">${esc(ap.texto)}</textarea>
        ${botonMicro("campo-obs-" + ap.id)}</div>
      ${(O.frases[ap.clave] || []).length ? `<div class="frases" data-para="obs-${ap.id}">${O.frases[ap.clave].map((f) => `<button type="button" class="mini frase">${esc(f)}</button>`).join("")}</div>` : ""}
    </div>`).join("")}
    <p><button id="nuevo-apartado">＋ Añadir apartado</button>
      <button class="peligro" id="borrar-obs" style="float:right">Borrar este informe</button></p>`;
  enlazarCampos(vista);
  enlazarMicros(vista);
  $$(".frases").forEach((caja) => caja.querySelectorAll(".frase").forEach((b) => b.onclick = () => {
    const ta = $("#campo-" + caja.dataset.para);
    ta.value = (ta.value.trim() ? ta.value.trim() + " " : "") + b.textContent;
    ta.dispatchEvent(new Event("change"));
  }));
  // Al cambiar el periodo se recargan las notas de la agenda
  $$('[data-campo="desde"],[data-campo="hasta"]').forEach((el) => el.addEventListener("change", () => setTimeout(() => pintarNotasObs(O), 300)));
  pintarNotasObs(O);
  const ctx = $("#rellenar-contexto");
  if (ctx) ctx.onclick = () => intentar(async () => {
    const r = await api("GET", `/api/observaciones/${O.id}/contexto`);
    const ap = O.apartados.find((x) => x.clave === "contexto");
    const ta = $("#campo-obs-" + ap.id);
    if (!r.texto) { aviso("No está en ninguna sesión de tu horario"); return; }
    if (ta.value.trim() && !confirm("Se sustituirá el texto de este apartado por los días y horas de tu horario. ¿Seguir?")) return;
    ta.value = r.texto;
    ta.dispatchEvent(new Event("change"));
  });
  $("#word-obs").onclick = () => intentar(async () => {
    if (window.pywebview) {
      const r = await api("GET", `/api/observaciones/${O.id}/word?guardar=1`);
      aviso("Guardado en " + r.ruta);
    } else {
      location.href = `/api/observaciones/${O.id}/word`;
    }
  });
  $("#nuevo-apartado").onclick = () => intentar(async () => {
    const titulo = prompt("Nombre del apartado", "Otras observaciones");
    if (titulo === null) return;
    await api("POST", `/api/observaciones/${O.id}/apartados`, { titulo });
    vistaObservacion(O.id);
  });
  $$("[data-borrar-apartado]").forEach((b) => b.onclick = () => intentar(async () => {
    if (!confirm("¿Quitar este apartado del informe?")) return;
    await api("DELETE", `/api/observacion_apartados/${b.dataset.borrarApartado}`);
    vistaObservacion(O.id);
  }));
  $("#borrar-obs").onclick = () => intentar(async () => {
    if (!confirm("¿Borrar este informe de observación? No se puede deshacer.")) return;
    await api("DELETE", `/api/informes_observacion/${O.id}`);
    location.hash = `#/alumno/${O.alumno_id}`;
  });
}

async function pintarNotasObs(O) {
  const d = await api("GET", `/api/observaciones/${O.id}/notas`).catch(() => null);
  const caja = $("#tarjeta-notas-obs");
  if (!caja || !d) return;
  const f = d.asistencia.faltas;
  const asis = `<p><strong>${d.asistencia.realizadas}</strong> sesiones realizadas del ${fechaES(d.desde)} al ${fechaES(d.hasta)}
    · <strong>${f.length} ${f.length === 1 ? "falta" : "faltas"}</strong></p>`;
  if (!d.notas.length) {
    caja.innerHTML = `<h2>📝 Tus notas de la agenda</h2>${asis}<p class="muted">Aún no hay notas de sesiones en este periodo. Lo que escribas o dictes
      en las notas de cada sesión de la agenda aparecerá aquí, ya redactado, para añadirlo al apartado que quieras.</p>`;
    return;
  }
  const opciones = (sug) => O.apartados.map((ap) => `<option value="${ap.id}" ${ap.clave === sug ? "selected" : ""}>${esc(ap.titulo)}</option>`).join("");
  caja.innerHTML = `<h2>📝 Tus notas de la agenda</h2>${asis}
    <p class="muted">Cada nota ya va redactada y con el apartado que parece corresponderle. Revísala y pulsa «Añadir».</p>
    ${d.notas.map((n, i) => `<div class="obs-informe" style="border-top:1px solid var(--borde, #ddd);padding-top:8px;margin-top:8px">
      <p class="muted" style="margin:0"><strong>${fechaCorta(n.fecha)}</strong> · ${esc(n.original)}</p>
      <textarea rows="2" id="nota-obs-${i}">${esc(n.texto)}</textarea>
      <div class="fila" style="gap:8px;margin-top:6px;flex-wrap:wrap"><label class="muted">Añadir a:</label>
        <select id="nota-obs-dest-${i}">${opciones(n.apartado)}</select>
        <button class="mini" data-usar-nota-obs="${i}">＋ Añadir</button></div></div>`).join("")}`;
  $$("[data-usar-nota-obs]").forEach((b) => b.onclick = () => {
    const i = b.dataset.usarNotaObs;
    const ta = $("#campo-obs-" + $("#nota-obs-dest-" + i).value);
    const txt = $("#nota-obs-" + i).value.trim();
    if (!ta || !txt) return;
    ta.value = (ta.value.trim() ? ta.value.trim() + " " : "") + txt;
    ta.dispatchEvent(new Event("change"));
    b.textContent = "✔ Añadida";
    aviso("Nota añadida al apartado");
  });
}

function htmlAsistencia(d) {
  const f = d.faltas;
  return `<p><strong>${d.trimestre}º trimestre ${esc(d.curso_escolar)}</strong>: ${d.realizadas} sesiones realizadas ·
      <strong>${f.length} ${f.length === 1 ? "falta" : "faltas"}</strong>${d.canceladas ? ` · ${d.canceladas} canceladas por otros motivos` : ""}</p>
    ${f.length ? `<ul class="lista-notas">${f.map((x) => `<li>${fechaCorta(x.fecha)}${x.motivo ? " · " + esc(x.motivo) : ""}</li>`).join("")}</ul>` : ""}`;
}

async function pintarAsistencia(alumnoId) {
  const caja = $("#asistencia");
  const pintar = async (trimestre, curso) => {
    const q = trimestre ? `?trimestre=${trimestre}&curso_escolar=${encodeURIComponent(curso)}` : "";
    const d = await api("GET", `/api/alumnos/${alumnoId}/asistencia${q}`).catch(() => null);
    if (!d || !caja.isConnected) return;
    caja.innerHTML = `<div class="fila" style="justify-content:space-between;flex-wrap:wrap;gap:8px"><h2 style="margin:0">Asistencia a las sesiones</h2>
        <select id="trim-asist">${[1, 2, 3].map((t) => `<option value="${t}" ${t === d.trimestre ? "selected" : ""}>${t}º trimestre</option>`).join("")}</select></div>
      ${htmlAsistencia(d)}
      <p class="muted" style="margin:6px 0 0">Se marca en la agenda con «🚫 No ha venido» en la sesión.</p>`;
    $("#trim-asist").onchange = (e) => pintar(e.target.value, d.curso_escolar);
  };
  pintar();
}

const normArea = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/^\s*area\s+(de\s+)?/, "").trim();

async function pintarNotasInforme(I, esp) {
  const d = await api("GET", `/api/informes/${I.id}/notas`).catch(() => null);
  const caja = $("#tarjeta-notas");
  if (!caja || !d) return;
  const asis = `<div class="asistencia-informe">${htmlAsistencia(d.asistencia)}</div>`;
  const obs = d.observaciones || [];
  if (!d.notas.length && !d.items.length && !obs.length) {
    caja.innerHTML = `<h2>📝 Tus notas de la agenda</h2>${asis}<p class="muted">Aún no hay notas ni ítems trabajados en la agenda de este trimestre
      (${fechaCorta(d.desde)} – ${fechaCorta(d.hasta)}). Lo que escribas o dictes en las notas de cada sesión aparecerá aquí para redactar el informe.</p>`;
    return;
  }
  const destinos = [["social", "Cómo se ha mostrado este trimestre"],
    ...(esp !== "AL" ? [["actitud_pt", "Actitud en las sesiones de PT"]] : []),
    ...(esp !== "PT" ? [["actitud_al", "Actitud en las sesiones de AL"]] : []),
    ["estrategias", "Estrategias y apoyos que han funcionado"], ["valoracion", "Cierre"]];
  caja.innerHTML = `<h2>📝 Tus notas de la agenda</h2>${asis}
    <p class="muted">${d.sesiones} sesiones este trimestre, ${d.notas.length} con notas. Abajo tienes un borrador redactado con ellas:
      revísalo, cámbialo a tu gusto y añádelo al apartado que quieras.</p>
    <details><summary class="muted">Ver mis notas tal cual (${d.notas.length})</summary>
      <ul class="lista-notas">${d.notas.map((n) => `<li><strong>${fechaCorta(n.fecha)}</strong> · ${esc(n.notas)}</li>`).join("")}</ul></details>
    <textarea rows="5" id="borrador-notas" style="margin-top:8px">${esc(d.borrador)}</textarea>
    <div class="fila" style="gap:8px;margin-top:8px;flex-wrap:wrap"><label class="muted">Añadir a:</label>
      <select id="destino-notas">${destinos.map(([k, t]) => `<option value="${k}">${t}</option>`).join("")}</select>
      <button class="primario" id="usar-notas">＋ Añadir al informe</button></div>
    ${obs.length ? `<h3 style="margin:16px 0 4px">Observaciones de los ítems (${obs.length})</h3>
      <p class="muted">Lo que apuntaste junto a cada ítem en la agenda, redactado para la familia. Al crear o rehacer el borrador
        ya se incluyen en su área; aquí puedes añadirlas a un informe ya empezado.</p>
      ${obs.map((o, i) => `<div class="obs-informe" style="border-top:1px solid var(--borde, #ddd);padding-top:8px;margin-top:8px">
        <p style="margin:0"><strong>${esc(o.area)}</strong> · ${esc(o.texto)} <span class="chip">${esc(o.evaluacion || "sin evaluar")}</span></p>
        <ul class="lista-notas">${o.notas.map((n) => `<li><strong>${fechaCorta(n.fecha)}</strong> · ${esc(n.texto)}</li>`).join("")}</ul>
        <textarea rows="3" id="obs-red-${i}">${esc(o.redactada)}</textarea>
        <div class="fila" style="gap:8px;margin-top:6px;flex-wrap:wrap"><label class="muted">Añadir a:</label>
          <select id="obs-dest-${i}">${I.areas.map((a) => `<option value="${a.id}" ${normArea(a.area) === normArea(o.area) ? "selected" : ""}>${esc(a.area)}</option>`).join("")}</select>
          <button class="mini" data-usar-obs="${i}" ${I.areas.length ? "" : "disabled"}>＋ Añadir</button></div></div>`).join("")}` : ""}`;
  $$("[data-usar-obs]").forEach((b) => b.onclick = () => {
    const i = b.dataset.usarObs;
    const ta = $("#campo-area-" + $("#obs-dest-" + i).value);
    const txt = $("#obs-red-" + i).value.trim();
    if (!ta || !txt) return;
    ta.value = (ta.value.trim() ? ta.value.trim() + " " : "") + txt;
    ta.dispatchEvent(new Event("change"));
    ta.scrollIntoView({ behavior: "smooth", block: "center" });
    aviso("Observación añadida al área");
  });
  $("#usar-notas").onclick = () => {
    const ta = $("#campo-" + $("#destino-notas").value);
    const txt = $("#borrador-notas").value.trim();
    if (!ta || !txt) return;
    ta.value = (ta.value.trim() ? ta.value.trim() + "\n" : "") + txt;
    ta.dispatchEvent(new Event("change"));
    ta.scrollIntoView({ behavior: "smooth", block: "center" });
    aviso("Añadido al informe");
  };
}

// ======================================================================= mi trabajo PT/AL
let TRABAJO = null;            // categorías y tipos de cita
let FILTRO_TAREA = "";         // categoría elegida en el filtro de tareas
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const mesDe = (iso) => iso.slice(0, 7);
function sumarMeses(mes, n) {
  const [a, m] = mes.split("-").map(Number);
  const d = new Date(a, m - 1 + n, 1, 12);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function fechaLarga(iso) {
  const d = new Date(iso + "T12:00:00");
  return `${["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"][d.getDay()]} ${d.getDate()} de ${MESES[d.getMonth()]}`;
}
async function infoTrabajo() {
  if (!TRABAJO) {
    const r = await api("GET", "/api/trabajo/info");
    TRABAJO = { categorias: Object.fromEntries(r.categorias), tipos_cita: Object.fromEntries(r.tipos_cita) };
  }
  return TRABAJO;
}
const etiquetaCita = (c) => [c.hora_inicio, c.alumno || c.con_quien || (TRABAJO ? TRABAJO.tipos_cita[c.tipo] : "")].filter(Boolean).join(" · ");

// Vistas «mes», «semana» y «dia» del calendario de citas, con la lista de tareas al lado
async function vistaTrabajo(modo, fecha) {
  await infoTrabajo();
  if (!["dia", "semana", "mes"].includes(modo)) modo = leerPref("trabajo", "mes");
  guardarPref("trabajo", modo);
  const hoy = hoyISO();
  let desde, hasta, ref;  // ref: día de referencia para cambiar de vista
  if (modo === "mes") {
    const mes = fecha ? fecha.slice(0, 7) : mesDe(hoy);
    ref = mes === mesDe(hoy) ? hoy : `${mes}-01`;
  } else if (modo === "semana") {
    desde = lunesISO(fecha && fecha.length === 10 ? fecha : hoy);
    hasta = sumarDias(desde, 6);
    ref = hoy >= desde && hoy <= hasta ? hoy : desde;
  } else {
    desde = hasta = ref = fecha && fecha.length === 10 ? fecha : hoy;
  }
  const mes = mesDe(ref);
  const pCitas = modo === "mes" ? api("GET", `/api/citas?mes=${mes}`) : api("GET", `/api/citas?desde=${desde}&hasta=${hasta}`);
  const [tareas, cal, alumnos, ag, proximas, cals] = await Promise.all([
    api("GET", "/api/tareas"), pCitas, api("GET", "/api/alumnos"),
    modo === "mes" ? null : api("GET", `/api/agenda?desde=${desde}&hasta=${hasta}`),
    modo === "mes" ? api("GET", `/api/citas?desde=${hoy}&hasta=${sumarDias(hoy, 90)}`) : null,
    api("GET", "/api/calendarios").catch(() => [])]);
  const evs = cals.length ? await api("GET", `/api/eventos-externos?desde=${modo === "mes" ? cal.desde : desde}&hasta=${modo === "mes" ? cal.hasta : hasta}`).catch(() => []) : [];
  const recargar = () => vistaTrabajo(modo, modo === "mes" ? mes : (modo === "semana" ? desde : ref));

  // Cabecera del calendario: selector de vista, navegación y título
  const selector = selectorVista(modo, [["dia", "Día", `#/trabajo/dia/${ref}`],
    ["semana", "Semana", `#/trabajo/semana/${lunesISO(ref)}`], ["mes", "Mes", `#/trabajo/mes/${mes}`]]);
  const [a, m] = mes.split("-").map(Number);
  const nav = {
    mes: [`#/trabajo/mes/${sumarMeses(mes, -1)}`, `#/trabajo/mes/${mesDe(hoy)}`, `#/trabajo/mes/${sumarMeses(mes, 1)}`,
      `${mayus(MESES[m - 1])} ${a}`, "Mes"],
    semana: [`#/trabajo/semana/${sumarDias(desde || ref, -7)}`, `#/trabajo/semana/${lunesISO(hoy)}`,
      `#/trabajo/semana/${sumarDias(desde || ref, 7)}`, desde ? tituloSemana(desde, hasta) : "", "Semana"],
    dia: [`#/trabajo/dia/${sumarDias(ref, -1)}`, `#/trabajo/dia/${hoy}`, `#/trabajo/dia/${sumarDias(ref, 1)}`,
      mayus(fechaLarga(ref)) + (ref === hoy ? ' <span class="chip">hoy</span>' : ""), "Día"],
  }[modo];

  let cuerpo;
  if (modo === "mes") cuerpo = htmlMes(mes, cal, proximas, hoy, evs);
  else if (modo === "semana") cuerpo = htmlSemanaTrabajo(desde, cal.citas, ag.sesiones, tareas, hoy, evs);
  else cuerpo = htmlDiaTrabajo(ref, cal.citas, ag.sesiones, tareas, evs);

  vista.innerHTML = `
    <div class="cabecera"><div><h1>Mi trabajo PT/AL</h1>
      <p class="sub">Lo que haces fuera de las sesiones: material, pruebas, correos, tutorías y reuniones.</p></div></div>
    <div id="avisos-trabajo"></div>
    <div class="trabajo-grid modo-${modo}">
      <div class="tarjeta" id="tarjeta-tareas"></div>
      <div class="tarjeta" id="tarjeta-cal"><div class="cal-cab">
          ${selector}
          <div class="nav-fechas"><a class="boton mini" href="${nav[0]}" title="${nav[4]} anterior">◀</a>
            <a class="boton mini" href="${nav[1]}">Hoy</a>
            <a class="boton mini" href="${nav[2]}" title="${nav[4]} siguiente">▶</a></div>
          <h2>${nav[3]}</h2>
          <button class="primario mini" id="nueva-cita">＋ Nueva cita</button></div>
        <div class="leyenda">${Object.entries(TRABAJO.tipos_cita).map(([k, t]) => `<span class="cita ${k}">${esc(t)}</span>`).join("")}
          ${modo === "mes" ? "" : '<span class="sesion-leyenda">Sesiones con alumnos</span>'}</div>
        ${htmlEstadoCalendarios(cals)}
        ${cuerpo}</div>
    </div>`;
  pintarTareas(tareas, alumnos);
  pintarAvisos($("#avisos-trabajo"), false);
  const citas = [...cal.citas, ...((proximas && proximas.citas) || [])];
  enlazarCitasYTareas(citas, alumnos, recargar);
  enlazarEventos(evs);
  enlazarLeyendaCal(cals, recargar);
  if ($("#actualizar-cal")) $("#actualizar-cal").onclick = () => intentar(async () => {
    $("#actualizar-cal").disabled = true;
    const r = await actualizarCalendarios(0);
    const fallos = r.filter((x) => x.error);
    aviso(fallos.length ? fallos[0].error : "Calendario actualizado", fallos.length > 0);
    recargar();
  });
  // Mes: pulsar un día abre la vista Día; el «＋» de cada día crea una cita
  $$(".cal-dia[data-dia]").forEach((d) => d.onclick = (e) => {
    if (e.target.closest("[data-cita], [data-nueva], [data-evento]")) return;
    location.hash = `#/trabajo/dia/${d.dataset.dia}`;
  });
  // Semana: pulsar un hueco crea una cita a esa hora
  $$("[data-nueva]").forEach((b) => b.onclick = (e) => {
    if (e.target.closest("[data-cita], [data-evento]")) return;
    e.stopPropagation();
    dialogoCita({ fecha: b.dataset.nueva, hora_inicio: b.dataset.hora || "" }, alumnos, recargar);
  });
  $("#nueva-cita").onclick = () => dialogoCita({ fecha: modo === "semana" && !(hoy >= desde && hoy <= hasta) ? desde : ref },
    alumnos, recargar);
}

function tituloSemana(desde, hasta) {
  const d1 = new Date(desde + "T12:00:00"), d2 = new Date(hasta + "T12:00:00");
  const corto = (d) => MESES[d.getMonth()].slice(0, 3);
  return d1.getMonth() === d2.getMonth()
    ? `${d1.getDate()} – ${d2.getDate()} ${corto(d2)} ${d2.getFullYear()}`
    : `${d1.getDate()} ${corto(d1)} – ${d2.getDate()} ${corto(d2)} ${d2.getFullYear()}`;
}

function htmlMes(mes, cal, proximas, hoy, evs = []) {
  const pend = proximas.citas.filter((c) => !c.hecha);
  return `<div class="calendario">${["L", "M", "X", "J", "V", "S", "D"].map((d) => `<div class="cal-dia-nombre">${d}</div>`).join("")}
      ${diasCalendario(cal.desde, cal.hasta).map((f) => {
        const del = cal.citas.filter((c) => c.fecha === f);
        return `<div class="cal-dia ${mesDe(f) !== mes ? "otro-mes" : ""} ${f === hoy ? "hoy" : ""}" data-dia="${f}" title="Ver el ${fechaLarga(f)}">
          <div class="cal-dia-cab"><span class="num">${Number(f.slice(8))}</span>
            <button type="button" class="cal-mas" data-nueva="${f}" title="Nueva cita el ${fechaLarga(f)}">＋</button></div>
          ${eventosDelDia(evs, f).map(htmlEventoChip).join("")}
          ${del.map((c) => `<button type="button" class="cita ${c.tipo} ${c.hecha ? "hecha" : ""}" data-cita="${c.id}" title="${esc(TRABAJO.tipos_cita[c.tipo])}">${esc(etiquetaCita(c))}</button>`).join("")}</div>`;
      }).join("")}</div>
    <p class="muted" style="margin:6px 0 0;font-size:12px">Pulsa un día para verlo en detalle, o «＋» para añadir una cita.</p>
    <h3 style="margin:16px 0 6px">Próximas citas</h3>
    ${pend.length ? `<ul class="lista-citas">${pend.slice(0, 12).map((c) => `<li>
        <button type="button" class="cita ${c.tipo}" data-cita="${c.id}">${esc(TRABAJO.tipos_cita[c.tipo])}</button>
        <a href="#/trabajo/dia/${c.fecha}"><strong>${fechaLarga(c.fecha)}</strong></a>${c.hora_inicio ? ` · ${c.hora_inicio}${c.hora_fin ? "–" + c.hora_fin : ""}` : ""}
        ${c.alumno ? ` · ${esc(c.alumno)}` : ""}${c.con_quien ? ` · ${esc(c.con_quien)}` : ""}${c.lugar ? ` · <span class="muted">${esc(c.lugar)}</span>` : ""}</li>`).join("")}</ul>`
      : `<p class="muted">No tienes citas en los próximos tres meses.</p>`}`;
}

const NOMBRES_DIA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const horaDe = (h) => (h ? parseInt(h.slice(0, 2), 10) : null);

// Semana: rejilla por horas (para ver los huecos libres) y, en pantallas estrechas, lista por días
function htmlSemanaTrabajo(desde, citas, sesiones, tareas, hoy, evs = []) {
  const dias = [0, 1, 2, 3, 4, 5, 6].map((i) => sumarDias(desde, i));
  const conHora = evs.filter((e) => !e.todo_el_dia);
  const horas = [...citas.map((c) => horaDe(c.hora_inicio)), ...sesiones.map((s) => horaDe(s.inicio)),
    ...conHora.filter((e) => e.inicio.slice(0, 10) >= desde).map((e) => horaDe(horaEv(e)))].filter((h) => h !== null);
  const h0 = Math.min(8, ...horas), h1 = Math.max(17, ...horas);
  const rango = Array.from({ length: h1 - h0 + 1 }, (_, i) => h0 + i);
  const vencenEl = (f) => tareas.filter((t) => !t.hecha && t.fecha_limite === f);
  const sinHora = (f) => citas.filter((c) => c.fecha === f && !c.hora_inicio);
  const cabecera = dias.map((f, i) => `<a class="sem-cab ${f === hoy ? "hoy" : ""} ${i > 4 ? "finde" : ""}" href="#/trabajo/dia/${f}" title="Ver este día">
      <span>${NOMBRES_DIA[i].slice(0, 3)}</span><strong>${Number(f.slice(8))}</strong>
      ${vencenEl(f).length ? `<span class="sem-tareas" title="Tareas que vencen">📌 ${vencenEl(f).length}</span>` : ""}
      ${eventosDelDia(evs.filter((e) => e.todo_el_dia), f).map(htmlEventoChip).join("")}
      ${sinHora(f).map((c) => `<button type="button" class="cita ${c.tipo}" data-cita="${c.id}">${esc(etiquetaCita(c))}</button>`).join("")}</a>`).join("");
  const celda = (f, h, i) => {
    const hh = String(h).padStart(2, "0");
    const ses = sesiones.filter((s) => s.fecha === f && horaDe(s.inicio) === h);
    const cis = citas.filter((c) => c.fecha === f && horaDe(c.hora_inicio) === h);
    const exts = conHora.filter((e) => e.inicio.slice(0, 10) === f && horaDe(horaEv(e)) === h);
    return `<div class="sem-celda ${f === hoy ? "hoy" : ""} ${i > 4 ? "finde" : ""}" data-nueva="${f}" data-hora="${hh}:00" title="Nueva cita el ${fechaLarga(f)} a las ${hh}:00">
      ${ses.map((s) => `<span class="sesion-mini ${s.estado}" title="${esc(s.alumno)} · ${s.inicio}–${s.fin}">${s.inicio} ${esc(s.alumno.split(" ")[0])}</span>`).join("")}
      ${exts.map(htmlEventoChip).join("")}
      ${cis.map((c) => `<button type="button" class="cita ${c.tipo} ${c.hecha ? "hecha" : ""}" data-cita="${c.id}">${esc(etiquetaCita(c))}</button>`).join("")}</div>`;
  };
  const rejilla = `<div class="semana-rejilla"><div class="sem-esquina"></div>${cabecera}
    ${rango.map((h) => `<div class="sem-hora">${String(h).padStart(2, "0")}:00</div>${dias.map((f, i) => celda(f, h, i)).join("")}`).join("")}</div>`;
  const lista = `<div class="semana-lista">${dias.map((f, i) => {
      const ev = ordenarPorHora([...sesiones.filter((s) => s.fecha === f).map((s) => ({ hora: s.inicio, sesion: s })),
        ...citas.filter((c) => c.fecha === f).map((c) => ({ hora: c.hora_inicio, cita: c })),
        ...eventosDelDia(evs, f).map((e) => ({ hora: horaEv(e), externo: e }))]);
      return `<div class="sl-dia ${f === hoy ? "hoy" : ""}"><div class="sl-cab"><a href="#/trabajo/dia/${f}"><strong>${NOMBRES_DIA[i]} ${Number(f.slice(8))}</strong></a>
          ${vencenEl(f).length ? `<span class="sem-tareas">📌 ${vencenEl(f).length}</span>` : ""}
          <button type="button" class="mini" data-nueva="${f}">＋ Cita</button></div>
        ${ev.length ? ev.map(htmlEntrada).join("") : '<p class="muted sl-vacio">Libre 🌿</p>'}</div>`;
    }).join("")}</div>`;
  return `${rejilla}${lista}<p class="muted ayuda-rejilla" style="margin:6px 0 0;font-size:12px">Pulsa un hueco para añadir una cita a esa hora. En gris, tus sesiones con alumnos.</p>`;
}

const htmlEntrada = (e) => (e.sesion ? htmlSesionResumen(e.sesion) : e.cita ? htmlCitaTarjeta(e.cita) : htmlEventoTarjeta(e.externo));

function htmlSesionResumen(s) {
  const estado = s.falta ? "No vino" : s.estado === "cancelada" ? "Cancelada" : s.estado === "realizada" ? "Realizada" : "";
  return `<a class="sesion-resumen ${s.estado}" href="#/agenda/dia/${s.fecha}" title="Abrir en la agenda de sesiones">
    <span class="sr-hora">${s.inicio}–${s.fin}</span> <strong>${esc(s.alumno)}</strong> <span class="chip">${s.especialidad}</span>
    <span class="muted">${s.items.length} ${s.items.length === 1 ? "ítem" : "ítems"}</span>${estado ? ` <span class="chip ${s.falta ? "falta" : ""}">${estado}</span>` : ""}</a>`;
}

// Día: lista horaria con citas y sesiones, más las tareas que vencen ese día
function htmlDiaTrabajo(dia, citas, sesiones, tareas, evs = []) {
  const delDia = eventosDelDia(evs, dia);
  const ev = ordenarPorHora([...sesiones.map((s) => ({ hora: s.inicio, sesion: s })), ...citas.map((c) => ({ hora: c.hora_inicio, cita: c })),
    ...delDia.filter((e) => !e.todo_el_dia && e.inicio.slice(0, 10) === dia).map((e) => ({ hora: horaEv(e), externo: e }))]);
  const vencen = tareas.filter((t) => !t.hecha && t.fecha_limite === dia);
  return `${htmlFranjaTodoElDia(delDia)}${htmlTareasDelDia(vencen)}
    ${ev.length ? `<div class="linea-tiempo compacta">${ev.map((e) => `<div class="lt-fila"><div class="lt-hora">${e.hora || "—"}</div>
        <div class="lt-cont">${htmlEntrada(e)}</div></div>`).join("")}</div>`
      : `<div class="vacio">No tienes nada este día 🌿</div>`}
    ${sesiones.length ? `<p style="margin:10px 0 0"><a href="#/agenda/dia/${dia}">Abrir las sesiones de este día en la agenda →</a></p>` : ""}`;
}

// ======================================================================= calendarios externos (solo lectura)
async function actualizarCalendarios(minutos = 0) {
  if (!USUARIO) return [];
  return api("POST", `/api/calendarios/actualizar${minutos ? "?si_antiguo_min=" + minutos : ""}`).catch(() => []);
}
const colorCal = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#2B7BB9");
const eventosDelDia = (evs, f) => evs.filter((e) => e.inicio.slice(0, 10) <= f && e.fin.slice(0, 10) >= f);
const horaEv = (e) => (e.todo_el_dia ? "" : e.inicio.slice(11, 16));
function htmlEventoChip(e) {
  return `<button type="button" class="evento-ext" style="--ce:${colorCal(e.color)}" data-evento="${e.id}"
    title="${esc(e.calendario)}: ${esc(e.titulo)}">📅 ${horaEv(e) ? horaEv(e) + " " : ""}${esc(e.titulo)}</button>`;
}
function htmlEventoTarjeta(e) {
  const fin = e.todo_el_dia ? "" : e.fin.slice(11, 16);
  return `<button type="button" class="evento-tarjeta" style="--ce:${colorCal(e.color)}" data-evento="${e.id}">
    <span class="ct-tipo">📅 ${esc(e.titulo)}</span>
    <span class="ct-hora">${e.todo_el_dia ? "Todo el día" : horaEv(e) + (fin && fin !== horaEv(e) ? "–" + fin : "")} · ${esc(e.calendario)}</span>
    ${e.lugar ? `<span class="ct-lugar">📍 ${esc(e.lugar)}</span>` : ""}</button>`;
}
function htmlFranjaTodoElDia(evs) {
  const todos = evs.filter((e) => e.todo_el_dia);
  return todos.length ? `<div class="franja-todo-dia">${todos.map(htmlEventoChip).join("")}</div>` : "";
}
function dialogoEvento(e) {
  const fecha = (iso) => mayus(fechaLarga(iso.slice(0, 10)));
  const cuando = e.todo_el_dia
    ? (e.inicio === e.fin ? `${fecha(e.inicio)} · todo el día` : `Del ${fecha(e.inicio).toLowerCase()} al ${fecha(e.fin).toLowerCase()}`)
    : `${fecha(e.inicio)} · ${horaEv(e)}${e.fin.slice(11, 16) && e.fin !== e.inicio ? "–" + e.fin.slice(11, 16) : ""}`;
  dialogo.innerHTML = `<div class="dlg-cab" style="background:${colorCal(e.color)}"><h2>📅 ${esc(e.titulo)}</h2><button id="cerrar">Cerrar</button></div>
    <div class="dlg-cuerpo"><p><strong>${esc(cuando)}</strong></p>
      ${e.lugar ? `<p>📍 ${esc(e.lugar)}</p>` : ""}
      ${e.descripcion ? `<p style="white-space:pre-wrap">${esc(e.descripcion)}</p>` : ""}
      <p class="muted">Calendario «${esc(e.calendario)}». Es de solo lectura: para cambiarlo, hazlo en Google Calendar.</p></div>`;
  dialogo.showModal();
  $("#cerrar").onclick = () => dialogo.close();
}
function enlazarEventos(evs) {
  $$("[data-evento]").forEach((b) => b.onclick = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const e = evs.find((x) => String(x.id) === b.dataset.evento);
    if (e) dialogoEvento(e);
  });
}
function haceMinutos(iso) {
  if (!iso) return "nunca";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return min < 1 ? "ahora mismo" : min < 60 ? `hace ${min} min` : min < 1440 ? `hace ${Math.round(min / 60)} h` : `hace ${Math.round(min / 1440)} días`;
}
// Leyenda de calendarios externos: cada nombre es un botón que muestra u oculta ese calendario
function htmlEstadoCalendarios(cals) {
  if (!cals.length) return "";
  const conUrl = cals.filter((c) => c.origen === "url" && c.tiene_url);
  const ultima = conUrl.map((c) => c.actualizado).filter(Boolean).sort().pop();
  const error = cals.find((c) => c.error || c.falta_secreta);
  return `<div class="estado-cal">${cals.map((c) => `<button type="button" class="cal-nombre ${c.visible ? "" : "oculto"}"
      style="--ce:${colorCal(c.color)}" data-cal-ver="${c.id}" aria-pressed="${c.visible ? "true" : "false"}"
      title="${c.visible ? "Ocultar" : "Mostrar"} «${esc(c.nombre)}» (${c.tipo === "personal" ? "personal" : "del colegio"})">${c.visible ? "👁" : "🚫"} ${esc(c.nombre)}</button>`).join("")}
    ${conUrl.length ? `<span class="muted">Actualizado ${haceMinutos(ultima)}</span><button class="mini" id="actualizar-cal">↻ Actualizar</button>` : ""}
    ${error ? `<a class="error-cal" href="#/ajustes" title="${esc(error.error || "Falta la dirección secreta")}">⚠ ${esc(error.nombre)}: ${esc(error.error || "falta pegar de nuevo la dirección secreta")}</a>` : ""}</div>`;
}
function enlazarLeyendaCal(cals, recargar) {
  $$("[data-cal-ver]").forEach((b) => b.onclick = () => intentar(async () => {
    const c = cals.find((x) => String(x.id) === b.dataset.calVer);
    await api("PATCH", `/api/calendarios_externos/${b.dataset.calVer}`, { visible: c && c.visible ? 0 : 1 });
    recargar();
  }));
}

function diasCalendario(desde, hasta) {
  const dias = [];
  for (let f = desde; f <= hasta; f = sumarDias(f, 1)) dias.push(f);
  return dias;
}

function pintarTareas(tareas, alumnos) {
  const caja = $("#tarjeta-tareas");
  const cats = TRABAJO.categorias;
  const hoy = hoyISO();
  const pendientes = tareas.filter((t) => !t.hecha && (!FILTRO_TAREA || t.categoria === FILTRO_TAREA));
  const hechas = tareas.filter((t) => t.hecha);
  const fila = (t) => `<li class="tarea ${t.hecha ? "hecha" : ""} ${!t.hecha && t.fecha_limite && t.fecha_limite < hoy ? "vencida" : ""}">
      <input type="checkbox" data-tarea-hecha="${t.id}" ${t.hecha ? "checked" : ""} title="${t.hecha ? "Marcar como pendiente" : "Marcar como hecha"}">
      <div class="tarea-texto">${esc(t.texto)}
        <div class="tarea-meta"><span class="cat ${t.categoria}">${esc(cats[t.categoria] || t.categoria)}</span>
          ${t.alumno ? `<span class="muted">👧 ${esc(t.alumno)}</span>` : ""}
          ${t.cita_id ? `<a href="#/reunion/${t.cita_id}" class="enlace-reunion">🤝 ${esc(TRABAJO.tipos_cita[t.cita_tipo] || "Reunión")} · ${fechaCorta(t.cita_fecha)}</a>` : ""}
          ${t.fecha_limite ? `<span class="fecha-limite">📅 ${t.fecha_limite === hoy ? "hoy" : fechaCorta(t.fecha_limite)}${!t.hecha && t.fecha_limite < hoy ? " · vencida" : ""}</span>` : ""}</div></div>
      <button class="icono" data-tarea-borrar="${t.id}" title="Borrar tarea">✕</button></li>`;
  caja.innerHTML = `<h2>Tareas pendientes</h2>
    <div class="nueva-tarea">
      <div class="fila" style="gap:6px"><input id="t-texto" placeholder="Nueva tarea: preparar material, pasar prueba, enviar correo…" style="flex:1">${botonMicro("t-texto")}</div>
      <div class="fila" style="gap:6px;flex-wrap:wrap;margin-top:6px">
        <select id="t-cat">${Object.entries(cats).map(([k, t]) => `<option value="${k}" ${k === FILTRO_TAREA ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
        <select id="t-alumno"><option value="">Sin alumno</option>${alumnos.map((al) => `<option value="${al.id}">${esc(al.nombre)}</option>`).join("")}</select>
        <input type="date" id="t-fecha" title="Fecha límite (opcional)">
        <button class="primario" id="t-anadir">＋ Añadir</button></div></div>
    <div class="filtros"><button class="mini ${FILTRO_TAREA ? "" : "activo"}" data-filtro="">Todas</button>
      ${Object.entries(cats).map(([k, t]) => `<button class="mini cat ${k} ${FILTRO_TAREA === k ? "activo" : ""}" data-filtro="${k}">${esc(t)}</button>`).join("")}</div>
    ${pendientes.length ? `<ul class="lista-tareas">${pendientes.map(fila).join("")}</ul>`
      : `<div class="vacio" style="padding:16px">${FILTRO_TAREA ? "No hay tareas pendientes de esta categoría." : "¡Nada pendiente! 🎉"}</div>`}
    ${hechas.length ? `<details class="hechas"><summary>Hechas (${hechas.length})</summary>
      <ul class="lista-tareas">${hechas.map(fila).join("")}</ul>
      <button class="mini peligro" id="borrar-hechas">Borrar las hechas</button></details>` : ""}`;
  enlazarMicros(caja);
  const recargar = async () => pintarTareas(await api("GET", "/api/tareas"), alumnos);
  const anadir = () => intentar(async () => {
    const texto = $("#t-texto").value.trim();
    if (!texto) { $("#t-texto").focus(); return; }
    await api("POST", "/api/tareas", { texto, categoria: $("#t-cat").value, alumno_id: $("#t-alumno").value || null,
      fecha_limite: $("#t-fecha").value || null });
    await recargar();
    $("#t-texto").focus();
  });
  $("#t-anadir").onclick = anadir;
  $("#t-texto").onkeydown = (e) => { if (e.key === "Enter") anadir(); };
  $$("[data-filtro]", caja).forEach((b) => b.onclick = () => { FILTRO_TAREA = b.dataset.filtro; recargar(); });
  $$("[data-tarea-hecha]", caja).forEach((c) => c.onchange = () => intentar(async () => {
    await api("PATCH", `/api/tareas/${c.dataset.tareaHecha}`, { hecha: c.checked });
    if (c.checked) aviso("¡Tarea hecha! ✔");
    await recargar();
    pintarAvisos($("#avisos-trabajo"), false);
  }));
  $$("[data-tarea-borrar]", caja).forEach((b) => b.onclick = () => intentar(async () => {
    if (!confirm("¿Borrar esta tarea?")) return;
    await api("DELETE", `/api/tareas/${b.dataset.tareaBorrar}`);
    await recargar();
  }));
  const bh = $("#borrar-hechas");
  if (bh) bh.onclick = () => intentar(async () => {
    if (!confirm(`¿Borrar las ${hechas.length} tareas hechas? No se puede deshacer.`)) return;
    await api("POST", "/api/tareas/borrar-hechas");
    await recargar();
  });
}

async function dialogoCita(c, alumnos, alGuardar) {
  await infoTrabajo();
  const nueva = !c.id;
  const v = { hora_inicio: "", hora_fin: "", tipo: "tutoria_familia", alumno_id: "", con_quien: "", lugar: "", notas: "", hecha: 0, ...c };
  dialogo.innerHTML = `
    <div class="dlg-cab"><h2>${nueva ? "Nueva cita" : "Cita"}</h2><button id="cerrar">Cerrar</button></div>
    <div class="dlg-cuerpo"><div class="campos">
      <div><label>Fecha</label><input type="date" id="c-fecha" value="${esc(v.fecha)}"></div>
      <div><label>Tipo</label><select id="c-tipo">${Object.entries(TRABAJO.tipos_cita).map(([k, t]) => `<option value="${k}" ${k === v.tipo ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
      <div><label>Hora de inicio</label><input type="time" id="c-ini" value="${esc(v.hora_inicio)}"></div>
      <div><label>Hora de fin (opcional)</label><input type="time" id="c-fin" value="${esc(v.hora_fin || "")}"></div>
      <div><label>Alumno (opcional)</label><select id="c-alumno"><option value="">Sin alumno</option>
        ${alumnos.map((al) => `<option value="${al.id}" ${String(al.id) === String(v.alumno_id) ? "selected" : ""}>${esc(al.nombre)}</option>`).join("")}</select></div>
      <div><label>Con quién</label><input id="c-quien" value="${esc(v.con_quien)}" placeholder="Madre y padre, logopeda, psicóloga…"></div>
      <div class="campo-ancho"><label>Lugar</label><input id="c-lugar" value="${esc(v.lugar)}" placeholder="Aula de PT, videollamada…"></div>
      <div class="campo-ancho"><label>Notas</label><div class="fila" style="gap:6px;align-items:flex-start">
        <textarea id="c-notas" rows="3" style="flex:1" placeholder="Temas a tratar, acuerdos…">${esc(v.notas)}</textarea>${botonMicro("c-notas")}</div></div>
      ${nueva ? "" : `<div class="campo-ancho"><label class="fila" style="gap:6px"><input type="checkbox" id="c-hecha" ${v.hecha ? "checked" : ""}> Ya se ha hecho</label></div>`}
    </div></div>
    <div class="dlg-pie">${nueva ? "" : `<button class="peligro" id="c-borrar">Borrar</button>
      <button id="c-abrir" title="Tomar notas y pasar líneas a tareas">📝 Notas y tareas</button>`}
      <button id="c-cancelar">Cancelar</button><button class="primario" id="c-guardar">Guardar</button></div>`;
  dialogo.showModal();
  enlazarMicros(dialogo);
  const cerrar = async () => { await pararMicro(); dialogo.close(); };
  $("#cerrar").onclick = cerrar;
  $("#c-cancelar").onclick = cerrar;
  dialogo.oncancel = (e) => { e.preventDefault(); cerrar(); };
  $("#c-guardar").onclick = () => intentar(async () => {
    const datos = { fecha: $("#c-fecha").value, tipo: $("#c-tipo").value, hora_inicio: $("#c-ini").value,
      hora_fin: $("#c-fin").value, alumno_id: $("#c-alumno").value || null, con_quien: $("#c-quien").value,
      lugar: $("#c-lugar").value, notas: $("#c-notas").value };
    if (!nueva) datos.hecha = $("#c-hecha").checked;
    if (nueva) await api("POST", "/api/citas", datos); else await api("PATCH", `/api/citas/${v.id}`, datos);
    await cerrar();
    aviso(nueva ? "Cita guardada" : "Cita actualizada");
    alGuardar && alGuardar();
  });
  if (!nueva) $("#c-abrir").onclick = async () => { await cerrar(); location.hash = `#/reunion/${v.id}`; };
  if (!nueva) $("#c-borrar").onclick = () => intentar(async () => {
    if (!confirm("¿Borrar esta cita?")) return;
    await api("DELETE", `/api/citas/${v.id}`);
    await cerrar();
    alGuardar && alGuardar();
  });
}

// Aviso de citas de hoy y mañana y de tareas vencidas (en Mi trabajo y en la agenda de sesiones)
async function pintarAvisos(caja, conEnlace = true) {
  if (!caja) return;
  const av = await api("GET", "/api/avisos").catch(() => null);
  if (!av || !caja.isConnected) return;
  await infoTrabajo();
  const items = [
    ...av.citas.map((c) => `<li>${c.fecha === av.hoy ? "<strong>Hoy</strong>" : "Mañana"}${c.hora_inicio ? " a las " + c.hora_inicio : ""}:
      ${esc(TRABAJO.tipos_cita[c.tipo])}${c.alumno ? " · " + esc(c.alumno) : ""}${c.con_quien ? " · " + esc(c.con_quien) : ""}</li>`),
    ...av.tareas_vencidas.map((t) => `<li class="vencida">Tarea ${t.fecha_limite === av.hoy ? "para hoy" : "vencida (" + fechaCorta(t.fecha_limite) + ")"}: ${esc(t.texto)}</li>`)];
  caja.innerHTML = items.length ? `<div class="aviso-trabajo">🔔 <ul>${items.join("")}</ul>
    ${conEnlace ? `<a href="#/trabajo">Ver mi trabajo PT/AL</a>` : ""}</div>` : "";
}

// ======================================================================= reuniones (notas → tareas pendientes)
// Cada reunión es una cita de Mi trabajo con sus notas. Se escribe una idea por línea y
// cualquier línea pasa a tareas pendientes con un clic o con Ctrl + Enter.
let FILTRO_REUNION = "";
const BOTONES_REUNION = [["tutoria_familia", "👪 Familia"], ["reunion_orientacion", "🧭 Orientación"],
  ["reunion_profesores", "👩‍🏫 Profesores"], ["reunion_terapeutas", "🩺 Terapeutas"], ["otra", "＋ Otra"]];
const normLinea = (s) => (s || "").replace(/^\s*(?:[-*•·▪◦→>]+|\d{1,2}[.)]|\[\s?[xX]?\s?\]|☐|☑)\s*/, "").trim();
const claveLinea = (s) => normLinea(s).toLowerCase().replace(/\s+/g, " ");
function horaAhora() { const d = new Date(); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; }

async function nuevaReunion(tipo, extra = {}) {
  const r = await api("POST", "/api/citas", { fecha: hoyISO(), hora_inicio: horaAhora(), tipo, ...extra });
  location.hash = `#/reunion/${r.id}`;
}

function htmlFilaReunion(r) {
  const primera = (r.notas || "").split("\n").map(normLinea).find(Boolean) || "";
  return `<a class="reunion-fila ${r.hecha ? "hecha" : ""}" href="#/reunion/${r.id}">
    <span class="rf-fecha">${fechaCorta(r.fecha)}<small>${r.hora_inicio || ""}</small></span>
    <span class="rf-cuerpo"><span class="cita ${r.tipo}">${esc(TRABAJO.tipos_cita[r.tipo] || r.tipo)}</span>
      <strong>${esc([r.alumno, r.con_quien].filter(Boolean).join(" · "))}</strong>
      <span class="rf-notas">${esc(primera) || '<span class="muted">Sin notas</span>'}</span></span>
    ${r.tareas_pendientes ? `<span class="chip pendientes">📌 ${r.tareas_pendientes} pendiente${r.tareas_pendientes > 1 ? "s" : ""}</span>`
      : r.tareas_total ? `<span class="chip">✔ Tareas hechas</span>` : ""}</a>`;
}

// Lista de tareas (de una reunión o de todas): tic, fecha límite, borrar y enlace a su reunión
function htmlListaTareasReunion(tareas, conReunion) {
  const hoy = hoyISO();
  if (!tareas.length) return `<div class="vacio" style="padding:16px">${conReunion ? "¡Nada pendiente de tus reuniones! 🎉"
    : "Todavía no hay tareas. Pasa líneas de las notas con ➕ o con Ctrl + Enter."}</div>`;
  return `<ul class="lista-tareas">${tareas.map((t) => `<li class="tarea ${t.hecha ? "hecha" : ""} ${!t.hecha && t.fecha_limite && t.fecha_limite < hoy ? "vencida" : ""}">
    <input type="checkbox" data-rt-hecha="${t.id}" ${t.hecha ? "checked" : ""} title="${t.hecha ? "Marcar como pendiente" : "Marcar como hecha"}">
    <div class="tarea-texto">${esc(t.texto)}
      <div class="tarea-meta">${t.alumno ? `<span class="muted">👧 ${esc(t.alumno)}</span>` : ""}
        ${conReunion && t.cita_id ? `<a href="#/reunion/${t.cita_id}" class="enlace-reunion">🤝 ${esc(TRABAJO.tipos_cita[t.cita_tipo] || "Reunión")} · ${fechaCorta(t.cita_fecha)}</a>` : ""}
        <label class="fecha-limite" title="Fecha límite (opcional)">📅 <input type="date" data-rt-fecha="${t.id}" value="${esc(t.fecha_limite || "")}"></label></div></div>
    <button class="icono" data-rt-borrar="${t.id}" title="Borrar tarea">✕</button></li>`).join("")}</ul>`;
}
function enlazarTareasReunion(raiz, recargar) {
  $$("[data-rt-hecha]", raiz).forEach((c) => c.onchange = () => intentar(async () => {
    await api("PATCH", `/api/tareas/${c.dataset.rtHecha}`, { hecha: c.checked });
    if (c.checked) aviso("¡Tarea hecha! ✔");
    await recargar();
  }));
  $$("[data-rt-fecha]", raiz).forEach((i) => i.onchange = () => intentar(async () => {
    await api("PATCH", `/api/tareas/${i.dataset.rtFecha}`, { fecha_limite: i.value || null });
    aviso(i.value ? "Fecha límite guardada" : "Fecha límite quitada");
    await recargar();
  }));
  $$("[data-rt-borrar]", raiz).forEach((b) => b.onclick = () => intentar(async () => {
    if (!confirm("¿Borrar esta tarea?")) return;
    await api("DELETE", `/api/tareas/${b.dataset.rtBorrar}`);
    await recargar();
  }));
}

async function vistaReuniones() {
  await infoTrabajo();
  const [lista, alumnos] = await Promise.all([
    api("GET", `/api/reuniones${FILTRO_REUNION ? "?tipo=" + FILTRO_REUNION : ""}`), api("GET", "/api/alumnos")]);
  const hoy = hoyISO();
  const proximas = lista.filter((r) => r.fecha > hoy).reverse();
  const deHoy = lista.filter((r) => r.fecha === hoy).reverse();
  const pasadas = lista.filter((r) => r.fecha < hoy);
  const bloque = (titulo, rs) => rs.length ? `<h3 class="rf-titulo">${titulo}</h3><div class="lista-reuniones">${rs.map(htmlFilaReunion).join("")}</div>` : "";
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Reuniones</h1>
      <p class="sub">Toma notas en la reunión y pasa cada cosa que tengas que hacer a tareas pendientes.</p></div></div>
    <div class="tarjeta nueva-reunion"><h2>Empezar una reunión ahora</h2>
      <div class="fila" style="gap:8px;flex-wrap:wrap">
        ${BOTONES_REUNION.map(([k, t]) => `<button class="${k === "otra" ? "" : "primario"}" data-nueva-reunion="${k}">${t}</button>`).join("")}
        <select id="nr-alumno" style="width:auto"><option value="">Sin alumno</option>${alumnos.map((al) => `<option value="${al.id}">${esc(al.nombre)}</option>`).join("")}</select></div>
      <p class="muted" style="margin:8px 0 0">Se crea con la fecha y la hora de ahora y aparece también en el calendario de Mi trabajo PT/AL.
        Para una reunión futura, créala y cambia la fecha.</p></div>
    <div class="trabajo-grid">
      <div class="tarjeta"><h2>Tareas pendientes de reuniones</h2><div id="rt-todas"></div>
        <p class="muted" style="margin:10px 0 0">Todas tus tareas (también las que no salen de reuniones) están en <a href="#/trabajo">Mi trabajo PT/AL</a>.</p></div>
      <div class="tarjeta"><div class="filtros"><button class="mini ${FILTRO_REUNION ? "" : "activo"}" data-filtro-reunion="">Todas</button>
          ${Object.entries(TRABAJO.tipos_cita).map(([k, t]) => `<button class="mini ${FILTRO_REUNION === k ? "activo" : ""}" data-filtro-reunion="${k}">${esc(t)}</button>`).join("")}</div>
        ${lista.length ? bloque("Hoy", deHoy) + bloque("Próximas", proximas) + bloque("Anteriores", pasadas)
          : `<div class="vacio">${FILTRO_REUNION ? "No hay reuniones de este tipo." : "Todavía no hay reuniones. Pulsa uno de los botones de arriba para empezar."}</div>`}</div>
    </div>`;
  const pintarPendientes = async () => {
    const tareas = (await api("GET", "/api/tareas")).filter((t) => t.cita_id && !t.hecha);
    $("#rt-todas").innerHTML = htmlListaTareasReunion(tareas, true);
    enlazarTareasReunion($("#rt-todas"), pintarPendientes);
  };
  await pintarPendientes();
  $$("[data-nueva-reunion]").forEach((b) => b.onclick = () => intentar(() =>
    nuevaReunion(b.dataset.nuevaReunion, { alumno_id: $("#nr-alumno").value || null })));
  $$("[data-filtro-reunion]").forEach((b) => b.onclick = () => { FILTRO_REUNION = b.dataset.filtroReunion; vistaReuniones(); });
}

// Guardado de las notas mientras se escribe (y antes de salir de la pantalla)
let GUARDAR_NOTAS = null;
window.addEventListener("hashchange", () => { if (GUARDAR_NOTAS) GUARDAR_NOTAS(); });

async function vistaReunion(id) {
  await infoTrabajo();
  const [r, alumnos] = await Promise.all([api("GET", `/api/reuniones/${id}`), api("GET", "/api/alumnos")]);
  let tareas = r.tareas;
  vista.innerHTML = `
    <div class="migas"><a href="#/reuniones">Reuniones</a> › ${fechaCorta(r.fecha)}/${r.fecha.slice(0, 4)}</div>
    <div class="cabecera"><div><h1 id="r-titulo"></h1><p class="sub" id="r-sub"></p></div>
      <div class="acciones"><label class="fila" style="gap:6px;font-size:14px;color:var(--texto);margin:0">
          <input type="checkbox" id="r-hecha" style="width:auto" ${r.hecha ? "checked" : ""}> Reunión terminada</label>
        <button class="peligro" id="r-borrar">Borrar reunión</button></div></div>
    <details class="tarjeta reunion-datos" ${r.alumno_id || r.con_quien ? "" : "open"}><summary><strong>Datos de la reunión</strong>
        <span class="muted">(fecha, tipo, alumno, con quién…)</span></summary>
      <div class="campos" style="margin-top:12px">
        <div><label>Fecha</label><input type="date" data-r="fecha" value="${esc(r.fecha)}"></div>
        <div><label>Hora de inicio</label><input type="time" data-r="hora_inicio" value="${esc(r.hora_inicio)}"></div>
        <div><label>Hora de fin</label><input type="time" data-r="hora_fin" value="${esc(r.hora_fin || "")}"></div>
        <div><label>Tipo</label><select data-r="tipo">${Object.entries(TRABAJO.tipos_cita).map(([k, t]) => `<option value="${k}" ${k === r.tipo ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
        <div><label>Alumno (opcional)</label><select data-r="alumno_id"><option value="">Sin alumno</option>
          ${alumnos.map((al) => `<option value="${al.id}" ${al.id === r.alumno_id ? "selected" : ""}>${esc(al.nombre)}</option>`).join("")}</select></div>
        <div><label>Con quién</label><input data-r="con_quien" value="${esc(r.con_quien)}" placeholder="Familia, orientadora, tutora…"></div>
        <div><label>Lugar</label><input data-r="lugar" value="${esc(r.lugar)}" placeholder="Aula de PT, videollamada…"></div>
      </div></details>
    <div class="reunion-grid">
      <div class="tarjeta"><div class="fila" style="gap:10px;margin-bottom:8px"><h2 style="margin:0">Notas</h2><span class="muted" id="r-estado"></span>
          <span style="margin-left:auto">${botonMicro("r-notas")}</span></div>
        <p class="ayuda">Escribe una idea por línea. Para pasar a tareas la línea en la que estás, pulsa <code>Ctrl</code> + <code>Enter</code>,
          o usa el botón <strong>➕ Tarea</strong> de cada línea. El micrófono 🎤 escribe en una línea nueva.</p>
        <textarea id="r-notas" data-micro-lineas rows="14" placeholder="- La familia cuenta que…&#10;- Acordamos…&#10;- Pedir informe a…">${esc(r.notas)}</textarea>
        <h3 class="rf-titulo">Líneas de las notas</h3><ul class="lineas-reunion" id="r-lineas"></ul></div>
      <div class="tarjeta"><h2>Tareas de esta reunión</h2>
        <div class="fila" style="gap:6px;margin-bottom:8px"><input id="rt-texto" placeholder="Otra tarea que no esté en las notas…" style="flex:1">
          <button class="primario" id="rt-anadir">＋ Añadir</button></div>
        <div id="rt-lista"></div>
        <p class="muted" style="margin:10px 0 0">Aparecen también en <a href="#/trabajo">Mi trabajo PT/AL</a>, con el resto de tareas.</p></div>
    </div>`;
  enlazarMicros(vista);
  const ta = $("#r-notas");
  const ajustar = () => { ta.style.height = "auto"; ta.style.height = Math.max(260, ta.scrollHeight + 2) + "px"; };
  requestAnimationFrame(ajustar);

  const pintarCabecera = () => {
    $("#r-titulo").textContent = TRABAJO.tipos_cita[r.tipo] || "Reunión";
    const al = alumnos.find((x) => x.id === r.alumno_id);
    $("#r-sub").textContent = [mayus(fechaLarga(r.fecha)) + (r.hora_inicio ? ", " + r.hora_inicio : ""),
      al && al.nombre, r.con_quien].filter(Boolean).join(" · ");
  };
  let pintado = null;  // texto y tareas con los que se pintó la lista de líneas
  const pintarLineas = (forzar = false) => {
    const clave = ta.value + "\u0000" + tareas.map((t) => t.texto).join("\u0000");
    // Al salir del cuadro (evento change) no se repinta si nada cambió: así el clic en «➕ Tarea» no se pierde
    if (!forzar && clave === pintado) return;
    pintado = clave;
    const hechas = new Set(tareas.map((t) => claveLinea(t.texto)));
    const lineas = ta.value.split("\n").map((l, i) => [i, l]).filter(([, l]) => normLinea(l));
    $("#r-lineas").innerHTML = lineas.length ? lineas.map(([i, l]) => {
      const ya = hechas.has(claveLinea(l));
      return `<li class="${ya ? "ya-tarea" : ""}"><span>${esc(normLinea(l))}</span>${ya ? `<span class="chip">✔ Es tarea</span>`
        : `<button class="mini" data-linea="${i}" title="Pasar esta línea a tareas pendientes">➕ Tarea</button>`}</li>`;
    }).join("") : `<li class="muted">Aquí aparecerá cada línea que escribas, con su botón para pasarla a tareas.</li>`;
    $$("[data-linea]").forEach((b) => b.onclick = () => intentar(() => lineaATarea(Number(b.dataset.linea))));
  };
  const pintarTareasReunion = () => {
    $("#rt-lista").innerHTML = htmlListaTareasReunion(tareas, false);
    enlazarTareasReunion($("#rt-lista"), recargarTareas);
  };
  const recargarTareas = async () => {
    tareas = (await api("GET", `/api/reuniones/${id}`)).tareas;
    pintarTareasReunion();
    pintarLineas();
  };

  // Guardado automático de las notas
  let temporizador = null, guardado = r.notas;
  const guardarNotas = async () => {
    clearTimeout(temporizador);
    if (ta.value === guardado) return;
    const valor = ta.value;
    await api("PATCH", `/api/citas/${id}`, { notas: valor });
    guardado = valor;
    if ($("#r-estado") && ta.isConnected) $("#r-estado").textContent = "Guardado ✔";
  };
  GUARDAR_NOTAS = () => { if (ta.value !== guardado) guardarNotas().catch(() => aviso("No se han podido guardar las notas", true)); GUARDAR_NOTAS = null; };
  ta.oninput = () => {
    ajustar();
    $("#r-estado").textContent = "Guardando…";
    clearTimeout(temporizador);
    temporizador = setTimeout(() => intentar(guardarNotas), 800);
    pintarLineas();
  };
  ta.onchange = () => { ajustar(); pintarLineas(); intentar(guardarNotas); };

  // Pasa la línea «i» de las notas a tareas y la marca con ☑ en el texto
  const lineaATarea = async (i) => {
    const lineas = ta.value.split("\n");
    const texto = normLinea(lineas[i]);
    if (!texto) { aviso("Esa línea está vacía"); return; }
    if (tareas.some((t) => claveLinea(t.texto) === claveLinea(texto))) { aviso("Esa línea ya es una tarea"); return; }
    await api("POST", `/api/reuniones/${id}/tareas`, { texto });
    lineas[i] = "☑ " + texto;
    const pos = ta.selectionStart;
    const antes = ta.value.length;
    ta.value = lineas.join("\n");
    ajustar();
    ta.selectionStart = ta.selectionEnd = Math.max(0, pos + ta.value.length - antes);
    aviso("Pasada a tareas pendientes ✔");
    await guardarNotas();
    await recargarTareas();
  };
  ta.onkeydown = (e) => {
    if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const pos = ta.selectionStart;
    const i = ta.value.slice(0, pos).split("\n").length - 1;
    intentar(async () => {
      await lineaATarea(i);
      // Si estaba al final de la línea, sigue escribiendo en una nueva
      const v = ta.value, p = ta.selectionStart;
      const fin = v.indexOf("\n", p);
      if (fin === -1) { ta.value = v + "\n"; ta.selectionStart = ta.selectionEnd = ta.value.length; }
      else if (v.slice(p, fin).trim() === "") { ta.selectionStart = ta.selectionEnd = fin + 1; }
      ta.focus();
    });
  };

  // Datos de la reunión
  $$("[data-r]").forEach((el) => el.onchange = () => intentar(async () => {
    const campo = el.dataset.r;
    const valor = campo === "alumno_id" ? (el.value ? Number(el.value) : null) : el.value;
    await api("PATCH", `/api/citas/${id}`, { [campo]: valor });
    r[campo] = valor;
    pintarCabecera();
    aviso("Guardado");
  }));
  $("#r-hecha").onchange = () => intentar(async () => {
    await api("PATCH", `/api/citas/${id}`, { hecha: $("#r-hecha").checked });
    aviso($("#r-hecha").checked ? "Reunión marcada como terminada" : "Reunión marcada como pendiente");
  });
  $("#r-borrar").onclick = () => intentar(async () => {
    const msg = tareas.length ? `¿Borrar esta reunión y sus notas? Sus ${tareas.length} tareas se quedan en Mi trabajo PT/AL.`
      : "¿Borrar esta reunión y sus notas?";
    if (!confirm(msg)) return;
    GUARDAR_NOTAS = null;
    await api("DELETE", `/api/citas/${id}`);
    location.hash = "#/reuniones";
  });
  const anadir = () => intentar(async () => {
    const texto = $("#rt-texto").value.trim();
    if (!texto) { $("#rt-texto").focus(); return; }
    await api("POST", `/api/reuniones/${id}/tareas`, { texto });
    $("#rt-texto").value = "";
    await recargarTareas();
    $("#rt-texto").focus();
  });
  $("#rt-anadir").onclick = anadir;
  $("#rt-texto").onkeydown = (e) => { if (e.key === "Enter") anadir(); };

  pintarCabecera();
  pintarTareasReunion();
  pintarLineas();
  if (!r.notas) ta.focus();
}

// ======================================================================= crear material
const NOMBRE_ACT = { letra: "Letra grande", repasar: "Repasar", rodear: "Rodear", unir: "Unir con flechas", completar: "Completar",
  contar: "Contar", clasificar: "Clasificar", secuencia: "Secuencia", tarjetas: "Tarjetas", pregunta: "Pregunta", cuento: "Cuento" };
let PROPUESTA = null;  // { spec, origen, tipo, alumno_id }
let GOOGLE = {};  // estado de la conexión con Google Drive

// Qué hacer con la respuesta de «crear» o «abrir» (Google Drive, a mano o Word/PowerPoint)
function trasAbrirMaterial(r) {
  if (r.sincronizado) aviso(`Copiado a tu Google Drive (${GOOGLE.carpeta || "material mundo pt al"}). En unos segundos aparece en Chrome: haz doble clic para abrirlo con Documentos o Presentaciones de Google.`);
  else if (r.manual) aviso("Se ha abierto Google Drive en Chrome y la carpeta del archivo: arrastra el archivo a la ventana de Drive y ábrelo con doble clic.");
  else if (r.abierto === false && r.ruta) aviso("Está en " + r.ruta);
}

// Espera a que Claude Desktop cree el material (aparece en la tabla «materiales») y lo abre
let ESPERA_CLAUDE = null;
function esperarMaterialClaude(ultimoId) {
  if (ESPERA_CLAUDE) clearInterval(ESPERA_CLAUDE);
  const inicio = Date.now();
  ESPERA_CLAUDE = setInterval(async () => {
    if (Date.now() - inicio > 15 * 60 * 1000) { clearInterval(ESPERA_CLAUDE); ESPERA_CLAUDE = null; pintarEsperaClaude(false); return; }
    const lista = await api("GET", "/api/materiales").catch(() => null);
    const nuevo = lista && lista.find((m) => m.id > ultimoId);
    if (!nuevo) return;
    clearInterval(ESPERA_CLAUDE);
    ESPERA_CLAUDE = null;
    aviso("✨ Claude ha creado: " + nuevo.titulo);
    if (location.hash.startsWith("#/material")) vistaMaterial();
    trasAbrirMaterial(await api("POST", `/api/materiales/${nuevo.id}/abrir`).catch(() => ({})));
  }, 4000);
  pintarEsperaClaude(true);
}
function pintarEsperaClaude(esperando) {
  const e = $("#cd-estado");
  if (e) e.innerHTML = esperando ? " ⏳ Claude Desktop está preparando el material. Cuando lo cree aparecerá abajo y se abrirá solo." : "";
}

async function vistaMaterial() {
  const [info, alumnos, lista, google] = await Promise.all([api("GET", "/api/material/info"), api("GET", "/api/alumnos"), api("GET", "/api/materiales"),
    api("GET", "/api/google/estado").catch(() => ({}))]);
  GOOGLE = google;
  const tipos = info.tipos;
  const opcAlumnos = `<option value="">Ninguno</option>${alumnos.map((a) => `<option value="${a.id}">${esc(a.nombre)}</option>`).join("")}`;
  const comunes = (p) => `<div class="campos material-campos">
      <div><label>Alumno (opcional)</label><select id="${p}-alumno">${opcAlumnos}</select></div>
      <div><label>Nivel</label><select id="${p}-nivel"><option value="3">3 años</option><option value="4" selected>4 años</option><option value="5">5 años</option></select></div>
      <div><label>Formato</label><select id="${p}-formato"><option value="docx">Word · fichas para imprimir</option><option value="pptx">PowerPoint · para proyectar</option></select></div>
      <div><label>Nº de fichas o diapositivas</label><input type="number" id="${p}-num" min="1" max="${p === "ia" ? 20 : 40}" placeholder="${p === "ia" ? "6" : "Todas"}" value="${p === "ia" ? 6 : ""}"></div></div>`;
  const cd = info.claude_desktop;
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Crear material</h1>
      <p class="sub">Fichas para imprimir o diapositivas para proyectar, con el logo del colegio y pictogramas de ARASAAC.</p></div></div>
    <div class="material-grid">
      <div>
        ${cd ? `<div class="tarjeta tarjeta-ia"><h2>✨ Pídeselo a Claude</h2>
          <p class="muted" style="margin-top:0">Describe el material con todo el detalle que quieras. Se abre Claude Desktop con tu petición ya escrita: pulsa Enviar y Claude lo creará con el estilo del colegio.</p>
          <label>¿Qué material quieres?</label>
          <div class="fila" style="gap:6px;align-items:flex-start"><textarea id="cd-peticion" rows="4" style="flex:1"
            placeholder="Por ejemplo: «6 fichas para trabajar el fonema /r/ en posición inicial con dibujos de animales: una de unir, una de rodear y una de completar»"></textarea>${botonMicro("cd-peticion")}</div>
          ${comunes("cd")}
          <div id="sugerencias-cd" class="sugerencias"></div>
          <p class="nota-privacidad">🔒 Si eliges un alumno, se envían sus objetivos pendientes, nunca su nombre.</p>
          <p style="margin:10px 0 0"><button class="primario" id="cd-enviar">✨ Pedírselo a Claude</button><span class="muted" id="cd-estado"></span></p></div>` : ""}
        <${cd ? "details" : "div"} class="tarjeta">${cd ? "<summary><strong>📋 Plantillas (sin Internet)</strong></summary>" : "<h2>📋 Plantillas (gratis y sin Internet)</h2>"}
          <div class="campos material-campos">
            <div><label>Tipo de material</label><select id="pl-tipo">${tipos.map(([k, t]) => `<option value="${k}">${esc(t.nombre)}</option>`).join("")}</select></div>
            <div class="campo-ancho"><label>Contenido</label><input id="pl-contenido" placeholder="${esc(tipos[0][1].ejemplo)}">
              <p class="muted" id="pl-ayuda" style="margin:3px 0 0;font-size:12px">${esc(tipos[0][1].ayuda)}</p></div></div>
          ${comunes("pl")}
          <div id="sugerencias-pl" class="sugerencias"></div>
          <p style="margin:10px 0 0"><button class="primario" id="pl-preparar">👀 Ver propuesta</button></p>
          ${cd ? "" : `<p class="nota-amable">💬 Para pedir material más detallado, configura Claude Desktop en Ajustes › Usar con Claude Desktop.</p>`}</${cd ? "details" : "div"}>
        ${info.clave ? `<details class="tarjeta tarjeta-ia avanzadas"><summary>Opciones avanzadas</summary><h2>✨ Pídeselo a Claude</h2>
          <p class="nota-privacidad">🔒 Para crear el material se envía tu petición a Claude por Internet. No se envían nombres ni datos de tus alumnos.</p>
          <label>¿Qué material quieres?</label>
          <div class="fila" style="gap:6px;align-items:flex-start"><textarea id="ia-peticion" rows="3" style="flex:1"
            placeholder="Por ejemplo: «fichas para trabajar las vocales con animales» o «un cuento corto para trabajar la rutina de lavarse las manos»"></textarea>${botonMicro("ia-peticion")}</div>
          ${comunes("ia")}
          <div id="sugerencias-ia" class="sugerencias"></div>
          <p style="margin:10px 0 0"><button class="primario" id="ia-preparar">✨ Preparar propuesta</button>
            <span class="muted" id="ia-estado"></span></p></details>` : ""}
      </div>
      <div>
        <div class="tarjeta" id="tarjeta-propuesta"><h2>Vista previa</h2>
          <div class="vacio">Elige una plantilla y pulsa «Ver propuesta»: aquí verás sus páginas antes de crear el archivo.</div></div>
        <div class="tarjeta"><h2>Material creado</h2>
          ${lista.length ? `<ul class="lista-material">${lista.map((m) => `<li>
              <span class="formato ${m.formato}">${m.formato === "pptx" ? "PPT" : "DOC"}</span>
              <div class="lm-texto"><strong>${esc(m.titulo)}</strong>
                <span class="muted">${esc((m.creado || "").slice(0, 10))} · ${m.paginas} ${m.formato === "pptx" ? "diapositivas" : "fichas"}${m.origen === "ia" || m.origen === "claude_desktop" ? " · ✨ Claude" : ""}${m.alumno ? " · " + esc(m.alumno) : ""}${m.existe ? "" : " · ⚠ archivo movido o borrado"}</span></div>
              ${m.existe ? `<button class="mini" data-abrir-material="${m.id}">${GOOGLE.abrir_con === "local" ? "Abrir" : "Abrir en Google"}</button>` : ""}
              ${m.existe && GOOGLE.abrir_con === "local" ? `<button class="mini" data-drive-material="${m.id}" title="Subir a Google Drive y abrir con Documentos o Presentaciones de Google">☁ Drive</button>` : ""}
              ${m.existe ? `<a class="boton mini" href="/api/materiales/${m.id}/archivo">Descargar</a>` : ""}
              <button class="icono" data-quitar-material="${m.id}" title="Quitar de la lista (el archivo no se borra)">✕</button></li>`).join("")}</ul>`
            : `<div class="vacio" style="padding:16px">Todavía no has creado material.</div>`}
          <p class="muted" style="margin:8px 0 0;font-size:12px">Se guarda en: ${esc(info.carpeta)}${google.abrir_con !== "local"
            ? ` · <a href="#" id="abrir-carpeta-drive">Abrir mi carpeta de Drive</a>` : ""}</p></div>
      </div>
    </div>`;
  enlazarMicros(vista);
  const datos = (p) => ({ alumno_id: $(`#${p}-alumno`).value || null, nivel: $(`#${p}-nivel`).value, formato: $(`#${p}-formato`).value,
    num: Number($(`#${p}-num`).value) || null });
  $("#pl-tipo").onchange = () => {
    const t = Object.fromEntries(tipos)[$("#pl-tipo").value];
    $("#pl-contenido").placeholder = t.ejemplo;
    $("#pl-ayuda").textContent = t.ayuda;
  };
  for (const p of ["pl", ...(info.clave ? ["ia"] : []), ...(cd ? ["cd"] : [])]) {
    $(`#${p}-alumno`).onchange = async () => {
      const caja = $(`#sugerencias-${p}`);
      const id = $(`#${p}-alumno`).value;
      if (!id) { caja.innerHTML = ""; return; }
      const sug = await api("GET", `/api/material/sugerencias?alumno_id=${id}`).catch(() => []);
      caja.innerHTML = sug.length ? `<span class="muted">Según su ACI:</span> ${sug.map((s, i) =>
        `<button class="mini sugerencia" data-sug="${i}" title="${esc(s.motivo)}">${esc(Object.fromEntries(tipos)[s.tipo].nombre)}${s.contenido ? ": " + esc(s.contenido) : ""}</button>`).join("")}` : "";
      $$("[data-sug]", caja).forEach((b) => b.onclick = () => {
        const s = sug[Number(b.dataset.sug)];
        if (p === "pl") { $("#pl-tipo").value = s.tipo; $("#pl-tipo").onchange(); $("#pl-contenido").value = s.contenido; }
        else $(`#${p}-peticion`).value = `Material para trabajar: ${s.motivo.toLowerCase()}`;
      });
    };
  }
  $("#pl-preparar").onclick = () => intentar(async () => {
    const d = datos("pl");
    const r = await api("POST", "/api/material/propuesta", { modo: "plantilla", tipo: $("#pl-tipo").value, contenido: $("#pl-contenido").value, ...d });
    PROPUESTA = { ...r, tipo: $("#pl-tipo").value, ...d };
    pintarPropuesta();
  });
  if (info.clave) $("#ia-preparar").onclick = () => intentar(async () => {
    const b = $("#ia-preparar");
    b.disabled = true;
    $("#ia-estado").textContent = " Claude está preparando el material… (puede tardar un minuto)";
    try {
      const d = datos("ia");
      const r = await api("POST", "/api/material/propuesta", { modo: "ia", peticion: $("#ia-peticion").value, ...d });
      PROPUESTA = { ...r, tipo: "ia", ...d };
      if (r.anonimizados.length) aviso(`Se han quitado los nombres de la petición antes de enviarla (${r.anonimizados.join(", ")} → «el alumno»).`);
      pintarPropuesta();
    } finally { b.disabled = false; $("#ia-estado").textContent = ""; }
  });
  if (cd) $("#cd-enviar").onclick = () => intentar(async () => {
    const peticion = $("#cd-peticion").value.trim();
    if (!peticion) { $("#cd-peticion").focus(); return; }
    const r = await api("POST", "/api/material/claude-desktop", { peticion, ...datos("cd") });
    try { await navigator.clipboard.writeText(r.texto); } catch (e) { /* ya lo copia la aplicación */ }
    if (r.anonimizados.length) aviso(`Se han quitado los nombres de la petición (${r.anonimizados.join(", ")} → «el alumno»).`);
    aviso(r.abierto ? "Se ha abierto Claude Desktop con tu petición escrita: revisa y pulsa Enviar. Si no aparece el texto, pégalo con Ctrl+V."
      : "Abre Claude Desktop y pega la petición con Ctrl+V (ya está copiada).");
    esperarMaterialClaude(r.ultimo_id);
  });
  if (ESPERA_CLAUDE) pintarEsperaClaude(true);
  $$("[data-abrir-material]").forEach((b) => b.onclick = () => intentar(async () => {
    b.disabled = true;
    try { trasAbrirMaterial(await api("POST", `/api/materiales/${b.dataset.abrirMaterial}/abrir`)); }
    finally { b.disabled = false; }
  }));
  $$("[data-drive-material]").forEach((b) => b.onclick = () => intentar(async () => {
    b.disabled = true;
    try { trasAbrirMaterial(await api("POST", `/api/materiales/${b.dataset.driveMaterial}/drive`)); }
    finally { b.disabled = false; }
  }));
  if ($("#abrir-carpeta-drive")) $("#abrir-carpeta-drive").onclick = (e) => { e.preventDefault(); intentar(() => api("POST", "/api/google/abrir-carpeta")); };
  $$("[data-quitar-material]").forEach((b) => b.onclick = () => intentar(async () => {
    if (!confirm("¿Quitar este material de la lista? El archivo se queda en la carpeta.")) return;
    await api("DELETE", `/api/materiales/${b.dataset.quitarMaterial}`);
    vistaMaterial();
  }));
  if (PROPUESTA) pintarPropuesta();
}

function pintarPropuesta() {
  const caja = $("#tarjeta-propuesta");
  if (!caja || !PROPUESTA) return;
  const s = PROPUESTA.spec;
  const textoEl = (e) => [e.pictograma && e.pictograma !== e.texto ? `🖼 ${e.pictograma}` : "", e.texto, e.pareja ? `→ ${e.pareja}` : "",
    e.cantidad ? `×${e.cantidad}` : "", e.grupo ? `[${e.grupo}]` : "", e.correcto ? "✔" : ""].filter(Boolean).join(" ");
  caja.innerHTML = `<h2>Vista previa ${PROPUESTA.origen === "ia" ? '<span class="chip">✨ Claude</span>' : '<span class="chip">Plantilla</span>'}</h2>
    <h3 style="margin:0 0 2px">${esc(s.titulo)}</h3>
    <p class="muted" style="margin:0 0 6px">${esc(s.objetivo)}</p>
    ${s.instrucciones_maestra ? `<details><summary class="muted">Ideas para usarlo</summary><p>${esc(s.instrucciones_maestra)}</p></details>` : ""}
    <ol class="paginas-previa">${s.paginas.map((p) => `<li><span class="chip">${esc(NOMBRE_ACT[p.actividad] || p.actividad)}</span>
        <strong>${esc(p.enunciado)}</strong>${p.destacado ? ` <span class="destacado">${esc(p.destacado)}</span>` : ""}
        ${p.elementos.length ? `<div class="muted el-previa">${p.elementos.slice(0, 10).map((e) => esc(textoEl(e))).join(" · ")}${p.elementos.length > 10 ? " …" : ""}</div>` : ""}</li>`).join("")}</ol>
    <div class="fila" style="gap:8px;flex-wrap:wrap;margin-top:10px">
      <button class="primario" data-crear="docx">📄 Crear Word</button><button class="primario" data-crear="pptx">📊 Crear PowerPoint</button>
      <button id="descartar-propuesta">Descartar</button></div>
    <p class="muted" style="font-size:12px;margin:6px 0 0">${GOOGLE.abrir_con === "local" ? "El archivo se guarda y se abre con Word o PowerPoint. Después puedes retocarlo allí."
      : GOOGLE.mi_unidad ? "El archivo se guarda en el ordenador y en tu Google Drive, y se abre la carpeta en Chrome para abrirlo con Documentos o Presentaciones de Google."
      : "El archivo se guarda en el ordenador y se abre Google Drive en Chrome para que lo arrastres allí y lo abras con Documentos o Presentaciones de Google."}</p>`;
  $$("[data-crear]", caja).forEach((b) => b.onclick = () => intentar(async () => {
    b.disabled = true;
    const txt = b.textContent;
    b.textContent = "Creando…";
    try {
      const r = await api("POST", "/api/material/crear", { spec: s, formato: b.dataset.crear, alumno_id: PROPUESTA.alumno_id,
        origen: PROPUESTA.origen, tipo: PROPUESTA.tipo, abrir: true });
      aviso("Material guardado: " + r.nombre);
      trasAbrirMaterial(r);
      vistaMaterial();
    } finally { b.disabled = false; b.textContent = txt; }
  }));
  $("#descartar-propuesta").onclick = () => { PROPUESTA = null; vistaMaterial(); };
}

// ======================================================================= ajustes
async function pintarAjustesMaterial() {
  const caja = $("#ajustes-material");
  if (!USUARIO) { caja.innerHTML = "<h2>Crear material con Claude</h2><p class='muted'>Elige primero tu perfil.</p>"; return; }
  const info = await api("GET", "/api/material/info").catch(() => null);
  if (!info || !caja.isConnected) return;
  caja.innerHTML = `<h2>Crear material</h2>
    <h3 style="margin:0 0 6px">Cómo salen las fichas</h3>
    <label class="fila" style="gap:6px"><input type="checkbox" id="pictos-arasaac" ${info.pictos ? "checked" : ""} style="width:auto"> Usar pictogramas de ARASAAC (gratis; se descargan de Internet la primera vez y se guardan en Documentos › Mundo PT-AL › Pictogramas)</label>
    <div class="campos" style="margin-top:10px"><div class="campo-ancho"><label>Texto de la cabecera</label>
      <input id="cabecera-fichas" value="${esc(info.cabecera)}" placeholder="Tu nombre"></div></div>
    <p class="muted" style="font-size:12px;margin:3px 0 10px">Sale arriba a la derecha en cada ficha, seguido de «PT/AL».</p>
    <p>Logo de las fichas: ${info.logo_propio ? "<strong>tu logo</strong>" : "logo del colegio"}
      <label class="boton" for="logo-fichas">🖼 Cambiar logo</label><input type="file" id="logo-fichas" accept=".png,.jpg,.jpeg" hidden>
      ${info.logo_propio ? '<button id="logo-original">Volver al logo del colegio</button>' : ""}</p>
    <details class="avanzadas" ${info.clave ? "open" : ""}><summary>Opciones avanzadas</summary>
    <p class="nota-privacidad">Opcional y de pago: crear material con Claude por Internet. Se envía solo tu petición, sin nombres ni datos de tus alumnos. Sin clave, la aplicación no se conecta a Claude ni cobra nada.</p>
    <p>Clave de Claude: ${info.clave ? "<strong>✅ configurada</strong> (guardada en el Administrador de credenciales de Windows)" : "<strong>sin configurar</strong>"}</p>
    <div class="fila" style="gap:6px;flex-wrap:wrap"><input type="password" id="clave-claude" placeholder="Pega aquí tu clave (sk-ant-…)" style="flex:1;min-width:240px" autocomplete="off">
      <button class="primario" id="guardar-clave">Guardar</button><button id="probar-clave" ${info.clave ? "" : "disabled"}>Probar</button>
      ${info.clave ? '<button class="peligro" id="borrar-clave">Quitar clave</button>' : ""}</div>
    <details style="margin-top:8px"><summary>¿Cómo consigo la clave? (3 pasos)</summary><ol>
      <li>Entra en <strong>platform.claude.com</strong> y crea una cuenta (o inicia sesión).</li>
      <li>En <strong>Billing</strong>, añade saldo (por ejemplo 5 €; cada material cuesta unos céntimos).</li>
      <li>En <strong>API Keys › Create Key</strong>, crea una clave, cópiala y pégala aquí.</li></ol>
      <p class="muted">La clave no se guarda en la base de datos de la aplicación ni se comparte: queda en el Administrador de credenciales de Windows de este ordenador.</p></details>
    </details>`;
  const recargar = () => pintarAjustesMaterial();
  $("#guardar-clave").onclick = () => intentar(async () => {
    const clave = $("#clave-claude").value.trim();
    if (!clave) { $("#clave-claude").focus(); return; }
    await api("POST", "/api/material/clave", { clave });
    $("#clave-claude").value = "";
    aviso("Clave guardada");
    recargar();
  });
  $("#probar-clave").onclick = () => intentar(async () => {
    const r = await api("POST", "/api/material/clave/probar");
    aviso(`✅ La clave funciona (${r.modelo})`);
  });
  if ($("#borrar-clave")) $("#borrar-clave").onclick = () => intentar(async () => {
    if (!confirm("¿Quitar la clave de Claude de este ordenador?")) return;
    await api("DELETE", "/api/material/clave");
    recargar();
  });
  $("#pictos-arasaac").onchange = (e) => intentar(() => api("POST", "/api/material/ajustes", { pictos: e.target.checked }));
  $("#cabecera-fichas").onchange = (e) => intentar(async () => { await api("POST", "/api/material/ajustes", { cabecera: e.target.value }); aviso("Cabecera guardada"); });
  $("#logo-fichas").onchange = (e) => intentar(async () => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("archivo", f);
    await api("POST", "/api/material/logo", fd);
    aviso("Logo guardado");
    recargar();
  });
  if ($("#logo-original")) $("#logo-original").onclick = () => intentar(async () => { await api("DELETE", "/api/material/logo"); recargar(); });
}

// Google Drive sin cuentas ni claves: Drive para ordenadores o arrastrar el archivo a Drive en Chrome
async function pintarAjustesGoogle() {
  const caja = $("#ajustes-google");
  if (!caja) return;
  if (!USUARIO) { caja.innerHTML = "<h2>Google Drive</h2><p class='muted'>Elige primero tu perfil.</p>"; return; }
  const g = await api("GET", "/api/google/estado").catch(() => null);
  if (!g || !caja.isConnected) return;
  caja.innerHTML = `<h2>Google Drive</h2>
    <p class="muted" style="margin-top:0">Para ordenadores sin Word ni PowerPoint: el material se abre con <strong>Documentos</strong> o <strong>Presentaciones de Google</strong> desde tu carpeta de Drive «${esc(g.carpeta)}».</p>
    <h3 style="margin:0 0 6px">Al crear o abrir material</h3>
    <label class="fila" style="gap:6px"><input type="radio" name="abrir-con" value="drive" ${g.abrir_con !== "local" ? "checked" : ""} style="width:auto"> Abrir con Google Drive en ${g.chrome ? "Chrome" : "el navegador"}</label>
    <label class="fila" style="gap:6px"><input type="radio" name="abrir-con" value="local" ${g.abrir_con === "local" ? "checked" : ""} style="width:auto"> Abrir con Word o PowerPoint de este ordenador</label>
    <h3 style="margin:14px 0 6px">Tu carpeta de Drive</h3>
    <div class="campos"><div class="campo-ancho"><label>Enlace de la carpeta (opcional)</label>
      <input id="g-carpeta-url" value="${esc(g.carpeta_url)}" placeholder="https://drive.google.com/drive/folders/…"></div></div>
    <p class="muted" style="font-size:12px;margin:3px 0 10px">Abre la carpeta «${esc(g.carpeta)}» en Drive, copia la dirección de Chrome y pégala aquí: así «Abrir en Google» va directo a ella. Sin enlace se abre Mi unidad.</p>
    <p>${g.mi_unidad ? `✅ Google Drive para ordenadores: <code>${esc(g.mi_unidad)}</code>. El material se copia solo a «${esc(g.carpeta)}» y Drive lo sube.`
      : "Google Drive para ordenadores no está instalado: al abrir un material se abre Drive en Chrome y la carpeta del archivo para que lo arrastres. Si lo instalas (google.com/drive/download), se subirá solo."}</p>
    <details class="avanzadas"><summary>Opciones avanzadas</summary>
      <div class="campos"><div class="campo-ancho"><label>Carpeta «Mi unidad» en este ordenador (si no se detecta sola)</label>
        <input id="g-mi-unidad" value="${esc(g.mi_unidad_manual)}" placeholder="G:\\Mi unidad"></div></div></details>`;
  $$("[name=abrir-con]", caja).forEach((r) => r.onchange = () => intentar(async () => {
    await api("POST", "/api/google/ajustes", { abrir_con: r.value });
    aviso("Guardado");
  }));
  $("#g-carpeta-url").onchange = (e) => intentar(async () => { await api("POST", "/api/google/ajustes", { carpeta_url: e.target.value }); aviso("Carpeta guardada"); });
  $("#g-mi-unidad").onchange = (e) => intentar(async () => { await api("POST", "/api/google/ajustes", { mi_unidad: e.target.value }); pintarAjustesGoogle(); });
}

const COLORES_CAL = ["#7FB3D5", "#F1948A", "#82E0AA", "#F8C471", "#BB8FCE", "#76D7C4", "#F0B27A", "#AEB6BF"];

async function pintarAjustesCalendario() {
  const caja = $("#ajustes-calendario");
  if (!USUARIO) { caja.innerHTML = "<h2>Google Calendar</h2><p class='muted'>Elige primero tu perfil.</p>"; return; }
  const cals = await api("GET", "/api/calendarios").catch(() => null);
  if (!cals || !caja.isConnected) return;
  const color = COLORES_CAL[cals.length % COLORES_CAL.length];
  caja.innerHTML = `<h2>Google Calendar</h2>
    <p class="muted" style="margin-top:0">Ves tus calendarios (el del colegio, el tuyo…) dentro de «Mi trabajo PT/AL» y en la agenda del día. Solo se leen: nada de lo que creas en la aplicación va a Google.</p>
    ${cals.length ? `<ul class="lista-calendarios">${cals.map((c) => `<li>
        <input type="checkbox" ${c.visible ? "checked" : ""} data-cal-visible="${c.id}" title="Mostrar en Mi trabajo y en la agenda">
        <input type="color" value="${colorCal(c.color)}" data-cal-color="${c.id}" title="Color">
        <input value="${esc(c.nombre)}" data-cal-nombre="${c.id}" style="flex:1;min-width:120px">
        <select data-cal-tipo="${c.id}" title="Tipo"><option value="colegio" ${c.tipo !== "personal" ? "selected" : ""}>Colegio</option>
          <option value="personal" ${c.tipo === "personal" ? "selected" : ""}>Personal</option></select>
        <span class="muted">${c.eventos} eventos · ${c.origen === "url" ? (c.secreta ? "🔒 dirección secreta" : "🌐 público") + " · actualizado " + haceMinutos(c.actualizado) : "importado de archivo"}</span>
        ${c.error ? `<span class="error-cal">⚠ ${esc(c.error)}</span>` : ""}
        ${c.falta_secreta ? `<span class="error-cal">⚠ Falta la dirección secreta (no viaja al pasar los datos de ordenador). Pégala de nuevo:</span>
          <input type="password" data-cal-nueva-url="${c.id}" placeholder="https://calendar.google.com/calendar/ical/…/private-…/basic.ics" autocomplete="off" style="flex:2;min-width:200px">
          <button class="mini primario" data-cal-guardar-url="${c.id}">Guardar</button>` : ""}
        ${c.origen === "url" && c.tiene_url ? `<button class="mini" data-cal-probar="${c.id}">Probar</button>` : ""}
        ${c.origen === "archivo" ? `<label class="boton mini" for="reimp-${c.id}">Volver a importar</label><input type="file" id="reimp-${c.id}" data-cal-reimportar="${c.id}" accept=".ics" hidden>` : ""}
        <button class="mini peligro" data-cal-quitar="${c.id}">Quitar</button></li>`).join("")}</ul>` : ""}
    <h3 style="margin:14px 0 6px">Añadir un calendario</h3>
    <div class="campos">
      <div><label>Nombre</label><input id="cal-nombre" placeholder="Calendario del colegio"></div>
      <div><label>Color</label><input type="color" id="cal-color" value="${color}" style="height:36px"></div>
      <div><label>Tipo</label><select id="cal-tipo"><option value="colegio">Del colegio</option><option value="personal">Personal</option></select></div>
      <div class="campo-ancho"><label>Enlace del calendario</label>
        <input id="cal-url" placeholder="Enlace «Insertar», ID del calendario o dirección iCal (.ics)" autocomplete="off" spellcheck="false"></div></div>
    <p class="muted" id="cal-previa" style="margin:4px 0 0;font-size:12px"></p>
    <p style="margin:6px 0 0"><label style="font-weight:400"><input type="checkbox" id="cal-guardar-falla" style="width:auto;display:inline;margin:0 4px 0 0;vertical-align:middle">Guardarlo aunque ahora no se pueda leer (se sincronizará cuando Google lo permita)</label></p>
    <p style="margin:8px 0 0"><button class="primario" id="cal-anadir">Añadir</button>
      <span class="muted">o</span> <label class="boton" for="cal-archivo">📄 Importar archivo .ics</label><input type="file" id="cal-archivo" accept=".ics" hidden></p>
    <details style="margin-top:10px"><summary>¿Qué enlace pego?</summary><ol>
      <li>Abre Google Calendar en el ordenador (calendar.google.com).</li>
      <li>A la izquierda, pasa el ratón por el calendario › ⋮ › <strong>Configuración y uso compartido</strong>.</li>
      <li>En <strong>Integrar el calendario</strong> sirve cualquiera de estas: el <strong>ID de calendario</strong>, la <strong>URL pública</strong> o el código de <strong>Insertar</strong> (solo si el calendario es público), o la <strong>Dirección secreta en formato iCal</strong> (funciona aunque no sea público).</li></ol>
      <p class="muted">🌐 Si es público, la dirección se guarda con tus datos y viaja con ellos al exportarlos. 🔒 La dirección secreta es como una contraseña: se guarda en el Administrador de credenciales de Windows, no se exporta y en otro ordenador hay que pegarla de nuevo. Si no ves ninguna (las cuentas del colegio a veces lo impiden), usa «Importar archivo .ics»: Configuración › Importar y exportar › Exportar.</p></details>`;
  const recargar = () => pintarAjustesCalendario();
  $("#cal-anadir").onclick = () => intentar(async () => {
    const url = $("#cal-url").value.trim();
    if (!url) { $("#cal-url").focus(); return; }
    $("#cal-anadir").disabled = true;
    try {
      const r = await api("POST", "/api/calendarios", { nombre: $("#cal-nombre").value, color: $("#cal-color").value, url,
        tipo: $("#cal-tipo").value, guardar_si_falla: $("#cal-guardar-falla").checked });
      const n = r.calendarios.length, total = r.calendarios.reduce((a, x) => a + x.eventos, 0);
      if (r.error) aviso(`Guardado, pero aún no se puede leer: ${r.error}`, true);
      else aviso(`${n > 1 ? n + " calendarios añadidos" : "Calendario añadido"} (${total} eventos)`);
      recargar();
    } finally { if ($("#cal-anadir")) $("#cal-anadir").disabled = false; }
  });
  const subir = (archivo, extra) => intentar(async () => {
    const fd = new FormData();
    fd.append("archivo", archivo);
    Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
    const r = await api("POST", "/api/calendarios/importar", fd);
    aviso(`Importados ${r.eventos} eventos`);
    recargar();
  });
  $("#cal-archivo").onchange = (e) => e.target.files[0] && subir(e.target.files[0], { nombre: $("#cal-nombre").value || e.target.files[0].name.replace(/\.ics$/i, ""), color: $("#cal-color").value });
  $$("[data-cal-reimportar]").forEach((i) => i.onchange = (e) => e.target.files[0] && subir(e.target.files[0], { calendario_id: i.dataset.calReimportar }));
  $$("[data-cal-probar]").forEach((b) => b.onclick = () => intentar(async () => {
    const r = await api("POST", `/api/calendarios/${b.dataset.calProbar}/probar`);
    aviso(`✅ Funciona: ${r.eventos} eventos`);
    await actualizarCalendarios(0);
    recargar();
  }));
  $$("[data-cal-quitar]").forEach((b) => b.onclick = () => intentar(async () => {
    if (!confirm("¿Quitar este calendario de la aplicación? (En Google no se borra nada)")) return;
    await api("DELETE", `/api/calendarios/${b.dataset.calQuitar}`);
    recargar();
  }));
  $$("[data-cal-nombre]").forEach((i) => i.onchange = () => intentar(() => api("PATCH", `/api/calendarios_externos/${i.dataset.calNombre}`, { nombre: i.value })));
  $$("[data-cal-color]").forEach((i) => i.onchange = () => intentar(() => api("PATCH", `/api/calendarios_externos/${i.dataset.calColor}`, { color: i.value })));
  $$("[data-cal-tipo]").forEach((i) => i.onchange = () => intentar(() => api("PATCH", `/api/calendarios_externos/${i.dataset.calTipo}`, { tipo: i.value })));
  $$("[data-cal-visible]").forEach((i) => i.onchange = () => intentar(() => api("PATCH", `/api/calendarios_externos/${i.dataset.calVisible}`, { visible: i.checked ? 1 : 0 })));
  $$("[data-cal-guardar-url]").forEach((b) => b.onclick = () => intentar(async () => {
    const campo = $(`[data-cal-nueva-url="${b.dataset.calGuardarUrl}"]`);
    if (!campo.value.trim()) { campo.focus(); return; }
    const r = await api("PUT", `/api/calendarios/${b.dataset.calGuardarUrl}/url`, { url: campo.value.trim() });
    aviso(`Dirección guardada (${r.eventos} eventos)`);
    recargar();
  }));
  // Vista previa: qué calendario se va a añadir y si es público o secreto
  let espera;
  $("#cal-url").oninput = () => {
    clearTimeout(espera);
    const v = $("#cal-url").value.trim();
    $("#cal-previa").textContent = "";
    if (!v) return;
    espera = setTimeout(() => api("POST", "/api/calendarios/normalizar", { url: v }).then((fs) => {
      $("#cal-previa").textContent = fs.map((f) => (f.secreta
        ? "🔒 Dirección secreta: se guardará en el Administrador de credenciales y no se exportará."
        : "🌐 Público: " + decodeURIComponent(f.url.split("/ical/")[1].split("/")[0]))).join(" · ");
    }).catch((e) => { $("#cal-previa").textContent = "⚠ " + (e.message || e); }), 400);
  };
}

// Servidor MCP local: Claude Desktop (con la suscripción Pro) crea material sin clave de la API
async function pintarAjustesClaudeDesktop() {
  const caja = $("#ajustes-claude-desktop");
  const e = await api("GET", "/api/claude-desktop").catch(() => null);
  if (!e || !caja.isConnected) return;
  caja.innerHTML = `<h2>Usar con Claude Desktop</h2>
    <p class="muted" style="margin-top:0">Con la aplicación Claude Desktop y tu suscripción (Pro), puedes pedirle a Claude material
      («Hazme 6 fichas de vocales con animales para 4 años en Word») y lo crea con el estilo del colegio en tu carpeta de material, sin clave de la API.</p>
    <p>${e.configurado ? (e.al_dia ? "✅ Claude Desktop ya está configurado." : "⚠️ Claude Desktop está configurado con otra ruta: pulsa el botón para actualizarla.")
      : e.carpeta_claude ? "Claude Desktop está instalado pero aún no conoce Mundo PT-AL." : "No encuentro Claude Desktop en este ordenador. Instálalo desde claude.ai/download e inicia sesión."}</p>
    <p><button class="primario" id="cd-configurar">⚙ Configurar Claude Desktop</button>
      <button id="cd-copiar">📋 Copiar configuración</button></p>
    <ol class="muted" style="margin:6px 0">
      <li>Instala Claude Desktop e inicia sesión con tu cuenta Pro.</li>
      <li>Pulsa «Configurar Claude Desktop» (se guarda antes una copia de su configuración).</li>
      <li>Cierra Claude Desktop del todo (también desde el icono junto al reloj) y vuelve a abrirlo.</li>
      <li>Pídele el material. La primera vez te preguntará si permite usar «mundo-ptal».</li></ol>
    <label style="font-weight:400"><input type="checkbox" id="cd-alumnos" ${e.alumnos ? "checked" : ""} style="width:auto;display:inline;margin:0 4px 0 0;vertical-align:middle">
      Dejar que Claude vea los objetivos pendientes de las ACIs (solo como «Alumno 1», «Alumno 2»…, nunca nombres)</label>
    <details style="margin-top:10px"><summary>Configurarlo a mano</summary>
      <p class="muted">Añade esto dentro de <code>${esc(e.ruta)}</code> (si ya hay un bloque <code>mcpServers</code>, añade solo la entrada «mundo-ptal»):</p>
      <pre class="codigo" id="cd-json">${esc(e.fragmento)}</pre></details>`;
  $("#cd-configurar").onclick = () => intentar(async () => {
    const r = await api("POST", "/api/claude-desktop/configurar");
    aviso("Listo. Reinicia Claude Desktop" + (r.copia ? " (copia de su configuración: " + r.copia + ")" : ""));
    pintarAjustesClaudeDesktop();
  });
  $("#cd-copiar").onclick = () => intentar(async () => {
    await navigator.clipboard.writeText(e.fragmento);
    aviso("Configuración copiada");
  });
  $("#cd-alumnos").onchange = (ev) => intentar(() => api("POST", "/api/claude-desktop/ajustes", { alumnos: ev.target.checked }));
}

async function vistaAjustes() {
  const voz = await api("GET", "/api/voz");
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Ajustes</h1><p class="sub">${esc(INFO.app)} ${esc(INFO.version)} · ${esc(INFO.colegio)}</p></div></div>
    <div class="tarjeta"><h2>Tus datos</h2>
      <p>Toda la información se guarda únicamente en este ordenador, en la carpeta:</p>
      <p><code>${esc(INFO.datos)}</code></p>
      <p><button class="primario" id="copia">💾 Hacer copia de seguridad ahora</button></p>
      <p class="muted">Las copias se guardan en la subcarpeta «copias». Puedes llevarlas a un pendrive para no perder nada si cambias de ordenador.</p></div>
    <div class="tarjeta" id="tarjeta-actualizacion"><h2>Actualizaciones</h2>
      <p>Versión instalada: <strong>${esc(INFO.version)}</strong></p>
      <div id="estado-actualizacion" class="muted">Pulsa el botón para ver si hay una versión nueva.</div>
      <p><button id="buscar-act">🔄 Buscar actualizaciones</button></p>
      <p class="muted">Al actualizar, el programa se cierra, se instala la versión nueva y se vuelve a abrir. Tus datos no se tocan, y antes se hace una copia de seguridad.</p></div>
    <div class="tarjeta"><h2>Pasar los datos a otro ordenador</h2>
      <p>Sirve para empezar a usar el programa en otro ordenador con los mismos alumnos, ACIs, horarios e informes. Los datos <strong>no se sincronizan</strong>: a partir de ese momento cada ordenador tiene los suyos.</p>
      <p><button id="exportar-datos">📤 Exportar mis datos</button>
        <label class="boton" for="importar-datos">📥 Importar datos de otro ordenador</label>
        <input type="file" id="importar-datos" accept=".db" hidden></p>
      <p class="muted">«Exportar» guarda un archivo .db en Documentos › Mundo PT-AL. Llévalo al otro ordenador y allí pulsa «Importar». Importar <strong>sustituye</strong> todos los datos de ese ordenador (antes se guarda una copia de seguridad).</p></div>
    <div class="tarjeta"><h2>Dictado por voz</h2>
      ${voz.disponible ? `<p>✅ Dictado sin conexión disponible (el audio no sale del ordenador).</p>`
        : `<p>⚠️ ${esc(voz.motivo)}</p><p class="muted">Mientras tanto puedes usar el dictado de Windows: haz clic en el cuadro de texto y pulsa <strong>Windows + H</strong>.</p>`}
    </div>
    <div class="tarjeta" id="ajustes-calendario"><h2>Google Calendar</h2><p class="muted">Cargando…</p></div>
    <div class="tarjeta" id="ajustes-material"><h2>Crear material</h2><p class="muted">Cargando…</p></div>
    <div class="tarjeta" id="ajustes-google"><h2>Google Drive</h2><p class="muted">Cargando…</p></div>
    <div class="tarjeta" id="ajustes-claude-desktop"><h2>Usar con Claude Desktop</h2><p class="muted">Cargando…</p></div>`;
  pintarAjustesMaterial();
  pintarAjustesGoogle();
  pintarAjustesCalendario();
  pintarAjustesClaudeDesktop();
  $("#copia").onclick = () => intentar(async () => { const r = await api("POST", "/api/copia-seguridad"); aviso("Copia guardada en " + r.ruta); });
  $("#buscar-act").onclick = () => buscarActualizacion(true);
  if (ACTUALIZACION) pintarActualizacion(ACTUALIZACION);
  $("#exportar-datos").onclick = () => intentar(async () => {
    if (window.pywebview) {
      const r = await api("GET", "/api/datos/exportar?guardar=1");
      aviso("Datos guardados en " + r.ruta);
    } else {
      location.href = "/api/datos/exportar";
    }
  });
  $("#importar-datos").onchange = (e) => importarDatos(e);
}

function importarDatos(e) {
  return intentar(async () => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (!confirm("Se sustituirán TODOS los datos de este ordenador por los del archivo «" + f.name + "». Antes se hará una copia de seguridad. ¿Seguir?")) return;
    const fd = new FormData();
    fd.append("archivo", f);
    const r = await api("POST", "/api/datos/importar", fd);
    alert(`Datos importados: ${r.usuarios} perfil(es) y ${r.alumnos} alumno(s).\nSi necesitas volver atrás, la copia anterior está en:\n${r.copia_previa}`
      + (r.calendarios_sin_direccion ? `\n\n${r.calendarios_sin_direccion} calendario(s) con dirección secreta: pégala de nuevo en Ajustes › Google Calendar (las direcciones secretas no viajan con los datos).` : ""));
    try { localStorage.removeItem(CLAVE_PERFIL); } catch (err) { /* sin almacenamiento */ }
    location.hash = "#/alumnos";
    location.reload();
  });
}

// ======================================================================= actualizaciones
let ACTUALIZACION = null;

function pintarActualizacion(r) {
  const nav = $('[data-nav="ajustes"]');
  if (nav) nav.classList.toggle("con-aviso", !!r.hay_nueva);
  const caja = $("#estado-actualizacion");
  if (!caja) return;
  if (!r.hay_nueva) {
    caja.innerHTML = `✅ Tienes la última versión${r.ultima ? ` (${esc(r.ultima)})` : ""}.`;
    return;
  }
  caja.innerHTML = `<p><strong>Hay una versión nueva: ${esc(r.ultima)}</strong>${r.fecha ? ` · publicada el ${esc(r.fecha.split("-").reverse().join("/"))}` : ""}</p>
    ${r.notas ? `<pre class="notas-version">${esc(r.notas)}</pre>` : ""}
    ${r.puede_instalar ? `<p><button class="primario" id="instalar-act">⬇️ Actualizar ahora</button></p>`
      : `<p class="muted">Descárgala desde GitHub y sustituye la carpeta del programa.</p>`}`;
  const b = $("#instalar-act");
  if (b) b.onclick = () => intentar(async () => {
    if (!confirm(`Se va a instalar la versión ${r.ultima}. El programa se cerrará y se volverá a abrir solo en unos segundos. ¿Seguir?`)) return;
    b.disabled = true;
    b.textContent = "Descargando…";
    await api("POST", "/api/actualizacion/instalar", { url: r.url });
    document.body.innerHTML = `<div class="vacio" style="margin:20vh auto;max-width:420px">Instalando la versión ${esc(r.ultima)}…<br>El programa se volverá a abrir en unos segundos.</div>`;
  }).catch(() => { b.disabled = false; b.textContent = "⬇️ Actualizar ahora"; });
}

async function buscarActualizacion(manual) {
  const caja = $("#estado-actualizacion");
  if (manual && caja) caja.textContent = "Buscando…";
  try {
    ACTUALIZACION = await api("GET", "/api/actualizacion");
    pintarActualizacion(ACTUALIZACION);
    if (!manual && ACTUALIZACION.hay_nueva) aviso(`Hay una versión nueva (${ACTUALIZACION.ultima}). Ve a Ajustes para actualizar.`);
  } catch (e) {
    if (manual && caja) caja.textContent = "⚠️ " + e.message;
  }
}

// ======================================================================= juntas de evaluación
// Guardado pendiente de las notas de la junta (se hace también al salir de la pantalla)
let GUARDAR_JUNTA = null;
window.addEventListener("hashchange", () => { if (GUARDAR_JUNTA) GUARDAR_JUNTA(); });

async function vistaJuntas(tri, alumnoId) {
  const trimestre = tri ? +tri : (+leerPref("junta.trimestre", "0") || 1);
  guardarPref("junta.trimestre", String(trimestre));
  const J = await api("GET", `/api/juntas?trimestre=${trimestre}`);
  const solo = alumnoId ? J.alumnos.find((a) => String(a.alumno_id) === String(alumnoId)) : null;
  if (alumnoId && !solo) throw new Error("Ese alumno no está en tu perfil.");
  if (solo) J.alumnos = [solo];
  const conNotas = (a) => (a.notas || "").trim();
  const enlaceInforme = (a) => a.informe ? `<a class="boton" href="#/${a.informe.tipo === "observacion" ? "observacion" : "informe"}/${a.informe.id}">Abrir ${a.informe.tipo === "observacion" ? "informe de observación" : "informe"}</a>` : "";
  const tarjeta = (a) => `<div class="tarjeta junta-alumno" id="ja-${a.alumno_id}">
      <div class="fila" style="gap:10px;flex-wrap:wrap;margin-bottom:6px">
        <div class="avatar">${esc(a.nombre[0] || "?").toUpperCase()}</div>
        <div><div class="nombre">${esc(a.nombre)}</div><div class="muted">${esc(a.curso || "")}</div></div>
        ${a.seguimiento === "observacion" ? `<span class="chip valoracion">En valoración · informe de observación</span>` : `<span class="chip">ACI · informe a familias</span>`}
        <span class="muted" data-estado="${a.alumno_id}">${a.pasado ? "Pasado al informe el " + fechaES(a.pasado.slice(0, 10)) : ""}</span>
        <span style="margin-left:auto">${botonMicro("jn-" + a.alumno_id)}</span></div>
      <textarea id="jn-${a.alumno_id}" data-alumno="${a.alumno_id}" data-micro-lineas rows="3"
        placeholder="- La tutora comenta que…&#10;- Le cuesta…&#10;- Le ayudan los pictogramas…">${esc(a.notas)}</textarea>
      <div class="fila" style="gap:8px;margin-top:8px;flex-wrap:wrap">
        <button class="primario" data-redactar="${a.alumno_id}">✨ Redactar para el informe del ${trimestre}º trimestre</button>
        ${enlaceInforme(a)}</div></div>`;
  const enlaceTri = (t) => solo ? `#/juntas/${t}/${solo.alumno_id}` : `#/juntas/${t}`;
  vista.innerHTML = `
    <div class="migas"><a href="#/alumnos">Alumnos</a> › ${solo ? `<a href="#/alumno/${solo.alumno_id}">${esc(solo.nombre)}</a> › Junta de evaluación`
      : "Junta de evaluación de todos"}</div>
    <div class="cabecera"><div><h1>${solo ? `Junta de evaluación · ${esc(solo.nombre)}` : "Juntas de evaluación"}</h1>
      <p class="sub">Apunta o dicta lo que se diga de cada alumno durante la junta. Después, con <strong>✨ Redactar</strong>,
        tus notas se convierten en un borrador más profesional, repartido por los apartados del informe del trimestre, que revisas antes de pasarlo.</p></div>
      <div class="acciones">${selectorVista(String(trimestre), [1, 2, 3].map((t) => [String(t), `${t}º trimestre`, enlaceTri(t)]))}</div></div>
    <div class="tarjeta"><div class="campos">
        <div><label>Fecha de la junta</label><input type="date" id="j-fecha" value="${esc(J.fecha || "")}"></div>
        <div><label>Curso escolar</label><input value="${esc(J.curso_escolar)}" disabled></div></div>
      ${solo ? `<p class="muted" style="margin:10px 0 0">Solo ves a ${esc(solo.nombre)}. <a href="#/juntas/${trimestre}">Ver la junta con todos los alumnos y las notas generales</a></p>` : ""}
      <details style="margin-top:10px" ${(J.notas || "").trim() ? "open" : ""} ${solo ? "hidden" : ""}><summary><strong>Notas generales de la junta</strong> <span class="muted">(acuerdos, fechas de entrega, cosas que no son de un alumno)</span></summary>
        <div class="notas-sesion" style="margin-top:8px"><textarea id="j-notas" data-micro-lineas rows="3">${esc(J.notas || "")}</textarea>${botonMicro("j-notas")}</div></details></div>
    ${J.alumnos.length ? `<div class="ayuda">Escribe una idea por línea (por ejemplo «la tutora dice que participa más en la asamblea»). Se guarda sola mientras escribes.
        El borrador nunca da nada por <strong>conseguido</strong>: eso solo sale de los ítems evaluados con C en la ACI.</div>
      ${solo ? "" : `<div class="junta-indice">${J.alumnos.map((a) => `<a href="#" data-ir="${a.alumno_id}" class="chip ${conNotas(a) ? "" : "vacia"}" id="ji-${a.alumno_id}">${conNotas(a) ? "✔ " : ""}${esc(a.nombre)}</a>`).join("")}</div>`}
      ${J.alumnos.map(tarjeta).join("")}`
      : `<div class="vacio">Todavía no tienes alumnos en tu perfil.</div>`}`;
  enlazarMicros(vista);

  // Datos de la junta
  $("#j-fecha").onchange = (e) => intentar(async () => { await api("PATCH", `/api/juntas/${J.id}`, { fecha: e.target.value }); aviso("Guardado"); });
  const general = $("#j-notas");
  general.onchange = () => intentar(() => api("PATCH", `/api/juntas/${J.id}`, { notas: general.value }));

  // Notas por alumno con guardado automático
  const guardados = Object.fromEntries(J.alumnos.map((a) => [a.alumno_id, a.notas || ""]));
  const temporizadores = {};
  const guardar = async (ta) => {
    const id = ta.dataset.alumno;
    clearTimeout(temporizadores[id]);
    if (ta.value === guardados[id]) return;
    const valor = ta.value;
    await api("PUT", `/api/juntas/${J.id}/alumnos/${id}`, { notas: valor });
    guardados[id] = valor;
    const chip = $("#ji-" + id);
    if (chip) {
      const nombre = (J.alumnos.find((a) => String(a.alumno_id) === id) || {}).nombre || "";
      chip.textContent = (valor.trim() ? "✔ " : "") + nombre;
      chip.classList.toggle("vacia", !valor.trim());
    }
    const estado = $(`[data-estado="${id}"]`);
    if (estado && ta.isConnected) estado.textContent = "Guardado ✔";
  };
  const ajustar = (ta) => { ta.style.height = "auto"; ta.style.height = Math.max(80, ta.scrollHeight + 2) + "px"; };
  $$("textarea[data-alumno]").forEach((ta) => {
    requestAnimationFrame(() => ajustar(ta));
    ta.oninput = () => {
      ajustar(ta);
      const estado = $(`[data-estado="${ta.dataset.alumno}"]`);
      if (estado) estado.textContent = "Guardando…";
      clearTimeout(temporizadores[ta.dataset.alumno]);
      temporizadores[ta.dataset.alumno] = setTimeout(() => intentar(() => guardar(ta)), 800);
    };
    ta.onchange = () => { ajustar(ta); intentar(() => guardar(ta)); };
  });
  GUARDAR_JUNTA = () => {
    $$("textarea[data-alumno]").forEach((ta) => { if (ta.value !== guardados[ta.dataset.alumno]) guardar(ta).catch(() => aviso("No se han podido guardar las notas de la junta", true)); });
    GUARDAR_JUNTA = null;
  };
  $$("[data-ir]").forEach((a) => a.onclick = (e) => {
    e.preventDefault();
    const t = $("#ja-" + a.dataset.ir);
    t.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => $("#jn-" + a.dataset.ir).focus({ preventScroll: true }), 400);
  });
  $$("[data-redactar]").forEach((b) => b.onclick = () => intentar(async () => {
    const ta = $("#jn-" + b.dataset.redactar);
    if (microActivo) await pararMicro();
    await guardar(ta);
    if (!ta.value.trim()) { aviso("Primero escribe o dicta las notas de la junta de este alumno."); ta.focus(); return; }
    const al = J.alumnos.find((a) => String(a.alumno_id) === b.dataset.redactar);
    await dialogoBorradorJunta(J, al);
  }));
}

async function dialogoBorradorJunta(J, al) {
  const d = await api("GET", `/api/juntas/${J.id}/alumnos/${al.alumno_id}/borrador`);
  if (!d.apartados.length) { aviso("No he encontrado frases en las notas de este alumno."); return; }
  const destino = d.tipo === "observacion" ? "informe de observación" : `informe del ${J.trimestre}º trimestre`;
  dialogo.innerHTML = `<form method="dialog" id="fjunta">
    <div class="dlg-cab"><h2>Borrador para el informe · ${esc(al.nombre)}</h2><button type="button" id="cerrar">Cerrar</button></div>
    <div class="dlg-cuerpo">
      <p class="muted" style="margin-top:0">He redactado tus notas de la junta y las he repartido por los apartados del ${destino}.
        Cambia lo que quieras: al pasarlo <strong>no se borra nada</strong> del informe, se añade al final de cada apartado
        ${d.tipo === "observacion" ? "" : "(si todavía no existe, se crea con el borrador de la ACI)"}.</p>
      <details><summary class="muted">Ver mis notas tal cual</summary><pre class="notas-junta">${esc(al.notas || $("#jn-" + al.alumno_id).value)}</pre></details>
      ${d.apartados.map((a, i) => `<div class="apartado-junta">
        <label class="check"><input type="checkbox" data-incluir="${i}" checked> <strong>${esc(a.titulo)}</strong></label>
        <textarea rows="3" data-texto="${i}">${esc(a.texto)}</textarea></div>`).join("")}
    </div>
    <div class="dlg-pie"><button type="button" id="copiar-junta" style="margin-right:auto">📋 Copiar texto</button>
      <button class="primario" id="pasar-junta">Pasar al ${destino}</button></div></form>`;
  dialogo.showModal();
  $$("[data-texto]", dialogo).forEach((t) => { t.style.height = "auto"; t.style.height = Math.max(70, t.scrollHeight + 2) + "px"; });
  $("#cerrar").onclick = () => dialogo.close();
  const elegidos = () => d.apartados.map((a, i) => ({ ...a, texto: $(`[data-texto="${i}"]`).value.trim(), incluir: $(`[data-incluir="${i}"]`).checked }))
    .filter((a) => a.incluir && a.texto);
  $("#copiar-junta").onclick = () => intentar(async () => {
    await navigator.clipboard.writeText(elegidos().map((a) => a.texto).join("\n\n"));
    aviso("Texto copiado");
  });
  $("#fjunta").onsubmit = (e) => {
    e.preventDefault();
    intentar(async () => {
      const apartados = elegidos();
      if (!apartados.length) { aviso("No hay ningún apartado marcado con texto."); return; }
      if (al.pasado && !confirm(`Ya pasaste la junta de ${al.nombre} al informe el ${fechaES(al.pasado.slice(0, 10))}. Lo que ya esté igual no se repite. ¿Añadir de nuevo?`)) return;
      const r = await api("POST", `/api/juntas/${J.id}/alumnos/${al.alumno_id}/informe`, { apartados });
      dialogo.close();
      aviso("Añadido al informe ✔. Revísalo y retócalo a tu gusto.");
      location.hash = r.tipo === "observacion" ? `#/observacion/${r.id}` : `#/informe/${r.id}`;
    });
  };
}

// ======================================================================= inicio
(async () => {
  try { INFO = await api("GET", "/api/info"); } catch (e) { /* valores por defecto */ }
  try {
    const usuarios = await api("GET", "/api/usuarios");
    const guardado = leerPerfilGuardado();
    USUARIO = usuarios.find((u) => String(u.id) === guardado) || (usuarios.length === 1 ? usuarios[0] : null);
    if (USUARIO) guardarPerfil(USUARIO.id);
  } catch (e) { /* sin perfiles */ }
  pintarPerfilLateral();
  enrutar();
  setTimeout(() => buscarActualizacion(false), 3000);  // aviso discreto si hay versión nueva
  setTimeout(() => actualizarCalendarios(30), 1500);   // Google Calendar en segundo plano (si hace más de 30 min)
})();
