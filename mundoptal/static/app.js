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
  [/^#\/informes$/, vistaInformes, "informes"],
  [/^#\/informe\/(\d+)$/, vistaInforme, "informes"],
  [/^#\/trabajo(?:\/(dia|semana|mes))?(?:\/(\d{4}-\d{2}(?:-\d{2})?))?$/, vistaTrabajo, "trabajo"],
  [/^#\/material$/, vistaMaterial, "material"],
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
async function vistaAlumnos() {
  const alumnos = await api("GET", "/api/alumnos");
  vista.innerHTML = `
    <div class="cabecera">
      <div><h1>Alumnos y ACIs</h1><p class="sub">Crea un alumno y su Adaptación Curricular Individual, o importa una ACI que ya tengas en Word.</p></div>
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
      </div>
      <p class="acciones" style="margin:12px 0 0"><button class="primario">Guardar y crear ACI</button><button type="button" id="cancelar">Cancelar</button></p>
    </form>
    ${alumnos.length ? `<div class="rejilla">${alumnos.map(tarjetaAlumno).join("")}</div>`
      : `<div class="vacio">Todavía no hay alumnos. Pulsa «Nuevo alumno» o importa una ACI desde Word.</div>`}`;

  const form = $("#form-alumno");
  $("#nuevo").onclick = () => { form.hidden = false; form.nombre.focus(); };
  $("#cancelar").onclick = () => { form.hidden = true; };
  form.onsubmit = (e) => intentar(async () => {
    e.preventDefault();
    const datos = Object.fromEntries(new FormData(form));
    const { id } = await api("POST", "/api/alumnos", datos);
    const aci = await api("POST", `/api/alumnos/${id}/acis`, {});
    location.hash = `#/aci/${aci.id}`;
  });
  $("#importar").onchange = (e) => importarWord(e.target.files[0]);
}

function tarjetaAlumno(a) {
  return `<div class="tarjeta alumno">
    <div class="fila"><div class="avatar">${esc(a.nombre[0] || "?").toUpperCase()}</div>
      <div><div class="nombre">${esc(a.nombre)}</div><div class="muted">${esc(a.curso || "Curso sin indicar")}</div></div></div>
    <div><span class="chip">${a.num_acis} ACI${a.num_acis === 1 ? "" : "s"}</span></div>
    <div class="botones">
      ${a.aci_vigente_id ? `<a class="boton primario" href="#/aci/${a.aci_vigente_id}">Abrir ACI</a>` : ""}
      <a class="boton" href="#/alumno/${a.id}">Ficha</a>
    </div></div>`;
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
  const a = await api("GET", `/api/alumnos/${id}`);
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
        <div class="campo-ancho"><label>Observaciones</label><textarea data-tabla="alumnos" data-id="${a.id}" data-campo="observaciones" rows="2">${esc(a.observaciones)}</textarea></div>
      </div>
      <p style="margin:12px 0 0"><button class="peligro" id="borrar-alumno">Borrar alumno y todas sus ACIs</button></p></div>
    <div class="tarjeta" id="asistencia"><h2>Asistencia a las sesiones</h2><p class="muted">Cargando…</p></div>
    <div class="tarjeta"><h2>Informes para la familia</h2>
      ${a.informes.length ? `<table class="tabla-adapt"><tr><th>Trimestre</th><th>Curso escolar</th><th>Última modificación</th><th></th></tr>
        ${a.informes.map((x) => `<tr><td>${x.trimestre}º trimestre</td><td>${esc(x.curso_escolar)}</td><td>${esc(x.actualizado)}</td>
          <td><a class="boton mini" href="#/informe/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">Sin informes todavía.</div>`}
      <p style="margin:12px 0 0"><button id="nuevo-informe">📝 Informe del trimestre actual</button></p></div>
    <div class="tarjeta"><h2>Tutorías y reuniones</h2>
      ${(a.citas || []).length ? `<ul class="lista-citas">${a.citas.map((c) => `<li>
          <button type="button" class="cita ${c.tipo} ${c.hecha ? "hecha" : ""}" data-cita-alumno="${c.id}">${c.tipo === "tutoria_familia" ? "Tutoría familia" : c.tipo === "reunion_terapeutas" ? "Reunión terapeutas" : "Cita"}</button>
          <strong>${fechaCorta(c.fecha)}/${c.fecha.slice(0, 4)}</strong>${c.hora_inicio ? " · " + c.hora_inicio : ""}${c.con_quien ? " · " + esc(c.con_quien) : ""}
          ${c.notas ? `<div class="muted" style="margin-left:4px">${esc(c.notas)}</div>` : ""}</li>`).join("")}</ul>`
        : `<div class="vacio" style="padding:16px">Sin tutorías ni reuniones todavía.</div>`}
      <p style="margin:12px 0 0"><button id="nueva-tutoria">＋ Nueva tutoría o reunión</button></p></div>
    <div class="tarjeta"><h2>ACIs</h2>
      ${a.acis.length ? `<table class="tabla-adapt"><tr><th>Trimestre</th><th>Curso escolar</th><th>Curso</th><th>Última modificación</th><th></th></tr>
        ${a.acis.map((x, i) => `<tr><td>${x.trimestre}º trimestre ${i === 0 ? '<span class="chip">vigente</span>' : ""}</td><td>${esc(x.curso_escolar)}</td>
          <td>${esc(x.curso)}</td><td>${esc(x.actualizado)}</td><td><a class="boton mini" href="#/aci/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">Sin ACIs todavía.</div>`}
      <p class="muted" style="margin-top:10px">La ACI más reciente es la vigente: es la que se usa para planificar las sesiones.</p></div>`;
  enlazarCampos(vista);
  pintarAsistencia(id);
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
    const base = ta.value.trim();
    await api("POST", "/api/voz/iniciar");
    b.classList.add("grabando");
    b.textContent = "⏹";
    const sondeoMicro = setInterval(async () => {
      const e = await api("GET", "/api/voz").catch(() => null);
      if (!e) return;
      ta.value = [base, e.texto, e.parcial].filter(Boolean).join(" ");
      if (e.error) aviso(e.error, true);
      if (!e.grabando) await pararMicro();
    }, 600);
    microActivo = { boton: b, ta, base, sondeo: sondeoMicro };
  }));
}
async function pararMicro() {
  if (!microActivo) return;
  const { boton, ta, base, sondeo: s } = microActivo;
  microActivo = null;
  clearInterval(s);
  const e = await api("POST", "/api/voz/detener").catch(() => null);
  boton.classList.remove("grabando");
  boton.textContent = "🎤";
  if (e) ta.value = [base, e.texto].filter(Boolean).join(" ");
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
  $("#importar-horario").onchange = (e) => intentar(async () => {
    const archivo = e.target.files[0];
    if (!archivo) return;
    const reemplazar = franjas.length > 0 && confirm("¿Quieres reemplazar tu horario actual por el del archivo?\n\nAceptar: se borra el horario actual (y sus sesiones planificadas).\nCancelar: se añaden las franjas nuevas sin tocar las que ya tienes.");
    const fd = new FormData();
    fd.append("archivo", archivo);
    fd.append("reemplazar", reemplazar ? "1" : "0");
    const r = await api("POST", "/api/horario/importar", fd);
    let txt = `Horario importado: ${r.franjas} franjas`;
    if (r.alumnos_nuevos.length) txt += `. Alumnos nuevos: ${r.alumnos_nuevos.join(", ")}`;
    if (r.omitidas.length) txt += `. Omitidas por solaparse: ${r.omitidas.length}`;
    aviso(txt);
    vistaHorario();
  });
  $$("[data-franja]").forEach((el) => el.onclick = () => formFranja(franjas.find((f) => f.id === +el.dataset.franja), alumnos));
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
    if (!confirm("¿Borrar esta franja y sus sesiones planificadas?")) return;
    await api("DELETE", `/api/franjas/${f.id}`); dialogo.close(); vistaHorario();
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

function htmlSesion(s) {
  return `<div class="sesion ${s.estado}">
    <div class="cab-ses"><span class="franja" style="padding:0;background:none;border:none;cursor:default"><span class="hora">${s.inicio}–${s.fin}</span></span>
      <a href="#/aci/${s.aci_id}" title="Abrir ACI">${esc(s.alumno)}</a><span class="chip">${s.especialidad}</span></div>
    ${s.items.length ? `<ul>${s.items.map((it) => `<li>
      <input type="checkbox" title="Trabajado en la sesión" data-trabajado data-sesion="${s.id}" data-item="${it.id}" ${it.trabajado ? "checked" : ""}>
      <div>${esc(it.texto)}<div class="ctx">${esc(it.subarea || it.area)} · ${esc(it.competencia)}</div>
        <div class="pie-item"><select title="Evaluación del trimestre actual" class="${claseEval(it.evaluacion)}" data-evaluar data-sesion="${s.id}" data-item="${it.id}">
        <option value=""></option>${INFO.escala.map((k) => `<option ${k === it.evaluacion ? "selected" : ""}>${k}</option>`).join("")}</select>
        <button class="icono" title="Quitar de esta sesión" data-quitar data-sesion="${s.id}" data-item="${it.id}">✕ quitar</button></div>
        <div class="obs-item"><textarea rows="1" class="nota" placeholder="Observación rápida (luego se redacta en el informe)" id="obs-${s.id}-${it.id}"
          data-obs-item data-sesion="${s.id}" data-item="${it.id}">${esc(it.observacion || "")}</textarea>${botonMicro(`obs-${s.id}-${it.id}`)}</div></div></li>`).join("")}</ul>`
      : `<p class="muted" style="font-size:12px">Sin ítems pendientes asignados.</p>`}
    <div class="notas-sesion"><textarea rows="2" placeholder="Notas de la sesión (escríbelas o díctalas rápido; luego se redactan en el informe)" data-notas="${s.id}" id="notas-${s.id}" style="font-size:12px">${esc(s.notas)}</textarea>
      ${botonMicro("notas-" + s.id)}</div>
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
    const filas = d.alumnos.map((a) => {
      const inf = a.informes.find((x) => x.trimestre === trimestre && x.curso_escolar === d.curso_escolar);
      return `<div class="tarjeta alumno">
        <div class="fila"><div class="avatar">${esc(a.nombre[0] || "?").toUpperCase()}</div>
          <div><div class="nombre">${esc(a.nombre)}</div><div class="muted">${esc(a.curso || "Curso sin indicar")}</div></div></div>
        <div>${inf ? `<span class="chip">Empezado · ${esc(inf.actualizado.slice(0, 10))}</span>` : `<span class="muted">Sin informe</span>`}</div>
        <div class="botones">${inf ? `<a class="boton primario" href="#/informe/${inf.id}">Abrir informe</a>`
          : `<button class="primario" data-crear="${a.id}">Crear informe</button>`}</div></div>`;
    }).join("");
    vista.innerHTML = `
      <div class="cabecera"><div><h1>Informes para las familias</h1>
        <p class="sub">Informe descriptivo de cómo ha ido el trimestre («Observaciones y comentarios»): cómo se ha mostrado, actitud en las sesiones de PT y AL y evolución en cada área.
        Se prepara un borrador con la ACI, lo completas y lo exportas a Word.</p></div>
        <div class="acciones"><label for="tri" style="align-self:center">Trimestre</label>
          <select id="tri">${[1, 2, 3].map((t) => `<option value="${t}" ${t === trimestre ? "selected" : ""}>${t}º · ${esc(d.curso_escolar)}</option>`).join("")}</select></div></div>
      ${d.alumnos.length ? `<div class="rejilla">${filas}</div>` : `<div class="vacio">Todavía no tienes alumnos en tu perfil.</div>`}`;
    $("#tri").onchange = (e) => { trimestre = +e.target.value; pintar(); };
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
    <div class="migas"><a href="#/informes">Informes</a> › <a href="#/alumno/${I.alumno_id}">${esc(I.alumno_nombre)}</a> › ${I.trimestre}º trimestre</div>
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
function htmlEstadoCalendarios(cals) {
  if (!cals.length) return "";
  const conUrl = cals.filter((c) => c.origen === "url");
  const ultima = conUrl.map((c) => c.actualizado).filter(Boolean).sort().pop();
  const error = cals.find((c) => c.error);
  return `<div class="estado-cal">${cals.map((c) => `<span class="cal-nombre" style="--ce:${colorCal(c.color)}">📅 ${esc(c.nombre)}</span>`).join("")}
    ${conUrl.length ? `<span class="muted">Actualizado ${haceMinutos(ultima)}</span><button class="mini" id="actualizar-cal">↻ Actualizar</button>` : ""}
    ${error ? `<span class="error-cal" title="${esc(error.error)}">⚠ ${esc(error.error)}</span>` : ""}</div>`;
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
    <div class="dlg-pie">${nueva ? "" : `<button class="peligro" id="c-borrar">Borrar</button>`}
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

// ======================================================================= crear material
const NOMBRE_ACT = { letra: "Letra grande", repasar: "Repasar", rodear: "Rodear", unir: "Unir con flechas", completar: "Completar",
  contar: "Contar", clasificar: "Clasificar", secuencia: "Secuencia", tarjetas: "Tarjetas", pregunta: "Pregunta", cuento: "Cuento" };
let PROPUESTA = null;  // { spec, origen, tipo, alumno_id }

async function vistaMaterial() {
  const [info, alumnos, lista] = await Promise.all([api("GET", "/api/material/info"), api("GET", "/api/alumnos"), api("GET", "/api/materiales")]);
  const tipos = info.tipos;
  const opcAlumnos = `<option value="">Ninguno</option>${alumnos.map((a) => `<option value="${a.id}">${esc(a.nombre)}</option>`).join("")}`;
  const comunes = (p) => `<div class="campos material-campos">
      <div><label>Alumno (opcional)</label><select id="${p}-alumno">${opcAlumnos}</select></div>
      <div><label>Nivel</label><select id="${p}-nivel"><option value="3">3 años</option><option value="4" selected>4 años</option><option value="5">5 años</option></select></div>
      <div><label>Formato</label><select id="${p}-formato"><option value="docx">Word · fichas para imprimir</option><option value="pptx">PowerPoint · para proyectar</option></select></div>
      <div><label>Nº de fichas o diapositivas</label><input type="number" id="${p}-num" min="1" max="${p === "ia" ? 20 : 40}" placeholder="${p === "ia" ? "6" : "Todas"}" value="${p === "ia" ? 6 : ""}"></div></div>`;
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Crear material</h1>
      <p class="sub">Fichas en Word para imprimir o diapositivas en PowerPoint, con el logo del colegio y pictogramas de ARASAAC.</p></div></div>
    <div class="material-grid">
      <div>
        <div class="tarjeta"><h2>📋 Plantillas (gratis y sin Internet)</h2>
          <div class="campos material-campos">
            <div><label>Tipo de material</label><select id="pl-tipo">${tipos.map(([k, t]) => `<option value="${k}">${esc(t.nombre)}</option>`).join("")}</select></div>
            <div class="campo-ancho"><label>Contenido</label><input id="pl-contenido" placeholder="${esc(tipos[0][1].ejemplo)}">
              <p class="muted" id="pl-ayuda" style="margin:3px 0 0;font-size:12px">${esc(tipos[0][1].ayuda)}</p></div></div>
          ${comunes("pl")}
          <div id="sugerencias-pl" class="sugerencias"></div>
          <p style="margin:10px 0 0"><button class="primario" id="pl-preparar">👀 Ver propuesta</button></p>
          <p class="nota-amable">💬 ¿Necesitas algo que no está aquí? Pídeselo a Claude en el chat de Mundo PT-AL y te lo dejará en Documentos › Mundo PT-AL › Material.</p></div>
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
                <span class="muted">${esc((m.creado || "").slice(0, 10))} · ${m.paginas} ${m.formato === "pptx" ? "diapositivas" : "fichas"}${m.origen === "ia" ? " · ✨ Claude" : ""}${m.alumno ? " · " + esc(m.alumno) : ""}${m.existe ? "" : " · ⚠ archivo movido o borrado"}</span></div>
              ${m.existe ? `<button class="mini" data-abrir-material="${m.id}">Abrir</button><a class="boton mini" href="/api/materiales/${m.id}/archivo">Descargar</a>` : ""}
              <button class="icono" data-quitar-material="${m.id}" title="Quitar de la lista (el archivo no se borra)">✕</button></li>`).join("")}</ul>`
            : `<div class="vacio" style="padding:16px">Todavía no has creado material.</div>`}
          <p class="muted" style="margin:8px 0 0;font-size:12px">Se guarda en: ${esc(info.carpeta)}</p></div>
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
  for (const p of info.clave ? ["pl", "ia"] : ["pl"]) {
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
        else $("#ia-peticion").value = `Material para trabajar: ${s.motivo.toLowerCase()}`;
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
  $$("[data-abrir-material]").forEach((b) => b.onclick = () => intentar(async () => {
    const r = await api("POST", `/api/materiales/${b.dataset.abrirMaterial}/abrir`);
    if (!r.abierto) aviso("Está en " + r.ruta);
  }));
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
    <p class="muted" style="font-size:12px;margin:6px 0 0">El archivo se guarda y se abre con Word o PowerPoint. Después puedes retocarlo allí.</p>`;
  $$("[data-crear]", caja).forEach((b) => b.onclick = () => intentar(async () => {
    b.disabled = true;
    const txt = b.textContent;
    b.textContent = "Creando…";
    try {
      const r = await api("POST", "/api/material/crear", { spec: s, formato: b.dataset.crear, alumno_id: PROPUESTA.alumno_id,
        origen: PROPUESTA.origen, tipo: PROPUESTA.tipo, abrir: true });
      aviso("Material guardado: " + r.nombre);
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

const COLORES_CAL = ["#2B7BB9", "#E67C73", "#33B679", "#F6BF26", "#8E24AA", "#F4511E", "#039BE5", "#616161"];

async function pintarAjustesCalendario() {
  const caja = $("#ajustes-calendario");
  if (!USUARIO) { caja.innerHTML = "<h2>Google Calendar</h2><p class='muted'>Elige primero tu perfil.</p>"; return; }
  const cals = await api("GET", "/api/calendarios").catch(() => null);
  if (!cals || !caja.isConnected) return;
  const color = COLORES_CAL[cals.length % COLORES_CAL.length];
  caja.innerHTML = `<h2>Google Calendar</h2>
    <p class="muted" style="margin-top:0">Ves tus calendarios (por ejemplo el del colegio) dentro de «Mi trabajo PT/AL» y en la agenda del día. Solo se leen: la aplicación nunca cambia nada en Google.</p>
    ${cals.length ? `<ul class="lista-calendarios">${cals.map((c) => `<li>
        <input type="color" value="${colorCal(c.color)}" data-cal-color="${c.id}" title="Color">
        <input value="${esc(c.nombre)}" data-cal-nombre="${c.id}" style="flex:1;min-width:120px">
        <span class="muted">${c.eventos} eventos · ${c.origen === "url" ? "actualizado " + haceMinutos(c.actualizado) : "importado de archivo"}</span>
        ${c.error ? `<span class="error-cal">⚠ ${esc(c.error)}</span>` : ""}
        ${c.origen === "url" ? `<button class="mini" data-cal-probar="${c.id}">Probar</button>`
          : `<label class="boton mini" for="reimp-${c.id}">Volver a importar</label><input type="file" id="reimp-${c.id}" data-cal-reimportar="${c.id}" accept=".ics" hidden>`}
        <button class="mini peligro" data-cal-quitar="${c.id}">Quitar</button></li>`).join("")}</ul>` : ""}
    <h3 style="margin:14px 0 6px">Añadir un calendario</h3>
    <div class="campos">
      <div><label>Nombre</label><input id="cal-nombre" placeholder="Calendario del colegio"></div>
      <div><label>Color</label><input type="color" id="cal-color" value="${color}" style="height:36px"></div>
      <div class="campo-ancho"><label>Dirección secreta en formato iCal</label>
        <input type="password" id="cal-url" placeholder="https://calendar.google.com/calendar/ical/…/private-…/basic.ics" autocomplete="off"></div></div>
    <p style="margin:8px 0 0"><button class="primario" id="cal-anadir">Añadir</button>
      <span class="muted">o</span> <label class="boton" for="cal-archivo">📄 Importar archivo .ics</label><input type="file" id="cal-archivo" accept=".ics" hidden></p>
    <details style="margin-top:10px"><summary>¿Dónde encuentro la dirección secreta?</summary><ol>
      <li>Abre Google Calendar en el ordenador (calendar.google.com).</li>
      <li>A la izquierda, pasa el ratón por tu calendario › ⋮ › <strong>Configuración y uso compartido</strong>.</li>
      <li>Baja hasta <strong>Integrar el calendario</strong> y copia la <strong>Dirección secreta en formato iCal</strong>.</li></ol>
      <p class="muted">Es privada: quien la tenga puede ver tu calendario. Se guarda en el Administrador de credenciales de Windows, no en los datos de la aplicación. Si no la ves (cuentas del colegio a veces la ocultan), usa «Importar archivo .ics»: en Google Calendar, Configuración › Importar y exportar › Exportar.</p></details>`;
  const recargar = () => pintarAjustesCalendario();
  $("#cal-anadir").onclick = () => intentar(async () => {
    const url = $("#cal-url").value.trim();
    if (!url) { $("#cal-url").focus(); return; }
    $("#cal-anadir").disabled = true;
    try {
      const r = await api("POST", "/api/calendarios", { nombre: $("#cal-nombre").value, color: $("#cal-color").value, url });
      aviso(`Calendario añadido (${r.eventos} eventos)`);
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
    <div class="tarjeta" id="ajustes-material"><h2>Crear material</h2><p class="muted">Cargando…</p></div>`;
  pintarAjustesMaterial();
  pintarAjustesCalendario();
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
    alert(`Datos importados: ${r.usuarios} perfil(es) y ${r.alumnos} alumno(s).\nSi necesitas volver atrás, la copia anterior está en:\n${r.copia_previa}`);
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
