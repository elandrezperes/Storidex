# AGENTS.md — Storidex

> Constitución del proyecto. Este archivo es la fuente de verdad para cualquier agente
> (Codex, ChatGPT, Cursor) que trabaje en este repositorio. Si una instrucción de sesión
> contradice este archivo, gana este archivo; si el cambio es necesario, se actualiza aquí
> primero y se registra en el historial al final.

---

## 1. Qué es este proyecto

**Storidex** es un prototipo de aplicación que genera guiones para reels publicitarios
(15–60 s) a partir de un briefing estructurado de marca.

Es la implementación técnica del **Modelo MIIA** (nombre científico del modelo), una
propuesta de ideación estratégica de guiones audiovisuales breves asistida por IA, en el
marco de una tesis de posgrado. Storidex es el nombre comercial; MIIA es el objeto de
estudio.

**Tesis central que el software debe hacer verdadera:** un guion dirigido y específico
surge de restringir la generación con un *briefing validado*, una *persona operativa* y
un *análisis de competencia*, en lugar de pedirle a un modelo que escriba "un buen guion".

### Qué NO es

- No es un chatbot que escribe guiones. No hay un campo de "pídeme un guion".
- No es un generador de texto libre. Toda fase devuelve JSON validado.
- No es un producto terminado. Es un instrumento de investigación con interfaz.

---

## 2. Reglas inviolables

Estas reglas existen porque el prototipo se valida académicamente. Romperlas invalida la tesis.

1. **Nunca inventar competidores.** Si no hay datos, se declara `sin_datos` y se marca
   `inferido`. Un competidor con nombre inventado es un fallo de validez, no un detalle.
2. **Nunca bloquear por falta de datos.** El pipeline siempre avanza. La falta de datos
   degrada la confianza (T4) y se propaga al guion como marca visible.
3. **Nunca generar texto libre cuando el contrato pide JSON.** Cada fase tiene esquema fijo.
   Si el modelo devuelve prosa, se reintenta con el esquema; no se parsea a la fuerza.
4. **Nunca pedirle al usuario que redacte una definición.** Se le muestran opciones y él
   elige o corrige. El usuario objetivo es un dueño de negocio, no un estratega de marca.
5. **Nunca declarar medición lo que es estimación.** La duración se estima por dos vías y
   se reporta como estimación (ver §8).
6. **Nunca ocultar procedencia.** Cada campo de la persona, del research y del guion lleva
   su nivel T1–T4. Sin excepción.
7. **Nunca asumir un vertical.** Storidex no es una app para radios. Radio es un caso de
   prueba. Todo lo específico de un vertical vive en `examples/`, nunca en el núcleo.

---

## 3. Stack

| Componente | Elección | Motivo |
|---|---|---|
| Interfaz | **Streamlit** | Cambia rápido; es banco de pruebas, no producto |
| Lenguaje | **Python 3.11+** | — |
| Modelo de research | **Gemini 3.8 Flash** + grounding Google Search | Devuelve fuentes citables (T2–T3) |
| Modelo de redacción | **GPT-6.1 Terra** (fases intermedias), **GPT-6.1 Sol** (guion final) | Coste/calidad |
| Persistencia | **JSON en disco** (`/runs/<run_id>/`) | Auditable, versionable, sin base de datos |
| Exportación | **.fdx** (XML Final Draft) + **PDF** | Formato heredado del oficio, ver §7 |
| Estado | `st.session_state` | Sin backend |
| Tests | **pytest** | Una prueba por contrato de fase |

**Prohibido:** añadir base de datos, autenticación, colas o frameworks web antes de que la
tesis esté defendida. El alcance es el pipeline.

### Estructura de carpetas

