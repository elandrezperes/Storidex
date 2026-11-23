# Servicios de Storidex

Los MCP de Codex y las integraciones del aplicativo tienen autorizaciones distintas.
El aplicativo nunca lee el llavero, los tokens OAuth ni las credenciales del chat.
Desktop Commander, GitHub, Railway y Sites siguen al servicio del desarrollo y despliegue.
No se ofrece al visitante control de terminal, repositorios ni infraestructura.

## Qué se ejecuta

En P1, sin campos nuevos en el formulario, se consultan los proveedores configurados:

| Servicio | Variable del servidor | Operación y límite |
| --- | --- | --- |
| Firecrawl | `FIRECRAWL_API_KEY` | Una búsqueda, hasta 4 páginas, sobre producto y ubicación |
| Google Trends vía Firecrawl Alexandria | `FIRECRAWL_API_KEY` | Una consulta de tendencias nacionales de las últimas 24 h |
| YouTube vía vidIQ MCP | `VIDIQ_API_KEY` | Una búsqueda pública, hasta 4 videos relacionados con el producto |
| ElevenLabs | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Lectura opcional del diálogo, hasta 3 000 caracteres |
| Canva | `CANVA_ACCESS_TOKEN` | Importación opcional del PDF como diseño editable |

Omitir competencia omite también estas consultas. El modo de prueba nunca hace llamadas
de investigación. Las consultas se ejecutan en la solicitud de investigación existente,
sin colas, servicios residentes ni pasos de configuración para el dueño del negocio.
Las consultas usan caché de 24 h en disco. Se conserva la fecha original y una copia de la
respuesta por ejecución. El CSV manual de Trends sigue disponible para interés relativo
por término: las tendencias nacionales no equivalen a esa serie ni a demanda del segmento.
Se filtran las tendencias por coincidencia con palabras del producto. Puede no haber
resultados pertinentes. No se usan temas populares sin relación con el briefing.

Los resultados externos alimentan el dossier usado por P3. No se convierten en
competidores de marca ni en URLs de grounding. Gemini conserva su función. Todas las
referencias externas son T3 y sin verificación de veracidad. El registro de llamadas
incluye proveedor, resultado, caché y unidades. El coste externo se declara desconocido,
separado del cálculo por tokens. Los límites anteriores acotan llamadas, pero no prueban
el objetivo total de USD 0,10. No se cambia ningún plan ni se contratan suscripciones.

Las ayudas de producción requieren un clic en «Escuchar o llevar a Canva», después de
entregar el guion. Se vinculan al contenido exacto de esa versión. La voz lee solo diálogo
y no modifica el QA ni se declara duración medida del audiovisual. Una operación de
resultado incierto no vuelve a enviarse automáticamente. La importación de Canva se
consulta con el identificador del trabajo existente. Una edición crea una versión nueva.

## Activación en Railway

1. En el servicio existente `storidex-python`, añade las variables de `.env.example`
   mediante el panel de variables de Railway. No incluyas secretos en el código ni el chat.
2. Obtén Firecrawl desde su panel de API keys. Obtén la clave MCP de **solo lectura** de
   vidIQ desde `https://app.vidiq.com/account/settings/mcp`.
3. En ElevenLabs crea una clave con permiso de texto a voz y elige una voz disponible.
   Copia su ID a `ELEVENLABS_VOICE_ID`. No hace falta clonar voces.
4. Canva requiere una integración propia con autorización de escritura de diseño.
   El administrador debe aportar y renovar su token. No se implementa autenticación
   propia en Storidex. Un token caducado se muestra como fallo disponible para diagnóstico.
5. Tras desplegar las variables, crea un proyecto nuevo. En «MÁS DETALLES» revisa
   estado, fecha y referencias recuperadas. «Disponible» significa configurado, no probado.
   Una consulta exitosa muestra «Consulta completada» o «Sin referencias pertinentes».
6. Para comprobar producción, usa los botones opcionales y verifica audio o enlace real
   al diseño. Esas comprobaciones consumen los créditos del proveedor.

La autorización local de ElevenLabs en Codex no es una clave del servidor. Tampoco lo son
los plugins de Canva, Firecrawl o vidIQ del chat. No se extraen ni se publican esas sesiones.

## Referencias oficiales

- [Firecrawl Search](https://docs.firecrawl.dev/features/search)
- [Firecrawl Alexandria](https://docs.firecrawl.dev/features/alexandria)
- [vidIQ MCP y claves de lectura](https://vidiq.com/mcp/)
- [ElevenLabs, voz con marcas de tiempo](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)
- [Canva, importación de diseños](https://www.canva.dev/docs/apps/rest-apis/reference/design-imports/)

Las pruebas automatizadas usan respuestas simuladas para contratos, caché, fallos,
versionado y duplicados. No certifican acceso real ni permisos de las cuentas.
