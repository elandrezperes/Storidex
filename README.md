# Storidex

Aplicación que escribe guiones para reels a partir del briefing de cualquier marca.
Implementación técnica del **Modelo MIIA**.

El guion lo escribe un modelo de lenguaje. No hay plantillas ni contenido
prestablecido: lo que sale depende enteramente de los datos que introduzcas.

## 1. Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Llave de API (obligatoria)

1. Entra en **platform.openai.com** → *API keys* → **Create new secret key**
2. Copia la llave (empieza por `sk-`)
3. Crea el archivo de configuración:

```bash
cp .env.example .env
```

4. Abre `.env` y pega la llave:

```
OPENAI_API_KEY=sk-tu-llave-aqui
```

El coste depende de los modelos, las revisiones y los servicios activados.
`trace.json` conserva la estimación por tokens y registra las llamadas externas
por separado. El objetivo de coste debe comprobarse con ejecuciones reales.

**Opcional — `GEMINI_API_KEY`:** activa la búsqueda de competencia real con fuentes
citables. Sin ella el sistema escribe igual y declara el análisis como no disponible,
en lugar de inventarlo.

## 3. Arranque

```bash
streamlit run app.py
```

Se abre en `http://localhost:8501`.

## Cómo se usa

1. **Contexto** — marca, producto, ubicación (país → provincia → ciudad),
   rango de edad, sexo, segmento socioeconómico, objetivo y sitio web.
2. **Forma** — participantes, quién es el protagónico, tipo de video, frase
   obligatoria, indicaciones, tono, duración y espacio escénico opcional.
3. **Resultado** — análisis de competencia, ficha del destinatario, tres premisas
   para elegir, guion final y control de calidad.
4. **Exportar** — `.fdx` (Final Draft) y PDF con el formato profesional.

## Siete etapas del modelo

| Fase | Qué hace |
|---|---|
| P0 | Valida el briefing y fija las restricciones duras |
| P1 | Investigación de mercado y competencia (Gemini con búsqueda, opcional) |
| P2 | Ficha del destinatario con autocorrección, procedencia por afirmación y cobertura documental |
| P3 | Tres premisas con conflicto, recurso visual, desenlace y razón estratégica |
| P4 | Escaleta con códigos de tiempo; el gancho nunca pasa de 3 s |
| P5 | Guion en párrafos tipados con vínculos propuestos a la evidencia |
| P6 | Control: duración, cuarta pared, frases prohibidas, frase obligatoria |

### Compatibilidad con la versión previa de GitHub

Se conservan el espacio escénico, el catálogo de registro regional y el acceso
por clave que ya tenía Streamlit. El espacio puede decidirlo el guionista o
fijarse con tipo, localización y momento. P4 lo conserva en los beats y P5 en
los encabezados. El QA comprueba su coherencia cuando está declarado.

El catálogo de registro orienta la escritura y no demuestra cómo habla el público.
Las decisiones de la ficha y la evidencia aportada prevalecen sobre ese catálogo.

En Streamlit Community Cloud, las claves se leen también de `st.secrets`.
La configuración previa `STORIDEX_CLAVE` conserva el acceso compartido de evaluación
y `STORIDEX_TOPE_SESION` el límite por sesión. No se amplía este mecanismo a Sites,
que mantiene el acceso del servicio alojado. No se añaden cuentas ni base de datos.

La sección Forma admite evidencia documentada del público y recursos de producción.
En Trazabilidad y revisión, registra el dictamen sobre una afirmación y, si se realizó,
el tiempo de una lectura cronometrada o un animatic. Los dictámenes preservan la ficha
original para auditoría. En Sites cada registro pertenece a la versión de guion revisada.

### Referencias de mercado y guion

En Forma, **MÁS DETALLES** explica para qué sirve cada fuente y permite aportar
material opcional. La investigación contextual, la selección de patrones y la
revisión del guion se ejecutan durante las fases del flujo. Puedes importar el CSV de **Interés a lo largo del tiempo** de Google Trends.
El dossier queda en `brief.json` y `research.json`. Las referencias seleccionadas
quedan en `premisas.json` y en la trazabilidad de `guion.json`. El control creativo
se guarda como orientación en `qa.json`, aparte de los criterios de aprobación.

Los hallazgos aportados se conservan separados de la competencia respaldada por
grounding. Si se compara el MIIA con otro procedimiento, reutiliza una copia del
mismo dossier congelado en todas las condiciones. `trace.json` registra el modelo,
la versión del prompt, los tokens informados y el costo estimado de tokens. Cuenta
las consultas reportadas por Gemini por separado y reutiliza durante 24 horas las
respuestas con fuentes para el mismo prompt y contexto de búsqueda.