```
storidex/
├── AGENTS.md                  # este archivo
├── app.py                     # Streamlit: 4 pantallas del flujo
├── core/
│   ├── phases/
│   │   ├── p0_brief.py         # validación, sin LLM
│   │   ├── p1_research.py      # Gemini + grounding
│   │   ├── p2_persona.py       # síntesis + autocrítica
│   │   ├── p3_premisas.py      # 3 premisas Egri
│   │   ├── p4_escaleta.py      # beats con timecode
│   │   ├── p5_guion.py         # guion formateado
│   │   └── p6_qa.py            # control de calidad
│   ├── schemas/                # JSON Schema por fase (fuente de verdad)
│   ├── prompts/                # versionados: v1_research.md, v1_premisas.md ...
│   ├── levels.py               # T1–T4: asignación y propagación
│   ├── export_fdx.py
│   └── export_pdf.py
├── examples/                   # los 3 casos de demostración
│   ├── caso_01_radio/          # La Suprema 96.1
│   ├── caso_02_producto/       # cafetería / marca de ropa
│   └── caso_03_servicio/       # clínica / estudio contable
├── evals/                      # rúbrica y registro del experimento
└── runs/                       # salida: un directorio por ejecución
```

---

## 4. El flujo: cuatro pantallas, seis fases

El usuario ve **cuatro pantallas**. El sistema ejecuta **seis fases**. No confundirlos:
la pantalla 3 dispara tres fases.

| Pantalla | Fase(s) | Qué ve el usuario |
|---|---|---|
| 1. Bienvenida | — | Acceso, proyecto reciente, carga de recursos |
| 2. Contexto | P0 | Formulario del brief |
| 3. Forma | P1 → P2 → P3 | Progreso, ficha de persona editable, competencia |
| 4. Premisas y guion | P4 → P5 → P6 | Tres premisas, elección, guion |

---

## 5. Contratos por fase

Todos los esquemas viven en `core/schemas/<fase>.json` y se validan antes de pasar a la
siguiente fase. Si la validación falla: **un reintento** con el error explícito, luego
excepción registrada en `runs/<run_id>/errors.json`.

### P0 — Brief (sin LLM)

Valida lo que ya recogió la pantalla 2 y 3. No genera nada.

```json
{
  "run_id": "2026-11-12_la_suprema_01",
  "marca": {"nombre": "", "producto": "", "sitio_web": null},
  "ubicacion": {"pais": "EC", "provincia": "Azuay", "ciudad": "Cuenca"},
  "segmento": {
    "edad_min": 25, "edad_max": 40,
    "sexo": "ambos",
    "nse": "C+",
    "nse_escala_pais": "EC"
  },
  "objetivo": ["views"],
  "forma": {
    "participantes": [{"nombre": "Ana", "protagonico": true},
                      {"nombre": "Diego", "protagonico": false}],
    "tipo": "sketch",
    "especificaciones": "La frase «La Suprema, donde vos sos» debe decirse literalmente",
    "indicaciones": "Tono cercano, sin doble sentido",
    "tono": "moderado",
    "duracion_objetivo_s": 30
  },
  "competencia": {"modo": "ambas"},
  "espacio":     { "modo": "fijo", "tipo": "INT", "local": "", "momento": "DÍA" },
  "idioma": {"locale": "es-EC", "variante": "cuencano"}
}
```

**Reglas de P0**
- `competencia.modo` ∈ `marca` | `feed` | `ambas` | `ninguna`. Presentado al usuario como
  «Contra quién compito» / «Contra qué compito» / «Ambas» / «Omitir».
- `tono` ∈ `neutro` | `moderado` | `marcado`. Por defecto `moderado`.
- `tipo` ∈ `sketch` | `publicitario` (ver §6).
- `duracion_objetivo_s` ∈ `15 | 30 | 45 | 60`.
- `sexo` ∈ `ambos | f | m`. `nse` es configurable por país (§9).

### P1 — Research y competencia

