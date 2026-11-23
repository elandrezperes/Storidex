Generas tres premisas dramáticas para un guion publicitario breve, con estructura de Lajos Egri:

- `caracter`: quién es y qué quiere.
- `conflicto`: qué se opone.
- `desenlace`: qué ocurre y qué queda.
- `proposicion`: UNA sola oración que reúna los tres: «X hace Y y obtiene Z».

REGLAS
- Exactamente tres premisas, identificadas A, B y C.
- Las tres deben ser DISTINTAS entre sí en conflicto, no variaciones de la misma idea.
- Al menos una debe apoyarse en `oportunidad` (el hueco de competencia detectado).
- Al menos una debe construirse a partir de la `anti_persona`, por contraste.
- La premisa debe poder resolverse en el tiempo disponible: no propongas una historia de tres actos para 30 segundos.
- `usa_oportunidad` es booleano y honesto.

Devuelve SOLO el JSON del esquema.


Cada opción también lleva `recurso_visual`, `razon_estrategica` y `afirmaciones`.
El recurso visual es una acción u objeto filmable. Diferencia el conflicto, el recurso
visual y el desenlace entre las tres alternativas. Usa los recursos declarados. Si faltan,
prefiere una puesta en escena sencilla y trata cualquier recurso adicional como supuesto.
La razón estratégica explica la decisión. En `afirmaciones` devuelve los IDs de campo de
la ficha que la motivan (por ejemplo ["conflicto.objecion"]), o [] cuando no aplique.
Una inferencia puede inspirar una decisión pero nunca justificar una promesa factual.
