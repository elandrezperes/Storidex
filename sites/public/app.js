const byId = id => document.getElementById(id);
const form = byId("brief");
const field = name => form.elements.namedItem(name);
const api = "/api/proyectos";
const notice = byId("notice");
let geography = {};
let busy = false;

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function options(select, values) {
  select.replaceChildren(...values.map(value => new Option(value, value)));
}

function locationField(id, name, values) {
  const input = element(values.length ? "select" : "input");
  input.name = name;
  input.required = name !== "nse";
  input.maxLength = 120;
  if (values.length) options(input, values);
  byId(id).replaceChildren(input);
  return input;
}

async function loadReferenceSources() {
  const response = await fetch("/referencias.json");
  if (!response.ok) throw new Error("No se pudo abrir el catálogo de referencias.");
  const catalog = await response.json();
  const sources = Object.entries(catalog.fuentes);
  const list = byId("reference-sources");
  for (const [, source] of sources) {
    const item = element("li");
    const link = element("a", source.nombre);
    Object.assign(link, {href: source.url, target: "_blank", rel: "noopener"});
    item.append(link, element("p", source.descripcion), element("p", source.aplicacion));
    item.append(element("small", source.modo === "consulta"
      ? "La búsqueda usa las páginas públicas disponibles. Su cobertura depende del mercado y del acceso a la fuente."
      : "Storidex utiliza patrones seleccionados de esta fuente para idear y revisar el guion."));
    list.append(item);
  }
  byId("add-reference").addEventListener("click", () => addReference(sources));
}

function addReference(sources) {
  const container = byId("reference-rows");
  if (container.children.length >= 12) return;
  const row = element("fieldset");
  row.append(element("legend", "Referencia"));
  const source = element("select");
  source.name = "ref_fuente";
  for (const [id, item] of sources) source.add(new Option(item.nombre, id));
  const field = (title, input) => {
    const label = element("label", title);
    label.append(input);
    row.append(label);
  };
  field("Fuente", source);
  for (const [name, label, type, maxLength] of [
    ["url", "Enlace de la pieza o consulta", "url", 1000],
    ["fecha", "Fecha de consulta", "date", 10],
    ["mercado", "País, ciudad o mercado", "text", 160],
    ["hallazgo", "Qué observaste", "text", 2000],
  ]) {
    const input = element(name === "hallazgo" ? "textarea" : "input");
    input.name = `ref_${name}`;
    if (input.tagName === "INPUT") input.type = type;
    input.maxLength = maxLength;
    field(label, input);
  }
  const remove = element("button", "Quitar referencia");
  remove.type = "button";
  remove.addEventListener("click", () => row.remove());
  row.append(remove);
  container.append(row);
}

function cities() {
  const provinces = geography[field("pais").value] ?? {};
  locationField("city", "ciudad", [...(provinces[field("provincia").value] ?? [])].sort());
}

function provinces() {
  const country = field("pais").value;
  const province = locationField("province", "provincia", Object.keys(geography[country] ?? {}).sort());
  province.addEventListener("change", cities);
  cities();

}

function addPerson() {
  const cast = byId("cast");
  const i = cast.children.length;
  if (i >= 5) return;
  const row = element("div");
  row.className = "participant-card";
  const avatar = element("span", "•");
  avatar.className = "participant-avatar";
  row.append(avatar);
  const name = element("label", `Nombre ${i + 1}`);
  const input = element("input");
  input.name = "participante";
  input.maxLength = 120;
  input.required = true;
  name.append(input);
  input.addEventListener("input", () => {
    avatar.textContent = input.value.trim().slice(0, 1).toUpperCase() || "•";
  });
  const lead = element("label");
  const check = element("input");
  check.type = "checkbox";
  check.checked = i === 0;
  lead.append(check, " Protagónico");
  row.append(name, lead);
  cast.append(row);
  help(name, "Escribe el nombre exacto que aparecerá en el guion.");
  help(lead, "Marca a quien lleva el conflicto principal.");
  if (i > 0) {
    const remove = element("button", "Quitar");
    remove.type = "button";
    remove.onclick = () => {
      row.remove();
      [...cast.children].forEach((item, index) => {
        item.querySelector("label").firstChild.textContent = `Nombre ${index + 1}`;
      });
    };
    row.append(remove);
  }
}

