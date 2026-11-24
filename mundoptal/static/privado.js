"use strict";
// Expediente privado de cada alumno: informes médicos, de gabinetes y resumen del diagnóstico.
// Va cifrado con una contraseña que solo conoce la maestra (ver mundoptal/privado.py).
// El testigo que da el servidor al abrirlo vive solo en esta variable (nunca en localStorage):
// al recargar la ventana o cerrar el programa hay que volver a escribir la contraseña.

let PRIV_TESTIGO = null;
let PRIV_ESTADO = null;
let PRIV_RELOJ = null;
let PRIV_ALUMNO = null;

class ErrorBloqueado extends Error {}

async function papi(metodo, url, cuerpo, crudo = false) {
  const op = { method: metodo, headers: {}, cache: "no-store" };
  if (USUARIO) op.headers["X-Usuario"] = String(USUARIO.id);
  if (PRIV_TESTIGO) op.headers["X-Privado"] = PRIV_TESTIGO;
  if (cuerpo instanceof FormData) op.body = cuerpo;
  else if (cuerpo !== undefined) { op.body = JSON.stringify(cuerpo); op.headers["Content-Type"] = "application/json"; }
  const r = await fetch(url, op);
  if (r.status === 423) { PRIV_TESTIGO = null; throw new ErrorBloqueado("El expediente privado se ha cerrado. Vuelve a escribir tu contraseña."); }
  if (crudo && r.ok) return r;
  const tipo = r.headers.get("Content-Type") || "";
  const datos = tipo.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((datos && datos.error) || "Error " + r.status);
  return datos;
}

// Como intentar(), pero si se ha cerrado vuelve a la pantalla de la contraseña
async function pintentar(fn) {
  try { return await fn(); } catch (e) {
    if (e instanceof ErrorBloqueado) { aviso(e.message); if (PRIV_ALUMNO) vistaPrivado(PRIV_ALUMNO); return; }
    aviso(e.message, true);
    throw e;
  }
}

const tamano = (n) => (n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");

function migasPrivado(al) {
  return `<div class="migas"><a href="#/alumnos">Alumnos</a> › <a href="#/alumno/${al.id}">${esc(al.nombre)}</a> › Expediente privado</div>`;
}

async function vistaPrivado(alumnoId) {
  PRIV_ALUMNO = alumnoId;
  clearInterval(PRIV_RELOJ);
  PRIV_ESTADO = await papi("GET", "/api/privado/estado");
  const al = await api("GET", `/api/alumnos/${alumnoId}`);
  if (!PRIV_ESTADO.configurado) return pintarCrearPrivado(al);
  if (!PRIV_ESTADO.abierto || !PRIV_TESTIGO) return pintarAbrirPrivado(al);
  let d;
  try { d = await papi("GET", `/api/privado/alumnos/${alumnoId}`); } catch (e) {
    if (e instanceof ErrorBloqueado) return pintarAbrirPrivado(al);
    throw e;
  }
  pintarExpediente(d);
}

// ------------------------------------------------------------------ primera vez: crear la contraseña
function pintarCrearPrivado(al) {
  vista.innerHTML = `${migasPrivado(al)}
    <div class="cabecera"><div><h1>🔒 Expediente privado</h1><p class="sub">Informes médicos, de gabinetes y diagnóstico de tus alumnos, en un sitio seguro.</p></div></div>
    <div class="tarjeta privado-candado">
      <h2>Crea tu contraseña del expediente privado</h2>
      <ul class="privado-lista">
        <li>Todo lo que guardes aquí (documentos y diagnóstico) se <strong>cifra</strong> con esta contraseña. Sin ella nadie puede leerlo: ni otra persona que use este ordenador o el programa, ni quien se lleve una copia de los datos.</li>
        <li>No sale del ordenador: no va a Internet, ni a Google, ni a Claude, ni en «Exportar mis datos».</li>
        <li>Es distinta de la de Windows. Usa una frase que recuerdes, de al menos ${PRIV_ESTADO.min_contrasena} caracteres.</li>
        <li>Se cierra solo tras ${PRIV_ESTADO.minutos} minutos sin usarlo y al cerrar el programa.</li>
      </ul>
      <form id="fcrear" class="campos" autocomplete="off">
        <div><label>Contraseña</label><input type="password" name="c1" required minlength="${PRIV_ESTADO.min_contrasena}" autocomplete="new-password"></div>
        <div><label>Repite la contraseña</label><input type="password" name="c2" required autocomplete="new-password"></div>
        <div class="campo-ancho"><button class="primario">🔒 Crear expediente privado</button></div>
      </form>
    </div>
    <div class="tarjeta"><h2>¿Ya lo usabas en otro ordenador?</h2>
      <p class="muted">Si en el otro ordenador pulsaste «Exportar expediente privado», carga aquí ese archivo .mpx con tu contraseña de siempre.</p>
      ${htmlImportarPrivado()}</div>`;
  $("#fcrear").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    if (f.c1.value !== f.c2.value) { aviso("Las dos contraseñas no coinciden", true); return; }
    pintentar(async () => {
      const r = await papi("POST", "/api/privado/configurar", { contrasena: f.c1.value });
      PRIV_TESTIGO = r.testigo;
      mostrarCodigo(r.codigo, () => vistaPrivado(al.id));
    });
  };
  enlazarImportarPrivado(al.id);
}

