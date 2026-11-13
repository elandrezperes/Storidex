"""Storidex · aplicación utilizable de extremo a extremo.

Formulario vacío, menús en cascada y generación a partir de los datos del
usuario. En modo seco responde el motor local (core/local.py): cualquier marca
obtiene un resultado distinto y coherente con lo que escribió.
"""
from __future__ import annotations

import json
import os
import tempfile

import streamlit as st

from core import export_fdx, export_pdf, levels, llm
from core.phases import (p0_brief, p1_research, p2_persona, p3_premisas,
                         p4_escaleta, p5_guion, p6_qa)

PAPEL = "#EDE6D8"
TINTA = "#12202D"
AZUL = "#1C3F94"
MUSGO = "#3E6B4A"
AMBAR = "#A9761F"
GRIS = "#4A4438"

st.set_page_config(page_title="Storidex", page_icon="◼", layout="centered")

st.markdown(f"""
<style>
  .stApp {{ background: {PAPEL}; }}
  html, body, [class*="css"] {{ color: {TINTA}; }}

  /* etiquetas de los controles con contraste suficiente sobre el papel */
  label, .stSelectbox label, .stTextInput label, .stTextArea label,
  .stSlider label, .stRadio label, .stMultiSelect label,
  [data-testid="stWidgetLabel"] p {{
      color: {TINTA} !important; font-weight: 500 !important;
  }}
  input, textarea, .stSelectbox div[data-baseweb="select"] {{
      color: {TINTA} !important;
  }}
  .stCaption, [data-testid="stCaptionContainer"] p {{ color: {GRIS} !important; }}
  p, span, li, .stMarkdown {{ color: {TINTA}; }}
  [data-testid="stMarkdownContainer"] p {{ color: {TINTA} !important; }}

  h1, h2, h3, h4, h5 {{ color: {TINTA} !important; letter-spacing: -0.02em; }}

  .marca {{ font-size: 2.6rem; font-weight: 700; letter-spacing: -0.03em;
            margin-bottom: 0; color: {TINTA} !important; }}
  .marca span {{ color: {AZUL}; }}
  .sub {{ color: {GRIS} !important; margin-top: -0.4rem; margin-bottom: 1.4rem; }}

  .pill {{ display:inline-block; padding:.16rem .58rem; border-radius:999px;
           font-size:.7rem; font-weight:600; color:#fff; margin-left:.3rem; }}
  .ver {{ background:{MUSGO}; }}
  .inf {{ background:{AMBAR}; }}

  .card {{ background:#FCF8EF; border:1px solid #D5CBB6; border-radius:14px;
           padding:.9rem 1.05rem; margin-bottom:.7rem; color:{TINTA} !important; }}
  .card b {{ color:{TINTA} !important; }}
  .gris {{ color:{GRIS} !important; }}

  .mono {{ font-family: ui-monospace, "Courier New", monospace; font-size:.84rem;
           white-space:pre-wrap; line-height:1.5; color:{TINTA} !important; }}

  .stButton>button {{ background:{AZUL}; color:#fff; border:none; border-radius:11px;
                      padding:.55rem 1.1rem; font-weight:600; }}
  .stButton>button p, .stButton>button span, .stButton>button div {{
      color:#fff !important; font-weight:600 !important; }}
  .stButton>button:hover {{ background:#12294E; }}
  .stButton>button:disabled {{ background:#B9B0A0 !important; opacity:1 !important; }}
  .stButton>button:disabled p, .stButton>button:disabled span {{
      color:#6B6355 !important; }}

  div[data-testid="stMetricValue"] {{ color:{AZUL}; }}
  .stAlert p {{ color:{TINTA} !important; }}
</style>
""", unsafe_allow_html=True)

SS = st.session_state
for k, v in {
    "pantalla": 1, "brief": None, "research": None, "persona": None,
    "premisas": None, "escaleta": None, "guion": None, "qa": None,
    "ruta": None, "premisa_elegida": "B",
    "autenticado": False, "guiones_sesion": 0,
}.items():
    SS.setdefault(k, v)


# ============================================================ ACCESO
from core import auth  # noqa: E402