function setStep(step) {
  document.body.dataset.step = step;
  for (const item of document.querySelectorAll(".steps li")) {
    const number = +item.dataset.step;
    item.classList.toggle("active", number === step);
    item.classList.toggle("complete", number < step);
    if (number === step) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  }
}

function show(section) {
  byId("home").hidden = section !== "home";
  form.hidden = section !== "brief";
  byId("result").hidden = section !== "result";
  byId("home-link").hidden = section !== "result";
  if (section === "home") setStep(0);
  else if (section === "brief") setStep(byId("shape").hidden ? 1 : 2);
}

async function request(path = "", data) {
  const reply = await fetch(api + path, data === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const result = await reply.json();
  if (!reply.ok) throw new Error(result.error ?? "No se pudo completar la acción.");
  return result;
}

async function run(operation) {
  if (busy) return;
  busy = true;
  document.body.setAttribute("aria-busy", "true");
  const buttons = [...document.querySelectorAll("button:not(:disabled)")];
  buttons.forEach(button => { button.disabled = true; });
  notice.textContent = "";
  try {
    await operation();
    notice.textContent = "";
  } catch (error) {
    notice.textContent = error.message;
  } finally {
    busy = false;
    document.body.removeAttribute("aria-busy");
    buttons.forEach(button => { button.disabled = false; });
  }
}

function button(text, operation) {
  const action = element("button", text);
  action.addEventListener("click", () => run(operation));
  return action;
}

function phraseCards(result, project) {
  const choices = element("fieldset");
  choices.append(element("legend", "¿Qué frase se parece más a tu público?"));
  for (const [i, phrase] of project.frases.entries()) {
    const label = element("label");
    label.className = "choice";
    const radio = element("input");
    Object.assign(radio, {type: "radio", name: "frase", value: phrase, checked: i === 0});
    label.append(radio, " ", phrase);
    choices.append(label);
  }
  help(choices.querySelector("legend"), "Selecciona la frase que más se acerca a cómo habla tu público.");
  result.append(choices,
    button("Generar tres premisas", () => advance(project, "premisas", {
      frase: choices.querySelector(":checked").value,
    })),
    button("Continuar sin elegir", () => advance(project, "premisas")));
}

function premises(result, project) {
  const choices = element("fieldset");
  choices.className = "premise-choices";
  choices.append(element("legend", "Elige una premisa"));
  for (const [i, premise] of project.premisas.entries()) {
    const label = element("label");
    label.className = "choice";
    const radio = element("input");
    Object.assign(radio, {type: "radio", name: "premisa", value: premise.id, checked: i === 0});
    const letter = element("span", premise.id);
    letter.className = "premise-letter";
    label.append(radio, letter, element("strong", premise.proposicion));
    const details = element("details");
    details.append(element("summary", "MÁS DETALLES"));
    for (const [field, title] of [
      ["conflicto", "Conflicto"], ["recurso_visual", "Recurso visual"],
      ["desenlace", "Desenlace"], ["razon_estrategica", "Razón estratégica"],
    ]) {
      if (premise[field]) details.append(element("small", `${title} · ${premise[field]}`));
    }
    for (const reference of premise.referencias_creativas ?? []) {
      details.append(element("small", `Referencia · ${reference.titulo ?? reference.hallazgo ?? reference.aplicacion}`));
    }
    const option = element("div");
    option.className = "premise-option";
    option.append(label, details);
    choices.append(option);
  }
  help(choices.querySelector("legend"), "Elige la idea que dará forma a tu guion.");
  result.append(choices, button("Escribir el guion", () => prepare(project, {
    premisa: choices.querySelector(":checked").value,
  })));
}

function script(result, project) {
  const toolbar = element("div");
  toolbar.className = "script-toolbar";
  const viewer = element("article");
  viewer.className = "script-paper";
  viewer.setAttribute("aria-label", "Guion");
  for (const paragraph of project.guion) {
    const line = element("p", paragraph.texto);
    line.className = `script-${paragraph.tipo}`;
    if (paragraph.tc) {
      const time = element("span", paragraph.tc);
      time.className = "timecode";
      line.prepend(time);
    }
    viewer.append(line);
  }
  const editor = element("div");
  editor.className = "script-editor";
  editor.hidden = true;
  const edit = element("button", "Editar guion");
  edit.className = "secondary";
  edit.type = "button";
  edit.setAttribute("aria-expanded", "false");
  edit.addEventListener("click", () => {
    editor.hidden = !editor.hidden;
    viewer.hidden = !editor.hidden;
    edit.textContent = editor.hidden ? "Editar guion" : "Leer versión guardada";
    edit.setAttribute("aria-expanded", String(!editor.hidden));
  });
  toolbar.append(edit);
  result.append(toolbar, viewer, editor);
  const types = {scene_heading: "Escena", action: "Acción", character: "Personaje",
    parenthetical: "Acotación", dialogue: "Diálogo", transition: "Transición", title: "Rótulo"};
  const inputs = project.guion.map(p => {
    const label = element("label", [p.tc, types[p.tipo]].filter(Boolean).join(" · "));
    const input = element("textarea");
    input.value = p.texto;
    input.rows = p.tipo === "action" || p.tipo === "dialogue" ? 2 : 1;
    label.append(input);
    editor.append(label);
    help(label, "Edita este párrafo y guarda los cambios para actualizar el PDF.");
    return input;
  });
  const link = element("a", "Descargar PDF");
  link.href = `${api}/${project.id}/pdf`;
  const save = button("Guardar cambios", async () => {
    const updated = await request(`/${project.id}/editar`, {
      version: project.version, textos: inputs.map(input => input.value),
    });
    render(updated);
    byId("result").prepend(element("p", "Cambios guardados."));
  });
  inputs.forEach(input => input.addEventListener("input", () => {
    link.hidden = inputs.some((item, i) => item.value !== project.guion[i].texto);
  }));
  save.className = "secondary";
  editor.append(save);
  link.className = "download-button";
  toolbar.append(link);
  const production = element("details");
  production.append(element("summary", "Escuchar o llevar a Canva"));
  production.append(element("p", "Opcional. Estas acciones usan los créditos del servicio configurado."));
  for (const [key, action, label] of [["elevenlabs", "voz", "Preparar lectura sintética"],
    ["canva", "canva", project.media?.canva?.job_id ? "Consultar importación a Canva" : "Crear copia en Canva"]]) {
    const state = project.media?.[key];
    if (state?.status === "unknown" || state?.status === "submitting") {
      production.append(element("p", "La solicitud anterior no pudo confirmarse. Revisa el proveedor antes de repetirla."));
      continue;
    }
    if (key === "elevenlabs" && state?.status === "success") {
      const audio = element("audio");
      audio.controls = true;
      audio.preload = "none";
      audio.src = `${api}/${project.id}/audio`;
      production.append(audio, element("p", `${state.duration_s == null ? "" : state.duration_s.toFixed(1) + " s · "}Lectura sintética del diálogo. Excluye acciones, montaje y pausas de interpretación.`));
      continue;
    }
    if (key === "canva" && state?.edit_url) {
      const design = element("a", "Abrir copia editable en Canva");
      Object.assign(design, {href: state.edit_url, target: "_blank", rel: "noopener"});
      production.append(design);
      continue;
    }
    if (key === "canva" && state?.status === "failed") {
      production.append(element("p", "Canva no pudo importar este PDF. Puedes descargarlo e importarlo desde Canva."));
      continue;
    }
    const control = button(label, async () => {
      notice.textContent = key === "elevenlabs" ? "Preparando la lectura…" : "Preparando la copia editable…";
      render(await request(`/${project.id}/${action}`, {version: project.version}));
      notice.textContent = "";
    });
    control.disabled = !project.services?.[key]?.configured;
    production.append(control);
    if (control.disabled) production.append(element("small", "Este servicio aún no está activado en Storidex."));
  }
  result.append(production);
  reviewPanel(result, project);
}

function servicePanel(result, project) {
  const panel = element("details");
  panel.append(element("summary", "MÁS DETALLES · Herramientas y fuentes"));
  const labels = {ready: "Disponible", not_configured: "Pendiente de activación en Storidex",
    success: "Consulta completada", no_relevant_data: "Sin referencias pertinentes",
    unavailable: "Consulta no disponible", skipped: "Sin consulta en esta ejecución"};
  for (const service of Object.values(project.services ?? {})) {
    panel.append(element("p", `${service.name} · ${labels[service.status] ?? service.status}`));
    panel.append(element("small", service.purpose));
    if (service.fetched_at) panel.append(element("small", `Consultado: ${service.fetched_at}${service.cached ? " · Caché de hasta 24 horas" : ""}`));
  }
  for (const ref of project.references ?? []) {
    const link = element("a", ref.hallazgo);
    if (!/^https:\/\//.test(ref.url)) continue;
    Object.assign(link, {href: ref.url, target: "_blank", rel: "noopener"});
    const row = element("p", `${ref.fuente} · ${ref.nivel} · `);
    row.append(link, element("small", ` ${ref.fecha} · ${ref.origen} · Sin verificación de veracidad`));
    panel.append(row);
  }
  panel.append(element("p", "Las referencias orientan ideas. No prueban hábitos del público, demanda ni eficacia publicitaria."));
  result.append(panel);
}

function reviewPanel(result, project) {
  const panel = element("details");
  panel.append(element("summary", "MÁS DETALLES"));
  panel.append(element("p", "Consulta qué datos orientaron el guion y registra tu revisión si deseas."));
  const sourceStates = {
    referencias_disponibles: "Hay referencias para esta ejecución",
    patrones_disponibles: "Patrones del catálogo disponibles para este contexto",
    sin_datos_actuales: "Sin datos actuales para este contexto",
  };
  for (const tool of Object.values(project.herramientas ?? {})) {
    panel.append(element("p", `${tool.nombre} · ${sourceStates[tool.estado]}`));
    panel.append(element("small", tool.aplicacion));
  }
  const coverage = project.cobertura;
  if (coverage) panel.append(element("p", `Cobertura documental · ${coverage.campos_con_fuente} de ${coverage.campos_totales} campos. La procedencia no acredita veracidad.`));
  const claims = Object.entries(project.afirmaciones ?? {});
  for (const [id, claim] of claims) {
    const source = claim.respaldo;
    const text = Array.isArray(claim.afirmacion) ? claim.afirmacion.join(" / ") : claim.afirmacion;
    const origin = {observacion: "Observación documentada", declaracion_dueno: "Declaración del dueño",
      inferencia_ia: "Inferencia de IA"}[claim.origen];
    panel.append(element("p", `${id} · ${text} · ${origin}` +
      (source ? ` · ${source.informante}, ${source.fecha} · «${source.fragmento}»` : "")));
  }
  const trace = project.trazabilidad;
  for (const reference of trace?.referencias_creativas ?? []) {
    const link = element("a", reference.hallazgo ?? reference.aplicacion);
    Object.assign(link, {href: reference.url, target: "_blank", rel: "noopener"});
    const paragraph = element("p", "Referencia aplicada · ");
    paragraph.append(link);
    panel.append(paragraph);
  }
  for (const [criterion, note] of Object.entries(project.qa?.revision_creativa?.alertas ?? {})) {
    panel.append(element("p", `${criterion.replaceAll("_", " ")} · ${note}`));
  }
  if (trace?.razon_estrategica) panel.append(element("p", trace.razon_estrategica));
  for (const item of trace?.vinculos ?? []) {
    panel.append(element("p", `Vínculo propuesto · ${item.afirmaciones.join(", ")} · ${item.beat} · «${item.fragmento}»`));
  }
  if (project.qa?.duracion) {
    const time = project.qa.duracion;
    panel.append(element("p", `Estimaciones de duración · ${time.por_timecodes_s} s por timecodes · ${time.por_paginas_s} s por páginas`));
  }
  const production = project.qa?.realizabilidad;
  if (production) panel.append(element("p", production.recursos_declarados
    ? `Recursos declarados · ${production.recursos_declarados}` : "Recursos de producción pendientes de declarar."));
  if (production?.alerta_modelo) panel.append(element("p", `Alerta del modelo · ${production.alerta_modelo}`));
  for (const notice of project.qa?.avisos_estimacion ?? []) panel.append(element("p", notice));
  const fields = (label, input) => {
    const wrapper = element("label", label);
    wrapper.append(input);
    panel.append(wrapper);
    return input;
  };
  const reviewer = fields("Revisor", element("input"));
  const saveReview = async values => {
    const updated = await request(`/${project.id}/revisar`, {
      version: project.version, revisor: reviewer.value.trim(), ...values,
    });
    render(updated);
    byId("result").querySelector("details").open = true;
  };
  if (claims.length) {
    const claim = fields("Afirmación", element("select"));
    for (const [id] of claims) claim.add(new Option(id, id));
    const decision = fields("Dictamen", element("select"));
    for (const [id, label] of [
      ["aceptada", "Aceptar"], ["corregida", "Corregir"], ["retirada", "Retirar"],
    ]) decision.add(new Option(label, id));
    const note = fields("Corrección o nota", element("input"));
    panel.append(button("Guardar dictamen", () => saveReview({
      afirmacion: claim.value, decision: decision.value, nota: note.value,
    })));
  }
  const method = fields("Prueba de duración", element("select"));
  method.add(new Option("Lectura cronometrada", "lectura"));
  method.add(new Option("Animatic", "animatic"));
  const seconds = fields("Segundos del ensayo", element("input"));
  Object.assign(seconds, {type: "number", min: 0.1, max: 3600, step: 0.1});
  panel.append(button("Registrar ensayo", () => saveReview({metodo: method.value, segundos: +seconds.value})));
  for (const record of project.revision_humana ?? []) {
    panel.append(element("p", record.afirmacion
      ? `${record.revisor} · ${record.afirmacion} · ${record.decision} ${record.nota}`
      : `${record.revisor} · ${record.metodo} · ${record.segundos} s`));
  }
  result.append(panel);
}

function render(project) {
  const result = byId("result");
  const heading = element("div");
  heading.className = "page-heading";
  heading.append(element("p", project.marca));
  const title = project.agotado ? "Revisión del guion" : project.guion ? "Tu guion" : project.frases.length && !project.premisas.length
    ? "La voz de tu público" : "Elige tu historia";
  heading.append(element("h1", title));
  result.replaceChildren(heading);
  setStep(project.frases.length && !project.premisas.length ? 3 : 4);
  if (project.demostracion) result.append(element("p", "Modo de demostración"));
  if (project.guion) script(result, project);
  else if (project.agotado) {
    if (project.puede_revisar) {
      result.append(element("p", "Este proyecto se detuvo al revisar el mensaje clave. Ya puedes volver a revisarlo con la comprobación corregida."));
      result.append(button("Volver a revisar el guion", () => prepare(project)));
    } else {
      result.append(element("p", "El guion no superó las revisiones. Conservamos el diagnóstico de esta generación."));
    }
  }
  else if (project.preparado) result.append(button("Continuar preparando", () => prepare(project)));
  else if (project.premisas.length) premises(result, project);
  else if (project.frases.length) phraseCards(result, project);
  else result.append(button("Continuar", () => analyze(project)));
  servicePanel(result, project);
  show("result");
}

async function advance(project, action, data = {}) {
  notice.textContent = "Preparando tu guion...";
  renderProgress();
  try {
    render(await request(`/${project.id}/${action}`, data));
  } catch (error) {
    render(await request(`/${project.id}`));
    throw error;
  }
}

function renderProgress() {
  show("result");
  const working = element("div");
  working.className = "working";
  working.setAttribute("aria-hidden", "true");
  working.append(element("span"));
  byId("result").replaceChildren(working);
  byId("home-link").hidden = true;
}

async function analyze(project) {
  notice.textContent = "Preparando tu guion...";
  renderProgress();
  try {
    if (!project.investigado) {
      notice.textContent = "Revisando el mercado y las referencias para tu negocio…";
      project = await request(`/${project.id}/investigar`, {});
    }
    notice.textContent = "Preparando una propuesta de público a partir de tu información…";
    render(await request(`/${project.id}/persona`, {}));
  } catch (error) {
    render(await request(`/${project.id}`));
    throw error;
  }
}

async function prepare(project, selection) {
  notice.textContent = "Preparando tu guion...";
  renderProgress();
  try {
    if (project.agotado && project.puede_revisar) {
      project = await request(`/${project.id}/preparar`, {});
    }
    if (!project.preparado) project = await request(`/${project.id}/escaleta`, selection);
    while (!project.guion && !project.agotado) {
      project = await request(`/${project.id}/preparar`, {});
    }
    render(project);
  } catch (error) {
    render(await request(`/${project.id}`));
    throw error;
  }
}

async function home() {
  show("home");
  const projects = await request();
  if (!projects.length) {
    byId("projects").replaceChildren(element("li", "Tus guiones guardados aparecerán aquí."));
    return;
  }
  byId("projects").replaceChildren(...projects.map(project => {
    const item = element("li");
    item.append(button(project.marca, async () => render(await request(`/${project.id}`))));
    return item;
  }));
}

function shape(showShape) {
  setStep(showShape ? 2 : 1);
  byId("context").hidden = showShape;
  byId("shape").hidden = !showShape;
}

byId("start").addEventListener("click", () => {
  form.reset();
  byId("reference-rows").replaceChildren();
  for (const detail of form.querySelectorAll("details")) detail.open = false;
  updateAge();
  field("pais").value = geography.Ecuador ? "Ecuador" : "Otro país";
  provinces();
  byId("cast").replaceChildren();
  addPerson();
  shape(false);
  show("brief");
});
byId("add").addEventListener("click", addPerson);
byId("back").addEventListener("click", () => shape(false));
byId("home-link").addEventListener("click", () => run(home));
field("pais").addEventListener("change", provinces);
byId("next").addEventListener("click", () => {
  const fields = [...byId("context").querySelectorAll("input, select")];
  if (fields.some(input => !input.reportValidity())) return;
  if (!form.querySelector("[name=objetivo]:checked") || +field("min").value >= +field("max").value) {
    notice.textContent = "Elige un objetivo y un rango de edad creciente.";
    return;
  }
  notice.textContent = "";
  shape(true);
});
loadReferenceSources().catch(error => {
  byId("add-reference").disabled = true;
  byId("reference-sources").append(element("li", error.message));
});
form.addEventListener("submit", event => {
  event.preventDefault();
  run(async () => {
    const value = name => field(name).value.trim();
    const participants = [...byId("cast").children].map(row => ({
      nombre: row.querySelector("[name=participante]").value.trim(),
      protagonico: row.querySelector("[type=checkbox]").checked,
    }));
    if (participants.some(person => !person.nombre)) {
      throw new Error("Escribe el nombre de cada participante.");
    }
    if (!participants.some(person => person.protagonico)) {
      throw new Error("Marca al menos un participante como protagónico.");
    }
    const evidence = {origen: value("origen"), informante: value("informante"),
      fecha: value("fecha_evidencia"), fragmento: value("fragmento")};
    const hasEvidence = evidence.informante || evidence.fecha || evidence.fragmento;
    if (hasEvidence && !(evidence.informante && evidence.fecha && evidence.fragmento)) {
      throw new Error("Completa el informante, la fecha y el fragmento de evidencia.");
    }
    notice.textContent = "Validando el briefing…";
    const references = [...byId("reference-rows").children].map(row =>
      Object.fromEntries(["fuente", "url", "fecha", "mercado", "hallazgo"].map(key =>
        [key, row.querySelector(`[name="ref_${key}"]`).value.trim()])));
    const csv = field("trends_csv").files[0];
    if (csv?.size > 12000) throw new Error("El CSV supera el máximo de 12 000 bytes.");
    const project = await request("", {
      referencias: references,
      trends_csv: csv ? await csv.text() : "",
      marca: { nombre: value("marca"), producto: value("producto"), sitio_web: value("sitio") || null },
      ubicacion: { pais: value("pais"), provincia: value("provincia"), ciudad: value("ciudad") },
      segmento: { edad_min: +value("min"), edad_max: +value("max"), sexo: value("sexo"),
        nse: value("nse"), nse_escala_pais: null },
      objetivo: new FormData(form).getAll("objetivo"),
      forma: { participantes: participants, tipo: value("tipo"), tono: value("tono"),
        duracion_objetivo_s: +value("duracion"), especificaciones: value("frase"), mensaje_clave: value("mensaje"),
        indicaciones: value("indicaciones"), recursos: value("recursos") },
      evidencia_publico: hasEvidence ? [evidence] : [],
      competencia: { modo: value("competencia") },
    });
    render(project);
    await analyze(project);
  });
});

let helpId = 0;
function help(anchor, description) {
  const wrapper = element("span");
  wrapper.className = "help";
  const icon = element("button", "?");
  icon.type = "button";
  icon.setAttribute("aria-label", "Ayuda: " + (anchor.firstChild.textContent.trim() || anchor.textContent.trim()));
  const tip = element("span", description);
  tip.className = "help-tip";
  tip.id = `help-${++helpId}`;
  icon.setAttribute("aria-describedby", tip.id);
  icon.onclick = () => wrapper.classList.toggle("open");
  icon.onkeydown = event => {
    if (event.key === "Escape") wrapper.classList.remove("open");
  };
  wrapper.append(icon, tip);
  if (anchor.tagName === "LEGEND") anchor.append(wrapper);
  else {
    const container = element("div");
    container.className = "help-field";
    anchor.before(container);
    container.append(wrapper, anchor);
  }
}

const helpText = {
  marca: "Nombre exacto de la marca que debe aparecer en el guion.",
  producto: "Describe la oferta específica que quieres mostrar.",
  sitio: "Dirección web de la marca, si existe.",
  pais: "País donde se encuentra tu público.",
  provincia: "Provincia o estado donde se encuentra tu público.",
  ciudad: "Ciudad donde se encuentra tu público.",
  sexo: "Indica a quién va dirigido el video.",
  nse: "Elige la clase socioeconómica del público.",
  tipo: "En sketch la acción cuenta la historia. En publicitario se habla a cámara.",
  tono: "Elige cuánto registro local usará el diálogo.",
  duracion: "Selecciona la duración objetivo del reel.",
  competencia: "Elige qué se investigará para orientar el guion.",
  mensaje: "Escribe la idea que debe aparecer en el diálogo o en pantalla.",
  frase: "Escribe la frase que debe decirse textualmente.",
  indicaciones: "Añade condiciones sobre el lenguaje, la acción o lo que debe mostrarse.",
};
for (const label of form.querySelectorAll("label:not(.type-option):not(.chips label)")) {
  const input = label.querySelector("[name], #province, #city");
  const key = input?.name ?? {province: "provincia", city: "ciudad"}[input?.id];
  const copy = label.htmlFor === "age-min"
    ? "Mueve las dos manijas para fijar la edad mínima y máxima."
    : helpText[key];
  if (copy) help(label, copy);
}
help(form.querySelector(".objectives legend"), "Marca uno o más resultados que esperas del video.");

function updateAge(event) {
  const min = field("min");
  const max = field("max");
  if (+min.value >= +max.value) {
    if (event?.target === min) min.value = +max.value - 1;
    else max.value = +min.value + 1;
  }
  byId("ages").value = `${min.value}–${max.value} años`;
  const track = min.parentElement;
  track.style.setProperty("--min", `${100 * (min.value - 18) / 52}%`);
  track.style.setProperty("--max", `${100 * (max.value - 18) / 52}%`);
}
for (const edge of ["min", "max"]) field(edge).addEventListener("input", updateAge);
updateAge();

run(async () => {
  const reply = await fetch("/ubicaciones.json");
  if (!reply.ok) throw new Error("No se pudo cargar la lista de ubicaciones.");
  geography = await reply.json();
  options(field("pais"), [...Object.keys(geography).sort(), "Otro país"]);
  await home();
});