function mostrarCodigo(codigo, despues) {
  dialogo.innerHTML = `<form method="dialog" class="privado-dialogo">
    <h2>Apunta tu código de recuperación</h2>
    <p>Si algún día olvidas la contraseña, este código es <strong>la única forma</strong> de recuperar el expediente. Nadie más lo tiene (tampoco Gonzalo ni el programa).</p>
    <p class="codigo-recuperacion">${esc(codigo)}</p>
    <p class="muted">Escríbelo en papel y guárdalo en casa. No lo guardes en el ordenador ni en el móvil.</p>
    <label class="check"><input type="checkbox" id="apuntado"> Lo he apuntado en papel</label>
    <p class="acciones" style="margin-top:14px"><button class="primario" id="seguir" disabled>Continuar</button></p></form>`;
  dialogo.showModal();
  dialogo.oncancel = (e) => e.preventDefault();
  $("#apuntado").onchange = (e) => { $("#seguir").disabled = !e.target.checked; };
  $("#seguir").onclick = () => { dialogo.oncancel = null; dialogo.close(); despues(); };
}

// ------------------------------------------------------------------ abrir con la contraseña
function pintarAbrirPrivado(al) {
  vista.innerHTML = `${migasPrivado(al)}
    <div class="cabecera"><div><h1>🔒 Expediente privado</h1><p class="sub">${esc(al.nombre)}</p></div></div>
    <div class="tarjeta privado-candado">
      <h2>Escribe tu contraseña</h2>
      <p class="muted">El expediente está cerrado y cifrado. Al abrirlo podrás ver los de todos tus alumnos hasta que lo cierres o pasen ${PRIV_ESTADO.minutos} minutos sin usarlo.</p>
      <form id="fabrir" class="fila-form" autocomplete="off">
        <input type="password" name="c" required placeholder="Contraseña del expediente privado" autocomplete="current-password" autofocus>
        <button class="primario">🔓 Abrir</button>
      </form>
      <details class="privado-olvido"><summary>¿Has olvidado la contraseña?</summary>
        <form id="frecuperar" class="campos" autocomplete="off">
          <div class="campo-ancho"><label>Código de recuperación (el que apuntaste en papel)</label><input name="codigo" required placeholder="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"></div>
          <div><label>Contraseña nueva</label><input type="password" name="c1" required minlength="${PRIV_ESTADO.min_contrasena}" autocomplete="new-password"></div>
          <div><label>Repite la contraseña nueva</label><input type="password" name="c2" required autocomplete="new-password"></div>
          <div class="campo-ancho"><button>Poner contraseña nueva y abrir</button></div>
        </form></details>
    </div>`;
  const entrar = (r) => { PRIV_TESTIGO = r.testigo; vistaPrivado(al.id); };
  $("#fabrir").onsubmit = (e) => {
    e.preventDefault();
    const boton = e.target.querySelector("button");
    boton.disabled = true;
    pintentar(async () => entrar(await papi("POST", "/api/privado/abrir", { contrasena: e.target.c.value })))
      .catch(() => { e.target.c.select(); }).finally(() => { boton.disabled = false; });
  };
  $("#frecuperar").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    if (f.c1.value !== f.c2.value) { aviso("Las dos contraseñas no coinciden", true); return; }
    pintentar(async () => {
      entrar(await papi("POST", "/api/privado/abrir", { codigo: f.codigo.value, nueva: f.c1.value }));
      aviso("Contraseña cambiada. Tu código de recuperación sigue siendo el mismo.");
    });
  };
  setTimeout(() => { const c = $("#fabrir input"); if (c) c.focus(); }, 50);
}

