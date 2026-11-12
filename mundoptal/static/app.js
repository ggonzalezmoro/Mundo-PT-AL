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

// ======================================================================= rutas
const rutas = [
  [/^#\/alumnos$/, vistaAlumnos, "alumnos"],
  [/^#\/alumno\/(\d+)$/, vistaAlumno, "alumnos"],
  [/^#\/aci\/(\d+)$/, vistaACI, "alumnos"],
  [/^#\/horario$/, vistaHorario, "horario"],
  [/^#\/agenda(?:\/(\d{4}-\d{2}-\d{2}))?$/, vistaAgenda, "agenda"],
  [/^#\/ajustes$/, vistaAjustes, "ajustes"],
  [/^#\/perfiles$/, vistaPerfiles, "perfiles"],
  [/^#\/informes$/, vistaInformes, "informes"],
  [/^#\/informe\/(\d+)$/, vistaInforme, "informes"],
];

async function enrutar() {
  const h = location.hash || "#/alumnos";
  if (!USUARIO && h !== "#/perfiles") { location.hash = "#/perfiles"; return; }
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
    <div class="tarjeta"><h2>Informes para la familia</h2>
      ${a.informes.length ? `<table class="tabla-adapt"><tr><th>Trimestre</th><th>Curso escolar</th><th>Última modificación</th><th></th></tr>
        ${a.informes.map((x) => `<tr><td>${x.trimestre}º trimestre</td><td>${esc(x.curso_escolar)}</td><td>${esc(x.actualizado)}</td>
          <td><a class="boton mini" href="#/informe/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">Sin informes todavía.</div>`}
      <p style="margin:12px 0 0"><button id="nuevo-informe">📝 Informe del trimestre actual</button></p></div>
    <div class="tarjeta"><h2>ACIs</h2>
      ${a.acis.length ? `<table class="tabla-adapt"><tr><th>Trimestre</th><th>Curso escolar</th><th>Curso</th><th>Última modificación</th><th></th></tr>
        ${a.acis.map((x, i) => `<tr><td>${x.trimestre}º trimestre ${i === 0 ? '<span class="chip">vigente</span>' : ""}</td><td>${esc(x.curso_escolar)}</td>
          <td>${esc(x.curso)}</td><td>${esc(x.actualizado)}</td><td><a class="boton mini" href="#/aci/${x.id}">Abrir</a></td></tr>`).join("")}</table>`
        : `<div class="vacio">Sin ACIs todavía.</div>`}
      <p class="muted" style="margin-top:10px">La ACI más reciente es la vigente: es la que se usa para planificar las sesiones.</p></div>`;
  enlazarCampos(vista);
  $("#nueva-aci").onclick = () => intentar(async () => {
    const r = await api("POST", `/api/alumnos/${id}/acis`, {});
    location.hash = `#/aci/${r.id}`;
  });
  $("#importar").onchange = (e) => importarWord(e.target.files[0], id);
  $("#nuevo-informe").onclick = () => crearInforme(id);
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
    <div class="texto"><textarea rows="1" data-tabla="items" data-id="${it.id}" data-campo="texto" placeholder="Describe el ítem">${esc(it.texto)}</textarea></div>
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
async function vistaAgenda(semana) {
  const desde = semana || fechaISO(lunes(new Date()));
  const hasta = sumarDias(desde, 4);
  const ag = await api("GET", `/api/agenda?desde=${desde}&hasta=${hasta}`);
  const hoy = fechaISO(new Date());
  const porDia = INFO.dias.map((_, i) => ag.sesiones.filter((s) => s.fecha === sumarDias(desde, i)));
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Agenda de sesiones</h1>
      <p class="sub">Semana del ${fechaCorta(desde)} al ${fechaCorta(hasta)}. Los ítems no conseguidos se reparten solos en tus sesiones.</p></div>
      <div class="acciones">
        <a class="boton" href="#/agenda/${sumarDias(desde, -7)}">◀</a>
        <a class="boton" href="#/agenda">Esta semana</a>
        <a class="boton" href="#/agenda/${sumarDias(desde, 7)}">▶</a>
        <button class="primario" id="planificar">⚡ Planificar semana</button>
        <button id="replanificar" title="Vuelve a repartir los ítems de las sesiones aún no realizadas">↻ Replanificar</button>
      </div></div>
    ${ag.sesiones.length ? "" : `<div class="vacio" style="margin-bottom:14px">No hay sesiones planificadas esta semana. Configura <a href="#/horario">tu horario</a> y pulsa «Planificar semana».</div>`}
    <div class="semana">${INFO.dias.map((d, i) => { const f = sumarDias(desde, i); return `<div class="dia ${f === hoy ? "hoy" : ""}">
      <h3>${d} <small>${fechaCorta(f)}</small></h3><div class="bloques">${porDia[i].map(htmlSesion).join("") || '<div class="muted" style="text-align:center;padding:20px 0">—</div>'}</div></div>`; }).join("")}</div>`;

  const plan = (re) => intentar(async () => {
    const r = await api("POST", "/api/planificar", { desde, hasta, replanificar: re });
    let txt = `Planificadas ${r.sesiones} sesiones nuevas con ${r.items} ítems`;
    if (r.sin_pendientes.length) txt += `. Sin ítems pendientes: ${r.sin_pendientes.join(", ")}`;
    aviso(txt);
    vistaAgenda(desde);
  });
  $("#planificar").onclick = () => plan(false);
  $("#replanificar").onclick = () => { if (confirm("Se volverán a repartir los ítems de las sesiones no realizadas de esta semana. ¿Continuar?")) plan(true); };

  $$("[data-sesion-estado]").forEach((b) => b.onclick = () => intentar(async () => {
    await api("PATCH", `/api/sesiones/${b.dataset.id}`, { estado: b.dataset.sesionEstado });
    vistaAgenda(desde);
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
    vistaAgenda(desde);
  }));
  $$("[data-notas]").forEach((t) => t.onchange = () => intentar(() => api("PATCH", `/api/sesiones/${t.dataset.notas}`, { notas: t.value })));
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
        <button class="icono" title="Quitar de esta sesión" data-quitar data-sesion="${s.id}" data-item="${it.id}">✕ quitar</button></div></div></li>`).join("")}</ul>`
      : `<p class="muted" style="font-size:12px">Sin ítems pendientes asignados.</p>`}
    <textarea rows="1" placeholder="Notas de la sesión" data-notas="${s.id}" style="font-size:12px">${esc(s.notas)}</textarea>
    <div class="estado" style="margin-top:6px">
      ${s.estado !== "realizada" ? `<button class="mini" data-sesion-estado="realizada" data-id="${s.id}">✔ Realizada</button>` : `<span class="chip">Realizada</span>`}
      ${s.estado !== "cancelada" ? `<button class="mini" data-sesion-estado="cancelada" data-id="${s.id}">Cancelar</button>` : ""}
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
      <p style="margin:12px 0 0"><button class="primario">Crear perfil</button></p></form>`;
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
    <textarea rows="4" data-tabla="informes" data-id="${INFORME.id}" data-campo="${campo}" id="campo-${campo}">${esc(INFORME[campo])}</textarea>
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
      <p class="sub">${I.trimestre}º trimestre · Curso ${esc(I.curso_escolar)}. Se guarda solo al escribir. Para dictar, haz clic en un cuadro y pulsa <strong>Windows + H</strong>.</p></div>
      <div class="acciones"><button class="primario" id="word-informe">📄 Exportar a Word</button></div></div>
    <div class="tarjeta"><p class="muted" style="margin-top:0">Se redacta como el apartado «Observaciones y comentarios» de la ACI: un texto seguido para la familia.
      Al exportar la ACI de este trimestre, este texto se incluye también al final de la ACI.</p><div class="campos">
      <div><label>Curso</label><input data-tabla="informes" data-id="${I.id}" data-campo="curso" value="${esc(I.curso)}"></div>
      <div><label>Prof. responsable de área (tutor/a)</label><input data-tabla="informes" data-id="${I.id}" data-campo="prof_area" value="${esc(I.prof_area)}"></div>
      <div><label>Prof. AL/PT</label><input data-tabla="informes" data-id="${I.id}" data-campo="maestra" value="${esc(I.maestra)}"></div></div></div>
    ${bloqueTexto("Cómo se ha mostrado este trimestre", "social", "Ánimo, relación con compañeros y adultos, gestión de emociones…", "social")}
    ${esp !== "AL" ? bloqueTexto("Actitud en las sesiones de PT", "actitud_pt", "", "actitud") : ""}
    ${esp !== "PT" ? bloqueTexto("Actitud en las sesiones de AL", "actitud_al", "", "actitud") : ""}
    <div class="tarjeta"><div class="cabecera" style="margin:0 0 8px"><div><h2 style="margin:0">Evolución en las distintas áreas</h2>
      <p class="muted">Borrador hecho con las evaluaciones de la ACI. Revísalo y escríbelo con tus palabras para la familia (el título del área no aparece en el Word).</p></div>
      <div class="acciones"><button id="rehacer">↻ Rehacer borrador desde la ACI</button><button id="nueva-area">＋ Añadir área</button></div></div>
      ${I.areas.length ? I.areas.map((a) => `<div class="area-informe">
        <div class="fila" style="gap:8px"><input class="titulo-area" data-tabla="informe_areas" data-id="${a.id}" data-campo="area" value="${esc(a.area)}">
          <button class="mini peligro" data-borrar-area="${a.id}" title="Quitar esta área del informe">✕</button></div>
        <textarea rows="5" data-tabla="informe_areas" data-id="${a.id}" data-campo="texto">${esc(a.texto)}</textarea></div>`).join("")
        : `<div class="vacio">No hay áreas. Pulsa «Rehacer borrador desde la ACI» o «Añadir área».</div>`}</div>
    ${bloqueTexto("Orientaciones para casa", "orientaciones", "Opcional: sugerencias sencillas para seguir avanzando en casa.", "orientaciones")}
    ${bloqueTexto("Cierre", "valoracion", "Unas palabras finales y agradecimiento a la familia.", "cierre")}
    <div class="tarjeta"><h2>Despedida</h2><input style="width:100%" data-tabla="informes" data-id="${I.id}" data-campo="despedida" value="${esc(I.despedida)}"></div>`;
  enlazarCampos(vista);
  $$(".frases").forEach((caja) => caja.querySelectorAll(".frase").forEach((b) => b.onclick = () => {
    const ta = $("#campo-" + caja.dataset.para);
    ta.value = (ta.value.trim() ? ta.value.trim() + " " : "") + b.textContent;
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

// ======================================================================= ajustes
async function vistaAjustes() {
  const voz = await api("GET", "/api/voz");
  vista.innerHTML = `
    <div class="cabecera"><div><h1>Ajustes</h1><p class="sub">${esc(INFO.app)} ${esc(INFO.version)} · ${esc(INFO.colegio)}</p></div></div>
    <div class="tarjeta"><h2>Tus datos</h2>
      <p>Toda la información se guarda únicamente en este ordenador, en la carpeta:</p>
      <p><code>${esc(INFO.datos)}</code></p>
      <p><button class="primario" id="copia">💾 Hacer copia de seguridad ahora</button></p>
      <p class="muted">Las copias se guardan en la subcarpeta «copias». Puedes llevarlas a un pendrive para no perder nada si cambias de ordenador.</p></div>
    <div class="tarjeta"><h2>Dictado por voz</h2>
      ${voz.disponible ? `<p>✅ Dictado sin conexión disponible (el audio no sale del ordenador).</p>`
        : `<p>⚠️ ${esc(voz.motivo)}</p><p class="muted">Mientras tanto puedes usar el dictado de Windows: haz clic en el cuadro de texto y pulsa <strong>Windows + H</strong>.</p>`}
    </div>`;
  $("#copia").onclick = () => intentar(async () => { const r = await api("POST", "/api/copia-seguridad"); aviso("Copia guardada en " + r.ruta); });
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
})();