if auth.hay_que_autenticarse() and not SS["autenticado"]:
    st.markdown('<p class="marca">STORYDEX<span>.</span></p>', unsafe_allow_html=True)
    st.markdown('<p class="sub">Acceso restringido · Modelo MIIA</p>',
                unsafe_allow_html=True)
    st.info("Esta es una versión de evaluación. Introduce la clave que te compartieron.")

    with st.form("acceso"):
        intento = st.text_input("Clave de acceso", type="password",
                                placeholder="••••••••")
        if st.form_submit_button("Entrar", use_container_width=True):
            if auth.verificar(intento):
                SS["autenticado"] = True
                st.rerun()
            else:
                st.error("La clave no es correcta.")
    st.stop()


# ------------------------------------------------------------------ helpers
@st.cache_data
def ubicaciones() -> dict:
    ruta = os.path.join(os.path.dirname(__file__), "core", "data", "ubicaciones.json")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def cabecera(paso: str | None = None):
    st.markdown('<p class="marca">STORYDEX<span>.</span></p>', unsafe_allow_html=True)
    st.markdown('<p class="sub">Guiones que saben a quién le hablan · Modelo MIIA</p>',
                unsafe_allow_html=True)
    if paso:
        st.caption(paso)


def badge(nivel: str) -> str:
    cls = "ver" if levels.es_verificado(nivel) else "inf"
    return f'<span class="pill {cls}">{nivel}</span>'


def reiniciar():
    for k in ("brief", "research", "persona", "premisas", "escaleta",
              "guion", "qa", "ruta", "premisa_elegida"):
        SS[k] = None
    SS["premisa_elegida"] = "B"
    SS["pantalla"] = 2