// ------------------------------------------------------------------ el expediente abierto
function pintarExpediente(d) {
  const { alumno: al, ficha, documentos: docs } = d;
  const tipos = PRIV_ESTADO.tipos;
  const campos = PRIV_ESTADO.campos;
  const largos = new Set(["diagnostico", "otros_diagnosticos", "profesionales", "tratamiento", "alertas", "pautas", "notas"]);
  vista.innerHTML = `${migasPrivado(al)}
    <div class="cabecera"><div><h1>🔒 Expediente privado</h1><p class="sub">${esc(al.nombre)}${al.curso ? " · " + esc(al.curso) : ""}</p></div>
      <div class="acciones"><span class="muted" id="priv-reloj"></span><button id="priv-cerrar">🔒 Cerrar ahora</button></div></div>
    <div class="aviso-privado">🔐 Solo tú puedes ver esto. Está cifrado en este ordenador y no sale en exportaciones, informes ni en Claude.</div>

    <div class="tarjeta"><h2>🩺 Diagnóstico actual</h2>
      <p class="muted">Resumen de lo que dicen los informes. Se guarda solo al escribir.${ficha.actualizado ? ` Última modificación: ${esc(ficha.actualizado)}.` : ""}</p>
      <div class="campos" id="priv-ficha">
        ${campos.map(([k, t]) => largos.has(k)
          ? `<div class="campo-ancho"><label for="pf-${k}">${esc(t)} ${botonMicro("pf-" + k)}</label><textarea id="pf-${k}" data-pf="${k}" rows="${k === "diagnostico" || k === "pautas" ? 3 : 2}">${esc(ficha[k])}</textarea></div>`
          : `<div><label for="pf-${k}">${esc(t)}</label><input id="pf-${k}" data-pf="${k}" type="date" value="${esc(ficha[k])}"></div>`).join("")}
      </div></div>

    <div class="tarjeta"><h2>📂 Documentos oficiales (${docs.length})</h2>
      <p class="muted">Informes de psiquiatría, neurología, gabinetes, Orientación… en PDF, foto o Word. Se guardan cifrados dentro del programa: puedes borrar después las copias que tengas sueltas por el ordenador.</p>
      ${docs.length ? `<table class="tabla-adapt tabla-docs"><tr><th>Fecha</th><th>Tipo</th><th>Documento</th><th>Profesional o centro</th><th></th></tr>
        ${docs.map((x) => `<tr>
          <td>${x.fecha ? esc(fechaES(x.fecha)) : `<span class="muted">—</span>`}</td>
          <td><span class="chip">${esc(x.tipo_texto)}</span></td>
          <td><strong>${esc(x.titulo)}</strong><div class="muted">${esc(x.nombre)} · ${tamano(x.tamano)}</div>${x.notas ? `<div class="notas-doc">${esc(x.notas)}</div>` : ""}</td>
          <td>${esc(x.profesional)}</td>
          <td class="acciones-doc">
            ${x.mostrable ? `<button class="mini primario" data-ver="${x.id}">👁 Ver</button>` : `<button class="mini primario" data-fuera="${x.id}" title="Se abre con el programa del ordenador. La copia temporal se borra al cerrar el expediente.">📄 Abrir</button>`}
            <button class="mini" data-editar="${x.id}">✏️</button>
            <button class="mini peligro" data-borrar="${x.id}" title="Borrar">🗑</button></td></tr>`).join("")}</table>`
        : `<div class="vacio">Todavía no hay documentos. Añade el primero aquí debajo.</div>`}
      <form id="priv-subir" class="subir-doc">
        <h3>Añadir documentos</h3>
        <div class="campos">
          <div class="campo-ancho"><label>Archivo(s)</label><input type="file" name="archivo" multiple required accept=".pdf,.jpg,.jpeg,.png,.webp,.gif,.doc,.docx,.odt,.txt,.rtf"></div>
          <div><label>Tipo</label><select name="tipo">${tipos.map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select></div>
          <div><label>Fecha del informe</label><input type="date" name="fecha"></div>
          <div><label>Profesional o centro</label><input name="profesional" placeholder="p. ej. Neuropediatría del hospital"></div>
          <div><label>Título (opcional)</label><input name="titulo" placeholder="Si lo dejas vacío, el nombre del archivo"></div>
          <div class="campo-ancho"><label>Notas (opcional)</label><input name="notas" placeholder="Qué dice en resumen, próxima revisión…"></div>
        </div>
        <p style="margin:12px 0 0"><button class="primario">🔒 Guardar en el expediente</button></p>
      </form></div>

    <details class="tarjeta privado-ajustes"><summary><h2>⚙️ Contraseña y copias del expediente</h2></summary>
      <div class="rejilla-privado">
        <form id="priv-cambiar"><h3>Cambiar la contraseña</h3>
          <label>Contraseña actual</label><input type="password" name="actual" required autocomplete="current-password">
          <label>Contraseña nueva</label><input type="password" name="c1" required minlength="${PRIV_ESTADO.min_contrasena}" autocomplete="new-password">
          <label>Repite la nueva</label><input type="password" name="c2" required autocomplete="new-password">
          <p><button>Cambiar contraseña</button></p></form>
        <form id="priv-codigo"><h3>Nuevo código de recuperación</h3>
          <p class="muted">Si has perdido el papel. El código anterior dejará de servir.</p>
          <label>Contraseña</label><input type="password" name="c" required autocomplete="current-password">
          <p><button>Generar código nuevo</button></p></form>
        <div><h3>Pasar a otro ordenador o guardar copia</h3>
          <p class="muted">«Exportar mis datos» de Ajustes <strong>no</strong> incluye el expediente privado. Para llevarlo a otro ordenador o guardar una copia, exporta este archivo: sigue cifrado y se abre con la misma contraseña.</p>
          <p><button id="priv-exportar">📤 Exportar expediente privado</button></p>
          ${htmlImportarPrivado()}</div>
      </div></details>`;

  // Diagnóstico: guardado automático
  const pendientes = {};
  let espera = null;
  const guardar = () => pintentar(async () => {
    const cambios = { ...pendientes };
    Object.keys(pendientes).forEach((k) => delete pendientes[k]);
    if (Object.keys(cambios).length) await papi("PUT", `/api/privado/alumnos/${al.id}/ficha`, cambios);
  });
  $$("[data-pf]").forEach((c) => {
    if (c.tagName === "TEXTAREA") { autoAltura(c); c.addEventListener("input", () => autoAltura(c)); }
    const cambio = () => { pendientes[c.dataset.pf] = c.value; clearTimeout(espera); espera = setTimeout(guardar, 700); };
    c.addEventListener("input", cambio);
    c.addEventListener("change", cambio);
  });
  enlazarMicros($("#priv-ficha"));
  // el dictado escribe en el cuadro sin teclear: se guarda al salir del cuadro
  $$("#priv-ficha textarea").forEach((t) => t.addEventListener("blur", () => { pendientes[t.dataset.pf] = t.value; guardar(); }));

  // Documentos
  $("#priv-subir").onsubmit = (e) => {
    e.preventDefault();
    const boton = e.target.querySelector("button");
    boton.disabled = true;
    pintentar(async () => {
      const r = await papi("POST", `/api/privado/alumnos/${al.id}/documentos`, new FormData(e.target));
      aviso(r.ids.length === 1 ? "Documento guardado y cifrado ✔" : `${r.ids.length} documentos guardados y cifrados ✔`);
      vistaPrivado(al.id);
    }).finally(() => { boton.disabled = false; });
  };
  $$("[data-ver]").forEach((b) => b.onclick = () => pintentar(() => verDocumento(docs.find((x) => String(x.id) === b.dataset.ver))));
  $$("[data-fuera]").forEach((b) => b.onclick = () => pintentar(async () => {
    const r = await papi("POST", `/api/privado/documentos/${b.dataset.fuera}/abrir`);
    aviso(r.abierto ? "Abierto. La copia temporal se borra al cerrar el expediente." : "No se ha podido abrir con otro programa en este equipo.", !r.abierto);
  }));
  $$("[data-editar]").forEach((b) => b.onclick = () => editarDocumento(docs.find((x) => String(x.id) === b.dataset.editar), al.id));
  $$("[data-borrar]").forEach((b) => b.onclick = () => pintentar(async () => {
    const x = docs.find((y) => String(y.id) === b.dataset.borrar);
    if (!confirm(`¿Borrar «${x.titulo}» del expediente? No se puede deshacer.`)) return;
    await papi("DELETE", `/api/privado/documentos/${x.id}`);
    vistaPrivado(al.id);
  }));

  // Contraseña y copias
  $("#priv-cerrar").onclick = () => pintentar(async () => {
    await papi("POST", "/api/privado/cerrar");
    PRIV_TESTIGO = null;
    aviso("Expediente privado cerrado 🔒");
    vistaPrivado(al.id);
  });
  $("#priv-cambiar").onsubmit = (e) => {
    e.preventDefault();
    const f = e.target;
    if (f.c1.value !== f.c2.value) { aviso("Las dos contraseñas nuevas no coinciden", true); return; }
    pintentar(async () => { await papi("POST", "/api/privado/contrasena", { actual: f.actual.value, nueva: f.c1.value }); f.reset(); aviso("Contraseña cambiada ✔"); });
  };
  $("#priv-codigo").onsubmit = (e) => {
    e.preventDefault();
    pintentar(async () => { const r = await papi("POST", "/api/privado/codigo", { contrasena: e.target.c.value }); e.target.reset(); mostrarCodigo(r.codigo, () => {}); });
  };
  $("#priv-exportar").onclick = () => pintentar(async () => {
    if (window.pywebview) {
      const r = await papi("GET", "/api/privado/exportar?guardar=1");
      aviso("Expediente (cifrado) guardado en " + r.ruta);
    } else {
      const r = await papi("GET", "/api/privado/exportar", undefined, true);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob());
      a.download = (r.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "expediente_privado.mpx";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    }
  });
  enlazarImportarPrivado(al.id);
  arrancarReloj(d.segundos_restantes);
}

