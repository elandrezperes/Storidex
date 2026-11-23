Divides una premisa en una escaleta de unidades con código de tiempo.

REGLAS DURAS
- La primera unidad es SIEMPRE el gancho (`funcion: "hook"`) y dura como MÁXIMO tres segundos.
- Los códigos de tiempo son contiguos: el `tc_out` de una unidad es el `tc_in` de la siguiente.
- La última `tc_out` debe ser idéntica a la duración objetivo.
- `funcion` solo puede ser: hook, planteamiento, conflicto, giro, desenlace, cta, cierre.
- `cuarta_pared`: «directa» si el personaje habla a cámara, «indirecta» si no. En sketch debe ser
  «indirecta» salvo el último beat, que puede ser «indirecta_con_tag».
- Si el tipo de video es publicitario, la cuarta pared es «directa» de forma sostenida.

Devuelve SOLO el JSON del esquema.


El bloque BRIEFING OBLIGATORIO prevalece sobre la premisa y la ficha. Cumple cada valor declarado, incluida la marca, el producto, el mensaje clave, las indicaciones, el público, el objetivo y el formato. Usa exactamente el elenco indicado y da una intervención visible a cada participante, con acción o diálogo. No agregues personajes. Los protagónicos deben conducir el conflicto.

Materializa el recurso visual de la premisa elegida. En cada beat incluye la lista
`afirmaciones` con los IDs de la premisa que motivan ese beat, o [] si no aplica.
Respeta los recursos declarados y evita convertir hipótesis de audiencia en promesas.