```json
{
  "competencia": {
    "modo_solicitado": "ambas",
    "de_marca": [
      {"nombre": "", "descripcion": "", "fuentes": ["https://..."],
       "nivel": "T2", "hallazgos": ["..."]}
    ],
    "de_feed": [
      {"patron": "", "ejemplo": "", "fuentes": [], "nivel": "T3"}
    ],
    "sin_datos": false
  },
  "mercado": {"tendencias": [{"termino": "", "fuente": "", "nivel": "T3"}]},
  "oportunidad": {"texto": "", "nivel": "T3"},
  "fuentes_total": 4
}
```

**Reglas de P1**
- Solo se usa Gemini **con grounding activo**. Cada URL de `fuentes` debe provenir del
  grounding, nunca del modelo.
- Si `modo` incluye `marca` y no hay resultados: `de_marca: []` y `sin_datos: true`.
  **No se rellena con competidores plausibles.**
- Cada hallazgo lleva `nivel`. T2 = página o red social del competidor; T3 = prensa,
  directorio, agregador; T4 = inferencia del modelo (debe poder justificarse).

### P2 — Persona operativa

```json
{
  "persona_id": "per_<run_id>",
  "confianza": {"score": 0.62, "campos_con_fuente": 7, "campos_totales": 12},
  "perfil":    {"nombre": "", "edad": 0, "ocupacion": "", "barrio": "", "nivel": "T4"},
  "consumo":   {"cuando": "", "donde": "", "dispositivo": "", "nivel": "T3"},
  "conflicto": {"problema": "", "objecion": "", "detonante": "", "nivel": "T4"},
  "lenguaje":  {"diria": ["", "", ""], "no_diria": ["", ""], "nivel": "T4"},
  "anti_persona": {"quien_no_es": "", "nivel": "T3"}
}
```

**Reglas de P2 — las más importantes del proyecto**

1. **El segmento es restricción, no sugerencia.** Antes de sintetizar, se construye un
   bloque de restricciones duras desde P0 (rango de edad, ciudad, NSE, sexo). Si la salida
   las viola, se rechaza y se reintenta una vez.
2. **Doce campos, `nivel` por bloque.** Una persona puede tener consumo verificado (T2) y
   lenguaje inferido (T4). No se promedia a un solo nivel.
3. **`lenguaje.diria` exige frases literales**, en primera persona, con el registro del
   segmento. Prohibido: adjetivos ("le gusta la música"), clichés publicitarios
   ("busca calidad y confianza"), y frases que ningún humano diría.
4. **`lenguaje.no_diria` es obligatorio.** Es el campo que previene el guion genérico.
   Debe incluir al menos una fórmula de locución que el guion NO puede usar.
5. **`anti_persona` es obligatorio.** Declarar a quién NO se le habla.
6. **Autocrítica (segunda llamada obligatoria)**. Revisa contra tres reglas: ¿contradice el
   segmento?, ¿hay estereotipo?, ¿alguna frase es genérica? Campos que fallan se reescriben.
7. **`confianza.score` = campos con T1–T3 / 12.** Si `< 0,40`, no se bloquea: se advierte
   en pantalla («ficha débil, añade capturas o entrevistas») y se sigue.
8. **La persona es editable por el usuario** antes de continuar. Se congela como
   `persona_v1.json`; si se edita, se guarda `persona_v2.json` y se registra el diff.

**Validación con usuario no experto:** en lugar de pedirle que defina, se le muestra
«¿cuál de estas tres frases suena más a tu público?» con las opciones de `diria`. Su
elección se registra como T1 y se añade a la ficha.

### P3 — Tres premisas (Egri)

```json
{
  "premisas": [
    {
      "id": "A",
      "caracter": "",
      "conflicto": "",
      "desenlace": "",
      "proposicion": "Una sola oración: X hace Y y obtiene Z",
      "usa_oportunidad": true,
      "nivel": "T3"
    }
  ]
}
```

**Reglas de P3**
- Exactamente **tres**. Cada una con la tríada de Egri y una `proposicion` de una oración.
- Al menos una debe apoyarse explícitamente en `oportunidad` de P1.
- Al menos una debe apoyarse en `anti_persona` de P2 (hablarle a quien no es, para
  contrastar).