// Cuenta atrás visible; si se acaba, vuelve a la pantalla de la contraseña
let PRIV_FIN = 0;
// cualquier petición renueva el plazo en el servidor; aquí se renueva al escribir o pulsar en la vista
["input", "click"].forEach((ev) => vista.addEventListener(ev, () => {
  if (PRIV_TESTIGO && location.hash.startsWith("#/privado/")) PRIV_FIN = Date.now() + PRIV_ESTADO.minutos * 60000;
}, { passive: true }));

function arrancarReloj(segundos) {
  PRIV_FIN = Date.now() + segundos * 1000;
  const pintar = () => {
    const el = $("#priv-reloj");
    if (!el || !location.hash.startsWith("#/privado/")) { clearInterval(PRIV_RELOJ); return; }
    const quedan = Math.round((PRIV_FIN - Date.now()) / 1000);
    if (quedan <= 0) { clearInterval(PRIV_RELOJ); PRIV_TESTIGO = null; aviso("El expediente privado se ha cerrado solo 🔒"); vistaPrivado(PRIV_ALUMNO); return; }
    el.textContent = quedan < 120 ? `Se cierra en ${quedan} s` : `Se cierra solo en ${Math.ceil(quedan / 60)} min sin usarlo`;
  };
  pintar();
  PRIV_RELOJ = setInterval(pintar, 1000);
}

