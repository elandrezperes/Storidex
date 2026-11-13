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

**Coste:** un guion completo ronda **0,02 USD**. Con 5 dólares salen unos 250 guiones.

**Opcional — `GEMINI_API_KEY`:** activa la búsqueda de competencia real con fuentes
citables. Sin ella el sistema escribe igual y declara el análisis como no disponible,
en lugar de inventarlo.

## 3. Arranque

```bash
streamlit run app.py
```

Se abre en `http://localhost:8501`.

## 4. Publicarla para que otros la usen

Ver **`DEPLOY.md`**. En resumen: subir el código a GitHub, conectarlo a
Streamlit Community Cloud, pegar las llaves en *Secrets* y compartir el enlace.
Gratis, y con clave de acceso opcional para proteger tus créditos.

## Cómo se usa

1. **Contexto** — marca, producto, ubicación (país → provincia → ciudad),
   rango de edad, sexo, segmento socioeconómico, objetivo y sitio web.
2. **Forma** — participantes, quién es el protagónico, tipo de video, frase
   obligatoria, indicaciones, tono y duración.
3. **Resultado** — análisis de competencia, ficha del destinatario, tres premisas
   para elegir, guion final y control de calidad.
4. **Exportar** — `.fdx` (Final Draft) y PDF con el formato profesional.

## El espacio escénico

Cada escena declara **tipo**, **localización** y **momento del día**, que es lo que
compone un encabezado profesional:

```
INT. APARTAMENTO - SALA/COCINA. DÍA.
```

- **tipo**: `INT` (interior), `EXT` (exterior) o `INT/EXT` (ambos)
- **momento**: AMANECER, MAÑANA, DÍA, MEDIODÍA, TARDE, ATARDECER, NOCHE,
  MADRUGADA o CONTINUO

En la pantalla de forma el usuario decide si lo fija él o lo deja al guionista. Si
lo deja abierto, el sistema propone el espacio según el rubro y la ciudad. El
control de calidad verifica que **todos** los encabezados declaren los tres
componentes y que, si el espacio estaba fijado, ninguno se salga de él.

## Las seis fases

| Fase | Qué hace |
|---|---|
| P0 | Valida el briefing y fija las restricciones duras |
| P1 | Investigación de mercado y competencia (Gemini con búsqueda, opcional) |
| P2 | Ficha del destinatario, con autocorrección de clichés |
| P3 | Tres premisas con estructura dramática |
| P4 | Escaleta con códigos de tiempo y espacio por unidad; el gancho nunca pasa de 3 s |
| P5 | Guion en párrafos tipados |
| P6 | Control: duración, reparto, espacio, cuarta pared, frases prohibidas, frase obligatoria |

## Estructura

```
app.py                 interfaz Streamlit (4 pantallas)
core/
  llm.py               único punto de acceso a los modelos
  levels.py            niveles de procedencia T1–T4
  contracts.py         validación de los esquemas
  phases/              p0_brief … p6_qa
  prompts/             instrucciones versionadas, fuera del código
  espacio.py           INT/EXT · localización · momento del día
  registro.py          variedad lingüística según la ubicación
  data/ubicaciones.json  país → provincia → ciudad
  export_fdx.py        exportación a Final Draft
  export_pdf.py        exportación a PDF (escritor propio, sin dependencias)
  local.py             solo para pruebas automáticas
examples/              tres briefings completos
runs/                  un proyecto por carpeta, con todos sus artefactos
tests/                 34 pruebas
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