- Máximo **3 regeneraciones** por sesión (guarda de costo, §10).

### P4 — Escaleta

```json
{
  "beats": [
    {"tc_in": "00:00", "tc_out": "00:03", "funcion": "hook",
     "descripcion": "", "cuarta_pared": "directa"}
  ],
  "duracion_estimada_s": 29.4,
  "cierre": ""
}
```

**Reglas de P4**
- `funcion` ∈ `hook | planteamiento | conflicto | giro | desenlace | cta | cierre`.
- **El primer beat es siempre `hook`, máximo 3 s.** Es la regla dura del formato reel.
- `cuarta_pared` ∈ `directa | indirecta` (ver §6), coherente con `forma.tipo`.
- Los timecodes son contiguos y su último `tc_out` = duración del guion.

### P5 — Guion

El guion se representa como **lista de párrafos tipados**, no como texto:

```json
{
  "parrafos": [
    {"tipo": "scene_heading", "tc": "00:00", "texto": "HOOK — INT. ESTUDIO. DÍA."},
    {"tipo": "action",        "texto": "ANA, 33, se sirve café de pie."},
    {"tipo": "character",     "texto": "ANA"},
    {"tipo": "parenthetical", "texto": "(a cámara)"},
    {"tipo": "dialogue",      "texto": "Son las seis y cuarenta."},
    {"tipo": "transition",    "texto": "CORTE A NEGRO."}
  ],
  "meta": {"duracion_objetivo_s": 30, "tipo": "sketch", "tono": "moderado",
           "nivel_global": "T3"}
}
```

**Reglas de P5**
- Tipos permitidos: `scene_heading`, `action`, `character`, `parenthetical`, `dialogue`,
  `transition`, `title`. **Nada de prosa libre.**
- Nombres de personaje normalizados contra `forma.participantes` (mayúsculas, acentos
  preservados). Corrige por diseño el error típico de guion escrito a mano.
- `nivel_global` = el peor nivel entre los campos de la ficha de los que dependió el guion.
- El guion se escribe contra la persona, no contra el segmento: toda línea de diálogo debe
  poder rastrearse a `conflicto`, `lenguaje` o `anti_persona`.

### P6 — QA y control

```json
{
  "duracion": {"por_timecodes_s": 29.4, "por_paginas_s": 30.0,
               "objetivo_s": 30, "dentro_de_rango": true},
  "cuarta_pared": {"esperada": "indirecta", "detectada": "indirecta", "ok": true},
  "tono": {"objetivo": "moderado", "detectado": "moderado", "ok": true},
  "objetivo_cumplido": {"pedido": ["views"], "evidencia": "", "ok": true},
  "frases_prohibidas": {"detectadas": [], "ok": true},
  "especificaciones_cumplidas": {"frase_exacta_presente": true, "ok": true},
  "nivel_global": "T3",
  "hallazgos": []
}
```

**Reglas de P6**
- `duracion` reporta **dos estimaciones** y nunca una sola. Ver §8.
- `frases_prohibidas` contrasta el guion contra `lenguaje.no_diria`. Si aparece una, falla.
- `especificaciones_cumplidas` verifica literalmente `forma.especificaciones` (la frase
  obligatoria, si existe).
- Si `ok: false` en cualquier bloque, se ofrece **una** regeneración de P5 con la corrección
  explícita. Nunca bucle automático.

---

## 6. Sketch vs. publicitario: la cuarta pared es el criterio

La distinción **no** es de género ni de tono publicitario: es **enunciativa**.

| Tipo | Cuarta pared | Qué significa en el texto |
|---|---|---|
| **Sketch** | Intacta o mínimamente rota | Los personajes no saben que hay cámara. La acción dramática sostiene el mensaje. Se admite **un** aparte al cierre (el *tag*), declarado como excepción. |
| **Publicitario** | Rota todo el tiempo | Se habla a cámara. El mensaje se enuncia, no se dramatiza. Puede haber personajes, pero el enunciador es visible. |

