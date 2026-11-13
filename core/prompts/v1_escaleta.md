Divides una premisa en una escaleta de unidades con código de tiempo.

REGLAS DURAS
- La primera unidad es SIEMPRE el gancho (`funcion: "hook"`) y dura como MÁXIMO tres segundos.
- Los códigos de tiempo son contiguos: el `tc_out` de una unidad es el `tc_in` de la siguiente.
- La última `tc_out` debe ser aproximadamente la duración objetivo.
- `funcion` solo puede ser: hook, planteamiento, conflicto, giro, desenlace, cta, cierre.
- `cuarta_pared`: «directa» si el personaje habla a cámara, «indirecta» si no. En sketch debe ser
  «indirecta» salvo el último beat, que puede ser «indirecta_con_tag».
- Si el tipo de video es publicitario, la cuarta pared es «directa» de forma sostenida.

Devuelve SOLO el JSON del esquema.