def guardar_ejecucion():
    """Persiste los artefactos de la ejecución en disco."""
    if not SS.get("ruta"):
        return
    pares = (("research.json", SS.get("research")), ("persona.json", SS.get("persona")),
             ("premisas.json", SS.get("premisas")), ("escaleta.json", SS.get("escaleta")),
             ("guion.json", SS.get("guion")), ("qa.json", SS.get("qa")))
    for nombre, datos in pares:
        if datos:
            with open(os.path.join(SS["ruta"], nombre), "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
    if SS.get("guion") and SS.get("brief"):
        export_fdx.guardar(SS["guion"], SS["brief"],
                           os.path.join(SS["ruta"], "guion.fdx"))
        export_pdf.generar(SS["guion"], SS["brief"],
                           os.path.join(SS["ruta"], "guion.pdf"))


# ============================================================ 1. BIENVENIDA
if SS["pantalla"] == 1:
    cabecera()

    if not llm.hay_llave() and not llm.DRY:
        st.error("**Falta la llave de API.** Sin ella el sistema no puede escribir guiones: "
                 "no hay ningún contenido preparado de antemano que pueda mostrarte.")
        st.markdown("""
**Para activarlo, dos minutos:**

1. Entra en `platform.openai.com` → *API keys* → **Create new secret key**
2. Copia la llave (empieza por `sk-`) y guárdala, solo se muestra una vez
3. En la carpeta del proyecto, crea un archivo llamado `.env` con esta línea:

```
OPENAI_API_KEY=sk-tu-llave-aqui
```

4. Reinicia la aplicación: `Ctrl + C` en la terminal y otra vez `streamlit run app.py`

El costo es de centavos: un guion completo ronda **0,02 USD**. Con 5 dólares
puedes generar unos 250 guiones.

**Opcional:** si además añades `GEMINI_API_KEY`, la fase de investigación busca
competencia real en la web con fuentes citables. Sin ella, el sistema escribe
igual, pero declara el análisis de competencia como no disponible en vez de
inventarlo.
""")
        st.stop()

    st.success(f"**Listo.** Modelo de redacción: `{llm.MODEL_WRITE}`"
               + (f" · investigación con `{llm.MODEL_RESEARCH}`" if llm.hay_gemini()
                  else " · sin búsqueda web (falta GEMINI_API_KEY)"))

    st.markdown("### Empieza con tu marca")
    st.caption("Un briefing de dos minutos. Al final obtienes el guion en formato profesional.")

    if st.button("Crear un guion", use_container_width=True):
        reiniciar()
        SS["pantalla"] = 2
        st.rerun()

    # proyectos guardados
    if os.path.isdir("runs"):
        guardados = sorted((d for d in os.listdir("runs")
                            if os.path.isfile(os.path.join("runs", d, "brief.json"))),
                           reverse=True)
    else:
        guardados = []

    if guardados:
        st.divider()
        st.markdown("**Proyectos guardados**")
        elegido = st.selectbox("Proyecto", guardados, label_visibility="collapsed")
        if st.button("Abrir proyecto", use_container_width=True):
            base = os.path.join("runs", elegido)
            with open(os.path.join(base, "brief.json"), encoding="utf-8") as f:
                SS["brief"] = json.load(f)
            SS["ruta"] = base
            for nombre, clave in (("research.json", "research"), ("persona.json", "persona"),
                                  ("premisas.json", "premisas"), ("escaleta.json", "escaleta"),
                                  ("guion.json", "guion"), ("qa.json", "qa")):
                p = os.path.join(base, nombre)
                if os.path.isfile(p):
                    with open(p, encoding="utf-8") as f:
                        SS[clave] = json.load(f)
            SS["pantalla"] = 4 if SS["guion"] else (4 if SS["premisas"] else 2)
            st.rerun()

    st.divider()
    st.caption("Storidex · prototipo de tesis · Modelo MIIA · Cuenca, Ecuador")

# ============================================================ 2. CONTEXTO
elif SS["pantalla"] == 2:
    cabecera("Paso 1 de 3 · Contexto")

    geo = ubicaciones()
    paises = sorted(geo.keys()) + ["Otro país"]

    st.markdown("**Tu marca**")
    c1, c2 = st.columns(2)
    marca = c1.text_input("Nombre de la marca *", placeholder="Ej. Café Tomebamba")
    producto = c2.text_input("Producto o servicio *",
                             placeholder="Ej. Café de especialidad tostado en casa")

    st.markdown("**Dónde opera**")
    c3, c4, c5 = st.columns(3)
    pais = c3.selectbox("País *", paises, index=paises.index("Ecuador"))

    if pais == "Otro país":
        provincia = c4.text_input("Provincia o estado *", placeholder="Ej. Valparaíso")
        ciudad = c5.text_input("Ciudad *", placeholder="Ej. Viña del Mar")
    else:
        provincias = sorted(geo[pais].keys())
        provincia = c4.selectbox("Provincia *", provincias, index=0)
        ciudades = sorted(geo[pais][provincia])
        ciudad = c5.selectbox("Ciudad *", ciudades, index=0)

    st.markdown("**A quién le hablas**")
    edad = st.slider("Rango de edad *", 18, 70, (25, 40),
                     help="Arrastra los dos extremos para acotar el público.")
    c6, c7 = st.columns(2)
    sexo = c6.selectbox("Sexo *", ["ambos", "f", "m"],
                        format_func=lambda v: {"ambos": "Ambos", "f": "Femenino",
                                               "m": "Masculino"}[v])
    nse = c7.selectbox("Segmento socioeconómico *",
                       ["A", "B", "C+", "C-", "D"], index=2,
                       help="Escala de referencia para Ecuador.")

    st.markdown("**Qué buscas con el video**")
    objetivo = st.multiselect(
        "Objetivo *", ["views", "cta", "ventas", "seguidores"], default=[],
        format_func=lambda v: {"views": "Más visualizaciones", "cta": "Un llamado a la acción",
                               "ventas": "Ventas", "seguidores": "Seguidores"}[v])

    sitio = st.text_input("Sitio web (opcional)", placeholder="Ej. cafetomebamba.ec")

    st.divider()
    faltan = []
    if not marca.strip():
        faltan.append("el nombre de la marca")
    if not producto.strip():
        faltan.append("el producto o servicio")
    if not objetivo:
        faltan.append("al menos un objetivo del video")
    if isinstance(provincia, str) and not provincia.strip():
        faltan.append("la provincia")
    if isinstance(ciudad, str) and not ciudad.strip():
        faltan.append("la ciudad")

    if faltan:
        st.warning("Falta " + ", ".join(faltan) + ".")

    c_izq, c_der = st.columns([1, 1])
    if c_der.button("Continuar →", use_container_width=True, disabled=bool(faltan)):
        SS["brief"] = {
            "marca": {"nombre": marca.strip(), "producto": producto.strip(),
                      "sitio_web": sitio.strip() or None},
            "ubicacion": {"pais": pais, "provincia": provincia, "ciudad": ciudad},
            "segmento": {"edad_min": edad[0], "edad_max": edad[1], "sexo": sexo,
                         "nse": nse, "nse_escala_pais": "EC"},
            "objetivo": objetivo,
            "forma": {},
            "competencia": {"modo": "ambas"},
        }
        SS["pantalla"] = 3
        st.rerun()
    if c_izq.button("← Volver", use_container_width=True):
        SS["pantalla"] = 1
        st.rerun()

# ============================================================ 3. FORMA
elif SS["pantalla"] == 3:
    cabecera("Paso 2 de 3 · Forma")
    b = SS["brief"] or {}

    st.markdown("**Quiénes aparecen**")
    n = st.number_input("Número de participantes", min_value=1, max_value=5, value=1,
                        help="Después puedes nombrarlos.")
    participantes = []
    for i in range(int(n)):
        c1, c2 = st.columns([2, 1])
        nombre = c1.text_input(f"Nombre {i + 1} *", key=f"nom_{i}",
                               placeholder="Ej. Ana" if i == 0 else "Ej. Diego")
        prota = c2.checkbox("Protagónico", value=(i == 0), key=f"prot_{i}")
        if nombre.strip():
            participantes.append({"nombre": nombre.strip(), "protagonico": prota})

    st.markdown("**Cómo se cuenta**")
    tipo = st.radio("Tipo de video *", ["sketch", "publicitario"], horizontal=True,
                    help="Sketch: los personajes no saben que hay cámara. "
                         "Publicitario: se habla a cámara de forma sostenida.")

    especificaciones = st.text_area(
        "Frase que debe decirse literalmente (opcional)",
        placeholder="Ej. Tostamos aquí, no importamos")
    indicaciones = st.text_area(
        "Indicaciones para el guionista (opcional)",
        placeholder="Ej. Sin humor de doble sentido. El producto debe verse desde el primer segundo.")

    tono = st.radio("Tono *", ["neutro", "moderado", "marcado"], index=1, horizontal=True,
                    help="Marcado usa vocabulario y giros locales sin caricatura.")
    duracion = st.radio("Duración *", [15, 30, 45, 60], index=1, horizontal=True,
                        format_func=lambda v: f"{v} s")

    st.markdown("**Espacio escénico**")
    st.caption("Dónde ocurre y a qué hora. Es lo que va en el encabezado de cada escena.")
    from core import espacio as esp_mod

    modo_esp = st.radio(
        "¿Quién decide el espacio? *", ["auto", "fijo"], horizontal=True,
        format_func=lambda v: "Que lo decida el guionista" if v == "auto" else "Lo defino yo",
        help="Si lo dejas al guionista, el sistema propone el espacio según el rubro.")

    espacio_brief = {"modo": "auto"}
    if modo_esp == "fijo":
        c_e1, c_e2, c_e3 = st.columns([1, 2, 1])
        tipo_esp = c_e1.selectbox("Tipo *", list(esp_mod.TIPOS.keys()),
                                  format_func=lambda k: esp_mod.TIPOS[k])
        local_esp = c_e2.text_input("Localización *", placeholder="Ej. LOCAL, ESTUDIO, CALLE")
        momento_esp = c_e3.selectbox("Momento *", esp_mod.MOMENTOS, index=2)

        if local_esp.strip():
            vista = esp_mod.construir(tipo_esp, local_esp, momento_esp)
            st.caption(f"Encabezado: **{esp_mod.encabezado(vista)}**")
            espacio_brief = {"modo": "fijo", **vista}
        else:
            st.caption("Escribe la localización para ver el encabezado.")

    competencia = st.selectbox(
        "Análisis de competencia *", ["ambas", "marca", "feed", "ninguna"],
        format_func=lambda v: {"ambas": "Contra quién y contra qué compito",
                               "marca": "Contra quién compito (otras marcas)",
                               "feed": "Contra qué compito (qué gana atención)",
                               "ninguna": "Omitir este paso"}[v])

    st.divider()
    faltan = []
    if modo_esp == "fijo" and not local_esp.strip():
        faltan.append("la localización del espacio escénico")
    if not participantes:
        faltan.append("al menos un participante con nombre")
    elif not any(p["protagonico"] for p in participantes):
        faltan.append("marcar un participante como protagónico")
    if faltan:
        st.warning("Falta " + ", ".join(faltan) + ".")

    c_izq, c_der = st.columns([1, 1])
    if c_der.button("Generar guion →", use_container_width=True, disabled=bool(faltan)):
        b["forma"] = {
            "participantes": participantes,
            "tipo": tipo,
            "especificaciones": especificaciones.strip(),
            "indicaciones": indicaciones.strip(),
            "tono": tono,
            "duracion_objetivo_s": duracion,
        }
        b["competencia"] = {"modo": competencia}
        b["espacio"] = espacio_brief

        fase = {"nombre": "validar el briefing"}
        try:
            with st.spinner("Validando el briefing…"):
                fase["nombre"] = "validar el briefing"
                brief_ok, ruta = p0_brief.ejecutar(b)
            with st.spinner("Analizando el mercado…"):
                fase["nombre"] = "analizar el mercado"
                res = p1_research.ejecutar(brief_ok)
            with st.spinner("Construyendo el destinatario…"):
                fase["nombre"] = "construir el destinatario"
                per = p2_persona.ejecutar(brief_ok, res)
            with st.spinner("Proponiendo premisas…"):
                fase["nombre"] = "proponer las premisas"
                pre = p3_premisas.ejecutar(brief_ok, per, res,
                                           p2_persona.inyectar(brief_ok, per))
        except llm.SinLlave as e:
            st.error(f"Falta la llave de API: {e}")
            st.stop()
        except llm.CosteExcedido as e:
            st.error(f"Se detuvo por control de gasto: {e}")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude {fase['nombre']}. Vuelve a intentarlo; si sigue fallando, "
                     f"cambia el tono o la duración y prueba otra vez.")
            with st.expander("Detalle técnico"):
                st.code(f"{type(e).__name__}: {e}")
            st.stop()

        SS.update(brief=brief_ok, ruta=ruta, research=res, persona=per, premisas=pre)
        SS["pantalla"] = 4
        st.rerun()

    if c_izq.button("← Volver", use_container_width=True):
        SS["pantalla"] = 2
        st.rerun()