**Implementación**
- `forma.tipo` fija `esperada` en P6.
- En P4, `cuarta_pared: directa` solo es válido si `tipo == publicitario`; en `sketch` es
  `indirecta`, salvo el último beat (tag), que se marca `indirecta_con_tag`.
- El QA detecta la ruptura contando marcas `parenthetical` con `(a cámara)`, `(al público)`,
  y vocativos en segunda persona dentro del diálogo.

**Nota teórica para la tesis:** un sketch *puede* romper la cuarta pared en el remate sin
dejar de ser sketch. La regla del prototipo es una decisión de diseño declarada, no una
definición de género. Debe decirse así en el documento.

---

## 7. Exportación: formato heredado, no inventado

El formato de referencia es el guion del director: **Final Draft 13**, Courier 12 pt,
página carta. Medidas verificadas sobre el PDF de referencia:

| Elemento | Posición X | Ancho | Notas |
|---|---|---|---|
| Número de escena / timecode | 54 pt (0,75") | — | En Storidex: `00:00` |
| Encabezado y acción | 108 pt (1,5") | 6,0" | — |
| Diálogo | 180 pt (2,5") | 3,5" | — |
| Personaje | 252 pt (3,5") | — | Mayúsculas |
| Cuerpo / interlineado | — | — | 12 pt / 12 pt (10 cpi) |
| Página | 612 × 792 pt | — | Carta; folio arriba a la derecha con punto (`19.`) |

**Exportación .fdx:** XML de Final Draft con `<Paragraph Type="...">` mapeado desde los
tipos de P5 (`scene_heading` → Scene Heading, `action` → Action, `character` → Character,
`parenthetical` → Parenthetical, `dialogue` → Dialogue, `transition` → Transition).
Debe abrir en Final Draft 13 sin conversión.

**Exportación PDF:** replica las medidas de la tabla. En pantalla de teléfono se usa
Courier Prime 13 pt por legibilidad; **el PDF siempre vuelve a 12 pt**.

---

## 8. Duración: dos estimaciones, declaradas como estimación

Regla de honestidad metodológica. Nunca presentar una sola cifra como medida.

1. **Por timecodes** = suma de `tc_out − tc_in` de P4. Es la estimación primaria.
2. **Por páginas** = páginas del PDF exportado × 60 s. Es la convención de oficio
   (una página de Courier 12 ≈ un minuto de pantalla), **no una ley física**.

Si las dos difieren en más de 15 %, se advierte en P6 y se sugiere revisar el ritmo. En el
texto de la tesis debe aparecer como *estimación*, nunca como duración medida.

---

## 9. Segmento socioeconómico: configurable

`segmento.nse` no asume una escala universal. Se resuelve contra
`core/schemas/nse_<pais>.json`:

```json
// nse_EC.json
{"pais": "EC", "escala": ["A", "B", "C+", "C-", "D"], "etiqueta": "Segmento socioeconómico"}
```

Implementación inicial: solo `EC`. Si falta el país, el campo se muestra como texto libre y
se marca T1 (declarado por el usuario). Esto cierra la objeción sobre generalización sin
coste de implementación.

---

## 10. Guardas de costo

Tarifas de referencia (noviembre 2026, verificar antes de cambiar de modelo):
GPT-6.1 Sol `$2 / $10` por millón; GPT-6.1 Terra `$1 / $5`; Gemini 3.8 Flash `$0,75 / $3,75`
(introductorio hasta 31-dic-2026). Grounding de Google Search: 5.000 consultas/mes gratis,
luego `$14 / 1.000`.

- Costo objetivo por generación completa: **≤ $0,10 USD**.
- Modelo asignado por fase: **no cambiar Sol por Terra en P5** (es donde se juega la
  calidad del diálogo); **no usar Sol en P1–P4 ni P6**.
- Máximo **3 regeneraciones** de P3 por sesión y **1** de P5 en P6.
- Cachear P1 por `(marca, producto, ubicacion, competencia.modo)` durante 24 h: el research
  es lo único reutilizable entre iteraciones del mismo brief.
- Registrar `tokens` y `costo_estimado` en cada `runs/<run_id>/trace.json`.

---

## 11. Los tres casos de demostración

Viven en `examples/`. Sirven para probar generalidad, no para el desarrollo del núcleo.
Cada uno estresa una capacidad distinta:

| Caso | Vertical | Qué estresa |
|---|---|---|
| `caso_01_radio` | Servicio local con audiencia (La Suprema 96.1) | Tono, voz, registro regional |
| `caso_02_producto` | Producto físico (cafetería o marca de ropa) | Hook visual, propuesta de valor |
| `caso_03_servicio` | Servicio profesional (clínica o estudio contable) | Objeción, confianza, CTA |

Ningún módulo de `core/` puede contener lógica específica de un vertical. Si aparece la
palabra "radio" fuera de `examples/`, es un error de arquitectura.

---

## 12. Validación (fuera del código, pero condiciona el diseño)

- **Diseño:** intra-sujeto. Cada evaluador juzga 2 guiones por caso —pipeline vs. baseline
  de prompt único— en orden aleatorio y a ciegas.
- **Muestra:** 12–15 personas del segmento (juzgan pertinencia) + 3 jueces expertos
  (juzgan oficio).
- **Rúbrica de 6 criterios:** pertinencia al persona, claridad del mensaje único, coherencia
  con el objetivo declarado, uso del dato de competencia, verosimilitud del registro,
  cumplimiento de duración.
- **Análisis:** Wilcoxon de rangos con signo sobre 45 comparaciones pareadas (15 × 3).
  Declarar como evidencia de preferencia, **no** como representatividad poblacional.

**Requisito de código:** cada `run` debe guardar el brief, la persona congelada, las tres
premisas, el guion y el QA en un solo directorio, para que el evaluador pueda recibir el
guion sin ver el proceso, y el investigador pueda auditarlo después.

---

## 13. Convenciones de código

- Python 3.11+, `ruff` para estilo, `pytest` para tests.
- **Ningún string de prompt dentro de `.py`**: viven en `core/prompts/<fase>_v<n>.md`.
  La versión del prompt usado se registra en `trace.json`.
- Todo acceso a API pasa por `core/llm.py`, con reintento exponencial y tope de gasto.
- Los errores no se silencian: se escriben en `runs/<run_id>/errors.json` y se muestran en
  la interfaz en lenguaje llano.
- Idioma del código y de los esquemas: **inglés** para claves; **español** para todo texto
  que vea el usuario.

---

## 14. Historial de decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-12 | Nombre comercial Storidex, modelo MIIA | Decisión del autor; el logo dice STORIDEX |
| 2026-11-12 | Competencia decidible por el usuario (marca / feed / ambas) | No siempre hay datos de marca; el usuario conoce su mercado |
| 2026-11-12 | Streamlit en lugar de Next.js | El prototipo cambiará; el diseño se demuestra con el pliego visual |
| 2026-11-12 | Arquitectura híbrida Gemini + GPT | El grounding aporta fuentes citables (T2–T3); GPT escribe mejor el diálogo |
| 2026-11-12 | Persona como artefacto sintetizado, no dato de entrada | El segmento no es un persona; sintetizar con restricciones evita el estereotipo |
| 2026-11-12 | Niveles T1–T4 por bloque, no por ficha | Permite declarar confianza parcial y propagarla al guion |
| 2026-11-12 | «Segmento socioeconómico» configurable por país | Evita asumir escala latinoamericana |
| 2026-11-12 | Tono en tres niveles, por defecto «moderado» | Control sin abrir la puerta a la parodia |
| 2026-11-12 | Duración como estimación doble, nunca medida | Honestidad metodológica |