## Estructura

```
app.py                 interfaz Streamlit (4 pantallas)
core/
  llm.py               único punto de acceso a los modelos
  levels.py            niveles de procedencia T1–T4
  contracts.py         validación de los esquemas
  phases/              p0_brief … p6_qa
  prompts/             instrucciones versionadas, fuera del código
  data/ubicaciones.json  país → provincia → ciudad
  export_fdx.py        exportación a Final Draft
  export_pdf.py        exportación a PDF (escritor propio, sin dependencias)
  local.py             solo para pruebas automáticas
examples/              tres briefings completos
runs/                  un proyecto por carpeta, con todos sus artefactos
tests/                 contratos, regresiones e interfaz automatizada
```

## Pruebas

```bash
pytest -q
```

Corren sin red y sin gastar créditos.

## Línea de comandos

```bash
python pipeline.py examples/caso_01_radio.json
```

Genera `runs/<fecha>_<marca>/` con brief, research, persona, premisas, escaleta,
guion, control de calidad, `.fdx` y PDF.


## Versión para Sites

La interfaz web corre en un Cloudflare Worker de Sites. Las llamadas a modelos,
la auditoría en JSON y las exportaciones corren en un servicio Python WSGI
separado con disco persistente. Streamlit y la CLI siguen disponibles localmente.

1. En un alojamiento Python POSIX, instala `requirements.txt` y Gunicorn.
   Configura `sites_backend:application` detrás de un endpoint HTTPS, por ejemplo
   con `gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 180 sites_backend:application`
   detrás del proxy TLS del alojamiento. Monta un volumen persistente en
   `STORIDEX_RUNS_DIR`. El backend requiere el mismo secreto de enlace en todas
   las instancias y debe usar un volumen con bloqueo de archivos.
2. Inyecta como secretos del servicio Python `OPENAI_API_KEY`, opcionalmente
   `GEMINI_API_KEY`, y `STORIDEX_PROXY_SECRET` (un valor aleatorio exclusivo
   para este enlace). La ausencia de Gemini permite continuar con P1 sin fuentes.
3. Mantén el Site privado para el propietario. Registra `STORIDEX_BACKEND_URL`
   y el mismo `STORIDEX_PROXY_SECRET` como valores de runtime de Sites.
   Las claves de OpenAI y Gemini solo residen en el servicio Python.
4. Ejecuta `python sites/build.py`. El Worker ESM queda en `dist/server/index.js`.
   Al registrar el Site, su manifiesto `.openai/hosting.json` requiere el
   `project_id` real y omite `static`. Usa el flujo nativo de empaquetado
   y publicación de Sites. El Worker incorpora únicamente HTML, CSS, JavaScript
   y el catálogo de ubicaciones.

La lista de proyectos muestra ejecuciones de Sites. Los proyectos previos de
Streamlit siguen en su directorio de origen y la interfaz alojada no los importa.
La ficha web permite confirmar una de las frases como T1 y guarda el cambio.
El modo de demostración usa `STORIDEX_DRY_RUN=true` en Python y se identifica
en pantalla.
## Servicios externos

Consulta [la activación y el alcance de las integraciones](docs/servicios.md).
Las credenciales de los MCP conectados en Codex no activan por sí solas los servicios
del aplicativo. La investigación usa los proveedores configurados en segundo plano.
Las ayudas de voz y Canva aparecen después de entregar el guion.

## Pruebas automáticas en GitHub Actions

El flujo **Pruebas de Storidex** ejecuta toda la carpeta `tests/` al actualizar
`main`, al abrir o actualizar una pull request y al iniciarlo manualmente desde
**Actions → Pruebas de Storidex → Run workflow**.

Usa Python 3.11 en Linux, instala `requirements.txt` y ejecuta:

```bash
STORIDEX_DRY_RUN=true python -m pytest tests -q
```

La ejecución no recibe claves de proveedores. Las respuestas locales y simuladas
permiten comprobar los contratos y las regresiones sin consumir APIs de IA.
El resumen de cada ejecución muestra pruebas aprobadas, fallidas y omitidas.
Un fallo deja la comprobación en rojo. El flujo no despliega la aplicación.

Estos controles no sustituyen la validación de guiones con público y expertos
ni verifican el acceso real a servicios externos.