# ============================================================ 4. RESULTADO
else:
    cabecera("Paso 3 de 3 · Premisas y guion")
    b, per, res = SS["brief"], SS["persona"], SS["research"]

    # ---------------------------------------------------------- competencia
    st.markdown(f"#### Análisis · {b['marca']['nombre']}")
    if res["competencia"]["sin_datos"]:
        st.warning("Sin competidores con fuente verificable. El análisis se declara "
                   "inferido, no inventado.")
    for c in res["competencia"]["de_marca"]:
        st.markdown(
            f'<div class="card"><b>{c["nombre"]}</b>{badge(c["nivel"])}<br>'
            f'<span class="gris">{c["descripcion"]}</span></div>', unsafe_allow_html=True)
    for f in res["competencia"]["de_feed"]:
        st.markdown(
            f'<div class="card"><b>{f["patron"]}</b>{badge(f["nivel"])}<br>'
            f'<span class="gris">{f["ejemplo"]}</span></div>', unsafe_allow_html=True)
    st.success(f"Oportunidad: {res['oportunidad']['texto']}")

    # ---------------------------------------------------------- persona
    st.markdown("#### A quién le hablas")
    st.caption(levels.resumen(per))
    cc = st.columns(2)
    cc[0].markdown(f"**{per['perfil']['nombre']}, {per['perfil']['edad']}**  \n"
                   f"{per['perfil']['ocupacion']}, {per['perfil'].get('barrio','')}")
    cc[1].markdown(f"**Objeción a desactivar**  \n{per['conflicto']['objecion']}")
    st.markdown("**Frases que diría**  \n" +
                "  \n".join(f"— *{f}*" for f in per["lenguaje"]["diria"]))
    st.markdown(f"**No le hablas a:** {per['anti_persona']['quien_no_es']}")
    with st.expander("Ficha completa con niveles de procedencia"):
        st.json(per)

    # ---------------------------------------------------------- premisas
    st.divider()
    st.markdown("#### Elige una premisa")
    for p in SS["premisas"]["premisas"]:
        st.markdown(
            f'<div class="card"><b>{p["id"]}.</b> {p["proposicion"]}{badge(p["nivel"])}<br>'
            f'<span class="gris">{p["caracter"]}</span></div>', unsafe_allow_html=True)

    elegida = st.radio("Premisa", ["A", "B", "C"], horizontal=True,
                       index=["A", "B", "C"].index(SS["premisa_elegida"]))

    # tope de guiones por sesión (protege los créditos si la app es pública)
    permitido, aviso_tope = auth.puede_generar(SS["guiones_sesion"])
    if aviso_tope and auth.tope_sesion() > 0:
        (st.caption if permitido else st.warning)(aviso_tope)

    if st.button("Escribir el guion", use_container_width=True, disabled=not permitido):
        prem = next(p for p in SS["premisas"]["premisas"] if p["id"] == elegida)
        txt = p2_persona.inyectar(b, per)
        try:
            with st.spinner("Armando la escaleta…"):
                esc = p4_escaleta.ejecutar(b, prem, txt)
            with st.spinner("Escribiendo…"):
                gu = p5_guion.ejecutar(b, per, prem, esc, txt)
            qa = p6_qa.ejecutar(b, per, gu, esc)
            if qa["hallazgos"]:
                with st.spinner("Corrigiendo lo que marca el control…"):
                    gu = p5_guion.ejecutar(b, per, prem, esc, txt,
                                           correccion=p6_qa.correccion_para(gu, qa))
                    qa = p6_qa.ejecutar(b, per, gu, esc)
        except llm.CosteExcedido as e:
            st.error(f"Se detuvo por control de gasto: {e}")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error("No pude escribir el guion. Vuelve a pulsar el botón.")
            with st.expander("Detalle técnico"):
                st.code(f"{type(e).__name__}: {e}")
            st.stop()
        SS["guiones_sesion"] = SS.get("guiones_sesion", 0) + 1
        SS.update(premisa_elegida=elegida, escaleta=esc, guion=gu, qa=qa)
        guardar_ejecucion()
        st.rerun()

    # ---------------------------------------------------------- guion
    if SS["guion"]:
        st.divider()
        st.markdown("#### Guion")

        lineas = []
        for p in SS["guion"]["parrafos"]:
            t = p["tipo"]
            if t == "scene_heading":
                lineas.append(f"{p.get('tc','')}  {p['texto'].upper()}")
            elif t == "character":
                lineas.append(f"\n{' ' * 12}{p['texto'].upper()}")
            elif t == "parenthetical":
                lineas.append(f"{' ' * 8}{p['texto']}")
            elif t == "dialogue":
                lineas.append(f"{' ' * 4}{p['texto']}")
            elif t == "transition":
                lineas.append(f"\n{' ' * 22}{p['texto'].upper()}")
            elif t == "title":
                lineas.append(f"\n{' ' * 14}{p['texto'].upper()}")
            else:
                lineas.append(f"\n{p['texto']}")
        st.markdown('<div class="card"><div class="mono">' +
                    "\n".join(lineas).replace("<", "&lt;") + "</div></div>",
                    unsafe_allow_html=True)

        # control de calidad
        st.markdown("#### Control de calidad")
        qa = SS["qa"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Duración estimada", f"{qa['duracion']['por_timecodes_s']} s",
                  f"objetivo {qa['duracion']['objetivo_s']} s")
        m2.metric("Por páginas", f"{qa['duracion']['por_paginas_s']} s")
        m3.metric("Cuarta pared", qa["cuarta_pared"]["detectada"])

        if qa["hallazgos"]:
            for h in qa["hallazgos"]:
                st.warning(h)
        else:
            st.success("Todas las verificaciones pasan.")
        st.caption("Ambas cifras son estimaciones: una suma los códigos de tiempo de la "
                   "escaleta, la otra aplica la convención de una página por minuto.")

        # exportar
        st.markdown("#### Exportar")
        tmp = tempfile.mkdtemp()
        ruta_fdx = os.path.join(tmp, "guion.fdx")
        ruta_pdf = os.path.join(tmp, "guion.pdf")
        export_fdx.guardar(SS["guion"], b, ruta_fdx)
        export_pdf.generar(SS["guion"], b, ruta_pdf)

        e1, e2 = st.columns(2)
        with open(ruta_fdx, "rb") as f:
            e1.download_button("Descargar .fdx", f.read(),
                               f"{b['marca']['nombre'][:20]}.fdx",
                               mime="application/xml", use_container_width=True)
        with open(ruta_pdf, "rb") as f:
            e2.download_button("Descargar PDF", f.read(),
                               f"{b['marca']['nombre'][:20]}.pdf",
                               mime="application/pdf", use_container_width=True)

        with st.expander("Ver la escaleta"):
            st.json(SS["escaleta"])
        with st.expander("Ver el control de calidad"):
            st.json(SS["qa"])
        if SS["ruta"]:
            st.caption(f"Proyecto guardado en `{SS['ruta']}`")

    st.divider()
    if st.button("← Crear otro guion", use_container_width=True):
        reiniciar()
        st.rerun()