async function verDocumento(x) {
  const r = await papi("GET", `/api/privado/documentos/${x.id}`, undefined, true);
  const url = URL.createObjectURL(await r.blob());
  const contenido = x.mime.startsWith("image/") ? `<img src="${url}" alt="${esc(x.titulo)}">`
    : `<iframe src="${url}" title="${esc(x.titulo)}"></iframe>`;
  dialogo.innerHTML = `<div class="visor-doc">
      <div class="visor-cab"><strong>${esc(x.titulo)}</strong><span class="muted">${esc(x.tipo_texto)}${x.fecha ? " · " + esc(fechaES(x.fecha)) : ""}${x.profesional ? " · " + esc(x.profesional) : ""}</span>
        <button type="button" id="cerrar-visor">✕ Cerrar</button></div>
      <div class="visor-cuerpo">${contenido}</div></div>`;
  dialogo.classList.add("dialogo-visor");
  dialogo.showModal();
  const cerrar = () => { dialogo.close(); };
  dialogo.onclose = () => { URL.revokeObjectURL(url); dialogo.classList.remove("dialogo-visor"); dialogo.innerHTML = ""; dialogo.onclose = null; };
  $("#cerrar-visor").onclick = cerrar;
}

function editarDocumento(x, alumnoId) {
  dialogo.innerHTML = `<form method="dialog" id="feditar-doc" class="privado-dialogo">
    <h2>Datos del documento</h2>
    <div class="campos">
      <div class="campo-ancho"><label>Título</label><input name="titulo" value="${esc(x.titulo)}"></div>
      <div><label>Tipo</label><select name="tipo">${PRIV_ESTADO.tipos.map(([k, t]) => `<option value="${k}" ${k === x.tipo ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
      <div><label>Fecha del informe</label><input type="date" name="fecha" value="${esc(x.fecha)}"></div>
      <div class="campo-ancho"><label>Profesional o centro</label><input name="profesional" value="${esc(x.profesional)}"></div>
      <div class="campo-ancho"><label>Notas</label><textarea name="notas" rows="3">${esc(x.notas)}</textarea></div>
    </div>
    <p class="acciones" style="margin-top:14px"><button class="primario" value="ok">Guardar</button><button value="cancelar" formnovalidate>Cancelar</button></p></form>`;
  dialogo.showModal();
  $("#feditar-doc").onsubmit = (e) => {
    if (e.submitter && e.submitter.value === "cancelar") return;
    const datos = Object.fromEntries(new FormData(e.target));
    pintentar(async () => { await papi("PATCH", `/api/privado/documentos/${x.id}`, datos); vistaPrivado(alumnoId); });
  };
}

function htmlImportarPrivado() {
  return `<form id="priv-importar" class="fila-form" autocomplete="off">
    <input type="file" name="archivo" accept=".mpx" required>
    <input type="password" name="contrasena" required placeholder="Contraseña de ese expediente" autocomplete="off">
    <button>📥 Importar</button></form>`;
}

function enlazarImportarPrivado(alumnoId) {
  const f = $("#priv-importar");
  if (!f) return;
  f.onsubmit = (e) => {
    e.preventDefault();
    if (PRIV_ESTADO.configurado && !confirm("Se sustituirá el expediente privado de este ordenador por el del archivo. El actual se guarda antes como copia. ¿Seguir?")) return;
    pintentar(async () => {
      const r = await papi("POST", "/api/privado/importar", new FormData(f));
      PRIV_TESTIGO = r.testigo;
      aviso("Expediente privado importado ✔");
      vistaPrivado(alumnoId);
    });
  };
}
