"""Generador local: compone contenido a partir del briefing real.

Este módulo es lo que hace que el prototipo funcione SIN llaves de API. No es un
modelo de lenguaje: es un motor de reglas que clasifica el producto y compone
persona, premisas, escaleta y guion con el material que el usuario escribió.

Su función no es sustituir al modelo —en modo real P1–P5 usan Gemini y GPT— sino
permitir que la aplicación sea utilizable desde el primer minuto: cualquier marca
obtiene un resultado distinto y coherente con lo que escribió, no un ejemplo fijo.

Cuando el modo seco está activo, la interfaz lo advierte y marca el guion como
material de demostración.
"""
from __future__ import annotations

from .levels import T1, T3, T4

# --------------------------------------------------------------- categorías
CATEGORIAS = {
    "radio": ("radio", "emisora", "programa", "locutor", "podcast", "matutin",
              "frecuencia", "cortina", "audiencia"),
    "gastronomia": ("café", "cafeteria", "cafetería", "restaurante", "comida", "bar",
                    "panadería", "panaderia", "pizzería", "pizzeria", "sushi", "helado",
                    "cerveza", "postre", "menú", "menu", "almuerzo", "hamburgues",
                    "panader", "pan ", "masa madre", "reposter", "pasteler", "café"),
    "comercio": ("tienda", "ropa", "boutique", "zapato", "moda", "accesorio",
                 "joyería", "joyeria", "mueble", "ferretería", "ferreteria",
                 "almacén", "almacen", "supermercado"),
    "servicios": ("contab", "abogad", "legal", "consultor", "estudio", "asesor",
                  "seguro", "inmobiliaria", "arquitect", "diseño", "diseno",
                  "marketing", "publicidad"),
    "salud": ("clínica", "clinica", "médic", "medic", "dental", "odontolog",
              "fisioterap", "psicólog", "psicolog", "laboratorio", "farmacia",
              "nutricion", "veterinar"),
    "educacion": ("academia", "escuela", "colegio", "universidad", "curso",
                  "instituto", "capacitación", "capacitacion", "clases"),
    "belleza": ("peluquería", "peluqueria", "barbería", "barberia", "spa",
                "estética", "estetica", "uñas", "unas", "maquillaje", "salón",
                "salon", "depilación", "depilacion"),
    "tecnologia": ("software", "app", "aplicación", "aplicacion", "plataforma",
                   "sistema", "digital", "startup", "web", "saas"),
    "turismo": ("hotel", "hostal", "hosteria", "hostería", "tour", "viaje",
                "agencia de viaje", "turismo", "cabalgata", "aventura"),
    "salud_animal": ("veterinaria", "mascota", "pet shop", "peluquería canina"),
}

# ------------------------------------------------------------------ léxico
LEXICO = {
    "radio": {
        "problema": "sale de casa antes de que el día esté resuelto",
        "objecion": "cree que la radio matutina es puro chisme",
        "detonante": "algo que la haga reír antes de llegar al trabajo",
        "diria": ["Yo a esa hora no pienso, solo pongo algo",
                  "No me hables de política a las siete",
                  "Si me río antes de llegar, el día es otro"],
        "no_diria": ["Estimado oyente", "Queridos radioescuchas"],
        "anti": "el oyente que busca análisis noticioso o debate político",
        "escena": "INT. ESTUDIO. DÍA.",
        "accion": "se sirve café de pie y enciende la consola sin mirarla",
        "gancho": "Son las {hora}. Nadie debería estar despierto.",
        "cierre": "El producto en primer plano. El logo aparece sobre el último acorde.",
    },
    "gastronomia": {
        "problema": "come siempre lo mismo porque elegir le cuesta más que comer",
        "objecion": "desconfía de los lugares nuevos: ya se quemó una vez",
        "detonante": "encontrar algo rico sin tener que decidir demasiado",
        "diria": ["A ver, ¿qué hay hoy?",
                  "Yo quiero algo rico pero no quiero pensarlo",
                  "Si está bueno, vuelvo mañana"],
        "no_diria": ["Exquisita experiencia gastronómica", "Deleite sus sentidos"],
        "anti": "quien busca una cena de mantel y tres tiempos",
        "escena": "INT. LOCAL. MEDIODÍA.",
        "accion": "entra, mira la pizarra del día y se relaja",
        "gancho": "Hay decisiones que uno no quiere tomar a la una de la tarde.",
        "cierre": "El producto en primer plano. El logo aparece sobre el vapor.",
    },
    "comercio": {
        "problema": "necesita algo puntual y no quiere perder la tarde buscándolo",
        "objecion": "asume que lo que busca no va a estar o va a costar caro",
        "detonante": "encontrarlo rápido y saber el precio antes de entrar",
        "diria": ["¿Tienen esto?",
                  "Solo quiero ver y ya",
                  "Si me queda, me lo llevo"],
        "no_diria": ["La mejor calidad al mejor precio", "Tú lo mereces"],
        "anti": "quien busca una marca de lujo con asesoría personalizada",
        "escena": "INT. TIENDA. DÍA.",
        "accion": "recorre la vitrina con la mirada, sin prisa",
        "gancho": "Nadie tiene una tarde entera para buscar una sola cosa.",
        "cierre": "El producto en mano. El logo aparece en la bolsa.",
    },
    "servicios": {
        "problema": "deja las obligaciones para después porque le dan miedo",
        "objecion": "teme que le cobre por algo que no entiende",
        "detonante": "que alguien le explique en dos frases qué pasa y cuánto cuesta",
        "diria": ["Eso lo veo después",
                  "¿Y eso cuánto me va a costar?",
                  "Explícame sin palabras raras"],
        "no_diria": ["Soluciones integrales de alto valor", "Sinergia empresarial"],
        "anti": "la empresa grande que ya tiene departamento propio",
        "escena": "INT. OFICINA. DÍA.",
        "accion": "ordena papeles que lleva meses evitando",
        "gancho": "Las cosas importantes siempre se dejan para mañana.",
        "cierre": "El trabajo terminado. El logo aparece en el lomo de la carpeta.",
    },
    "salud": {
        "problema": "posterga la consulta hasta que el malestar le gana",
        "objecion": "cree que ir al médico es caro y que le van a decir que exagera",
        "detonante": "sentir que lo escuchan sin apuro ni juicio",
        "diria": ["Después veo",
                  "¿Es muy caro?",
                  "Primero quiero saber qué tengo"],
        "no_diria": ["Su salud es nuestra prioridad", "Tecnología de punta"],
        "anti": "quien busca una cirugía estética de resultado inmediato",
        "escena": "INT. CONSULTORIO. DÍA.",
        "accion": "espera con las manos en las rodillas, mirando la puerta",
        "gancho": "Nadie va al médico por gusto. Se va cuando ya no queda de otra.",
        "cierre": "La puerta se abre. El logo aparece en la placa.",
    },
    "educacion": {
        "problema": "sabe que necesita formarse pero no encuentra cuándo",
        "objecion": "cree que va a empezar y va a abandonar como las otras veces",
        "detonante": "un formato corto, con horario real y un resultado visible",
        "diria": ["Quiero pero no tengo tiempo",
                  "¿Cuánto dura?",
                  "Si empiezo, ¿lo termino?"],
        "no_diria": ["Fórmate para el futuro", "Excelencia académica"],
        "anti": "quien busca un título universitario de cuatro años",
        "escena": "INT. AULA. TARDE.",
        "accion": "abre el cuaderno y mira el reloj antes de empezar",
        "gancho": "Siempre es el mismo problema: ganas sí, tiempo no.",
        "cierre": "El cuaderno lleno. El logo aparece en la esquina.",
    },
    "belleza": {
        "problema": "no encuentra quién le entienda el estilo sin cambiárselo",
        "objecion": "salió decepcionada la última vez que se dejó hacer algo",
        "detonante": "que le pregunten qué quiere antes de empezar",
        "diria": ["Yo quiero algo así, pero no tanto",
                  "No me cortes mucho",
                  "¿Vos qué harías?"],
        "no_diria": ["Renueva tu imagen", "Belleza sin límites"],
        "anti": "quien busca un cambio radical de look",
        "escena": "INT. SALÓN. DÍA.",
        "accion": "se mira en el espejo y duda antes de sentarse",
        "gancho": "Uno se sienta y ya no sabe cómo explicar lo que quiere.",
        "cierre": "El espejo. El logo aparece en el reflejo.",
    },
    "tecnologia": {
        "problema": "resuelve todo a mano y ya no le alcanza el tiempo",
        "objecion": "cree que la herramienta va a ser otro sistema que nadie va a usar",
        "detonante": "ver que se resuelve en el primer día, sin capacitación",
        "diria": ["¿Y esto quién lo va a usar?",
                  "Ya probamos algo así y no funcionó",
                  "Muéstrame, no me expliques"],
        "no_diria": ["Transformación digital 360", "Ecosistema de soluciones"],
        "anti": "la corporación que busca integrar veinte sistemas",
        "escena": "INT. OFICINA. DÍA.",
        "accion": "cierra tres pestañas y abre la cuarta",
        "gancho": "Nadie tiene tiempo para aprender otro sistema.",
        "cierre": "La pantalla limpia. El logo aparece en la barra.",
    },
    "turismo": {
        "problema": "necesita descansar y no quiere gastar el descanso organizando",
        "objecion": "desconfía de que el lugar sea como en las fotos",
        "detonante": "llegar y que todo esté resuelto sin preguntar nada",
        "diria": ["¿Está lejos?",
                  "¿Y si no me gusta?",
                  "Solo quiero llegar y no pensar"],
        "no_diria": ["Vive la experiencia de tu vida", "Destino soñado"],
        "anti": "quien busca un paquete con itinerario de doce horas",
        "escena": "EXT. ENTRADA. DÍA.",
        "accion": "deja la maleta en el piso y respira",
        "gancho": "Uno se toma vacaciones para descansar, no para organizar.",
        "cierre": "La vista abierta. El logo aparece abajo.",
    },
    "salud_animal": {
        "problema": "no sabe si lo que le pasa a su mascota es grave o no",
        "objecion": "teme que le cobren una fortuna por decirle que no es nada",
        "detonante": "que le expliquen qué tiene y qué hacer, sin alarmismo",
        "diria": ["¿Será grave?",
                  "Ella no come desde ayer",
                  "¿Y ahora qué hago?"],
        "no_diria": ["Tu mascota merece lo mejor", "Amor incondicional"],
        "anti": "quien busca una clínica de especialidades exóticas",
        "escena": "INT. CONSULTORIO. DÍA.",
        "accion": "sostiene al perro en brazos y espera",
        "gancho": "No habla, pero se le nota. Y eso es lo peor.",
        "cierre": "La mascota tranquila. El logo aparece en la placa.",
    },
    "otro": {
        "problema": "resuelve lo mismo todos los días sin que nadie se lo reconozca",
        "objecion": "cree que ya probó algo parecido y no le sirvió",
        "detonante": "que le hablen claro, sin promesas grandes",
        "diria": ["Bueno, a ver",
                  "¿Y eso qué me resuelve?",
                  "Si funciona, sigo"],
        "no_diria": ["La solución que estabas esperando", "Calidad garantizada"],
        "anti": "quien busca una solución a medida para una gran empresa",
        "escena": "INT. ESPACIO. DÍA.",
        "accion": "hace una pausa y mira lo que tiene delante",
        "gancho": "Hay cosas que uno hace todos los días sin pensarlas.",
        "cierre": "El logo aparece sobre el último plano.",
    },
}

NOMBRES_F = ["Mónica", "Verónica", "Andrea", "Carolina", "Daniela", "Gabriela",
             "Paulina", "María José", "Ximena", "Fernanda"]
NOMBRES_M = ["Mateo", "Diego", "Sebastián", "Andrés", "Joaquín", "Esteban",
             "Cristian", "Martín", "Nicolás", "Felipe"]
OFICIOS = {
    "radio": ["Locutor/a con doce años en la misma franja", "Productor/a de radio",
              "Conductor/a de magazine matutino"],
    "gastronomia": ["Contador/a con estudio propio", "Profesor/a de colegio",
                    "Vendedor/a de una distribuidora"],
    "comercio": ["Administrador/a de un local familiar", "Diseñador/a freelance",
                 "Empleado/a bancario"],
    "servicios": ["Dueño/a de una ferretería", "Gerente de un taller", "Arquitecto/a independiente"],
    "salud": ["Profesor/a universitario", "Contador/a", "Comerciante"],
    "educacion": ["Asistente administrativo", "Técnico/a en enfermería", "Vendedor/a"],
    "belleza": ["Recepcionista de hotel", "Estudiante de posgrado", "Vendedor/a de seguros"],
    "tecnologia": ["Jefe/a de operaciones", "Contador/a general", "Coordinador/a de proyectos"],
    "turismo": ["Odontólogo/a", "Funcionario/a público", "Dueño/a de una papelería"],
    "salud_animal": ["Profesor/a de escuela", "Diseñador/a gráfico", "Contador/a"],
    "otro": ["Profesional independiente", "Empleado/a de oficina", "Dueño/a de un negocio"],
}
BARRIOS = {
    "Cuenca": ["El Vergel", "Centro Histórico", "Yanuncay", "Totoracocha", "El Batán"],
    "Quito": ["La Floresta", "Carcelén", "El Inca", "González Suárez"],
    "Guayaquil": ["Urdesa", "Alborada", "Samborondón", "Los Ceibos"],
    "default": ["El Centro", "La Avenida principal", "El Barrio Norte", "La Zona Rosa"],
}


# ---------------------------------------------------------------- funciones
def clasificar(producto: str, marca: str = "") -> str:
    """Clasifica la categoría mirando el producto y, si hace falta, la marca."""
    texto = f"{producto} {marca}".lower()
    for cat, claves in CATEGORIAS.items():
        if any(c in texto for c in claves):
            return cat
    return "otro"


def _primer_nombre(brief: dict) -> str:
    for part in brief["forma"].get("participantes", []):
        if part.get("protagonico"):
            return part["nombre"]
    return "Ana"


def hora_por_defecto(brief: dict) -> str:
    cat = clasificar(brief["marca"].get("producto", ""), brief["marca"].get("nombre", ""))
    return {"radio": "las seis y cuarenta", "gastronomia": "la una de la tarde",
            "salud": "las ocho de la mañana", "educacion": "las siete de la noche",
            "tecnologia": "las nueve de la mañana"}.get(cat, "las ocho de la mañana")


def genero_por_nombre(nombre: str) -> str:
    return "f" if nombre.strip().lower() in [n.lower() for n in NOMBRES_F] else "m"


def persona(brief: dict) -> dict:
    """Ficha derivada del segmento, la ciudad y el producto."""
    cat = clasificar(brief["marca"].get("producto", ""), brief["marca"].get("nombre", ""))
    lex = LEXICO[cat]
    seg = brief["segmento"]
    edad = (seg["edad_min"] + seg["edad_max"]) // 2
    ciudad = brief["ubicacion"].get("ciudad", "")

    if seg["sexo"] == "f":
        nombre = NOMBRES_F[edad % len(NOMBRES_F)]
    elif seg["sexo"] == "m":
        nombre = NOMBRES_M[edad % len(NOMBRES_M)]
    else:
        nombre = (NOMBRES_F if edad % 2 == 0 else NOMBRES_M)[edad % 10]

    barrios = BARRIOS.get(ciudad, BARRIOS["default"])
    oficios = OFICIOS.get(cat, OFICIOS["otro"])

    # el índice se deriva de la marca: dos briefs distintos no dan la misma ficha
    semilla = sum(ord(c) for c in brief["marca"].get("nombre", "")) + edad

    return {
        "perfil": {"nombre": nombre, "edad": edad,
                   "ocupacion": oficios[semilla % len(oficios)],
                   "barrio": barrios[semilla % len(barrios)],
                   "nivel": T4},
        "consumo": {"cuando": f"de {seg['edad_min']} a {seg['edad_max']} años, en la semana",
                    "donde": "en el celular, casi siempre de pie",
                    "dispositivo": "celular",
                    "nivel": T3},
        "conflicto": {"problema": lex["problema"], "objecion": lex["objecion"],
                      "detonante": lex["detonante"], "nivel": T4},
        "lenguaje": {"diria": list(lex["diria"]), "no_diria": list(lex["no_diria"]),
                     "nivel": T1},
        "anti_persona": {"quien_no_es": lex["anti"], "nivel": T3},
    }


def premisas(brief: dict, ficha: dict) -> dict:
    """Tres premisas construidas sobre el conflicto del producto."""
    marca = brief["marca"]["nombre"]
    producto = brief["marca"]["producto"]
    cat = clasificar(producto, marca)
    lex = LEXICO[cat]
    prota = _primer_nombre(brief)
    ciudad = brief["ubicacion"].get("ciudad", "")

    return {"premisas": [
        {"id": "A",
         "caracter": f"{prota}, que carga todos los días con lo mismo",
         "conflicto": lex["problema"],
         "desenlace": f"encuentra en {marca} algo que le devuelve un minuto",
         "proposicion": (f"{prota} vive con un problema —{lex['problema']}— "
                         f"hasta que {marca} le devuelve el control."),
         "usa_oportunidad": False, "nivel": T4},
        {"id": "B",
         "caracter": f"{prota}, que ya probó algo parecido y no le sirvió",
         "conflicto": lex["objecion"],
         "desenlace": lex["detonante"],
         "proposicion": (f"{prota} no le da otra oportunidad a {marca} —{lex['objecion']}— "
                         f"hasta que descubre que hace justo lo que necesitaba."),
         "usa_oportunidad": True, "nivel": T3},
        {"id": "C",
         "caracter": "Alguien que no es el público habitual",
         "conflicto": lex["anti"],
         "desenlace": f"entiende para quién es {marca} al ver a quién no le habla",
         "proposicion": (f"Un destinatario ajeno —{lex['anti']}— descubre que {marca} "
                         f"no es para él, y eso define el mensaje."),
         "usa_oportunidad": False, "nivel": T4},
    ]}


def _cerrar(frase: str) -> str:
    """Cierra la frase sin duplicar el signo: ? y ! no llevan punto."""
    f = frase.strip()
    if not f:
        return f
    return f if f[-1] in ".?!" else f + "."


def _tc(seg: int) -> str:
    return f"{seg // 60:02d}:{seg % 60:02d}"


def escaleta(brief: dict, premisa: dict) -> dict:
    from . import espacio as esp_mod

    dur = brief["forma"]["duracion_objetivo_s"]
    tipo = brief["forma"]["tipo"]
    cp = "directa" if tipo == "publicitario" else "indirecta"

    # el espacio se hereda del briefing si está fijado; si no, se sugiere por rubro
    esp = brief.get("espacio") or {"modo": "auto"}
    if esp.get("modo") == "fijo":
        espacio = {k: esp[k] for k in ("tipo", "local", "momento")}
    else:
        rubro = clasificar(brief["marca"].get("producto", ""),
                           brief["marca"].get("nombre", ""))
        espacio = esp_mod.sugerido(rubro, brief["ubicacion"].get("ciudad", ""))

    hook = min(3, max(2, dur // 6))
    resto = dur - hook
    cortes = [0, hook,
              hook + max(2, round(resto * 0.22)),
              hook + max(4, round(resto * 0.55)),
              hook + max(6, round(resto * 0.80)),
              dur]

    if dur < 30:
        funciones = ["hook", "conflicto", "desenlace", "cierre"]
        cortes = [0, hook, hook + max(2, round(resto * 0.35)),
                  hook + max(5, round(resto * 0.70)), dur]
    else:
        funciones = ["hook", "planteamiento", "conflicto", "desenlace", "cierre"]

    descripciones = {
        "hook": "Plano cerrado. El gesto cotidiano que dispara la historia.",
        "planteamiento": "Se entiende dónde está y qué está evitando.",
        "conflicto": "La objeción aparece en pantalla, sin decirla del todo.",
        "desenlace": "El producto resuelve. Sin subrayarlo.",
        "cierre": "Rótulo con el nombre de la marca.",
    }
    beats = []
    for i, f in enumerate(funciones):
        beats.append({
            "tc_in": _tc(cortes[i]), "tc_out": _tc(cortes[i + 1]),
            "funcion": f, "descripcion": descripciones[f],
            "espacio": dict(espacio),
            "cuarta_pared": ("indirecta_con_tag" if (f == "cierre" and tipo == "sketch") else cp),
        })
    return {"beats": beats, "duracion_estimada_s": float(dur),
            "cierre": "Rótulo de marca"}


def guion(brief: dict, ficha: dict, premisa: dict, esc: dict) -> dict:
    """Guion compuesto con el material real del briefing."""
    marca = brief["marca"]["nombre"]
    producto = brief["marca"]["producto"]
    cat = clasificar(producto, marca)
    lex = LEXICO[cat]
    prota = _primer_nombre(brief).upper()
    tono = brief["forma"]["tono"]
    tipo = brief["forma"]["tipo"]
    dur = brief["forma"]["duracion_objetivo_s"]
    objetivo = set(brief.get("objetivo", []))

    frase = (brief["forma"].get("especificaciones") or "").strip("«»\" ")
    if not frase:
        frase = f"{marca}, para lo de todos los días."

    par = {"tipo": "parenthetical", "texto": "(a cámara)"} if tipo == "publicitario" else None

    # el espacio viene de la escaleta; si no, se sugiere por rubro
    from . import espacio as esp_mod
    beats_esp = (esc or {}).get("beats") or []
    espacio = beats_esp[0].get("espacio") if beats_esp else None
    if not espacio:
        esp_brief = brief.get("espacio") or {"modo": "auto"}
        if esp_brief.get("modo") == "fijo":
            espacio = {k: esp_brief[k] for k in ("tipo", "local", "momento")}
        else:
            espacio = esp_mod.sugerido(cat, brief["ubicacion"].get("ciudad", ""))
    enc = esp_mod.encabezado(espacio)

    p: list[dict] = [
        {"tipo": "scene_heading", "tc": "00:00", "texto": f"HOOK — {enc}",
         "espacio": dict(espacio)},
        {"tipo": "action",
         "texto": f"{prota}, {ficha['perfil']['edad']}, {lex['accion']}."},
        {"tipo": "character", "texto": prota},
    ]
    if par:
        p.append(par)
    p.append({"tipo": "dialogue", "texto": lex["gancho"].format(hora=hora_por_defecto(brief))})

    if dur < 30:
        p += [
            {"tipo": "action", "texto": f"Lo piensa dos segundos. Ahí está {producto.lower()}."},
            {"tipo": "character", "texto": prota},
            {"tipo": "dialogue", "texto": frase},
        ]
    else:
        p += [
            {"tipo": "transition", "texto": "CORTE A:"},
            {"tipo": "scene_heading", "tc": "00:09", "texto": enc,
             "espacio": dict(espacio)},
            {"tipo": "action", "texto": "Se le nota la duda en la cara."},
            {"tipo": "character", "texto": prota},
        ]
        if par:
            p.append(par)
        p += [
            {"tipo": "dialogue", "texto": _cerrar(ficha["lenguaje"]["diria"][0])},
            {"tipo": "action", "texto": "Lo prueba. No dice nada, pero se le cambia la cara."},
            {"tipo": "character", "texto": prota},
            {"tipo": "dialogue", "texto": frase},
        ]

    # material adicional proporcional a la duración
    for _ in range(max(0, (dur - 30) // 15)):
        p += [
            {"tipo": "action", "texto": "Un plano del detalle que importa."},
            {"tipo": "character", "texto": prota},
            {"tipo": "dialogue", "texto": _cerrar(ficha["lenguaje"]["diria"][1])},
        ]

    # llamado a la acción cuando el briefing lo pide
    if {"cta", "ventas", "seguidores"} & objetivo:
        cta = {"ventas": f"Pide el tuyo en {marca}.",
               "cta": f"Escríbenos y te contamos.",
               "seguidores": "Síguenos para más."}
        clave = next((k for k in ("ventas", "cta", "seguidores") if k in objetivo), "cta")
        p += [
            {"tipo": "character", "texto": prota},
            {"tipo": "dialogue", "texto": cta[clave]},
        ]

    p += [
        {"tipo": "scene_heading", "tc": "00:25", "texto": f"CIERRE — {enc}",
         "espacio": dict(espacio)},
        {"tipo": "action", "texto": lex["cierre"]},
        {"tipo": "title", "texto": marca.upper()},
        {"tipo": "transition", "texto": "CORTE A NEGRO."},
    ]

    if tono == "marcado":
        for parrafo in p:
            if parrafo["tipo"] == "dialogue" and "vos" not in parrafo["texto"]:
                parrafo["texto"] = parrafo["texto"].replace("usted", "vos")

    return {"parrafos": p,
            "meta": {"duracion_objetivo_s": dur, "tipo": tipo, "tono": tono,
                     "nivel_global": T4}}


def research(brief: dict) -> dict:
    """Investigación local: no inventa competidores, declara el vacío."""
    cat = clasificar(brief["marca"].get("producto", ""), brief["marca"].get("nombre", ""))
    ciudad = brief["ubicacion"].get("ciudad", "")
    modo = brief.get("competencia", {}).get("modo", "ambas")

    if modo == "ninguna":
        return {
            "competencia": {"modo_solicitado": "ninguna", "de_marca": [],
                            "de_feed": [], "sin_datos": True},
            "mercado": {"tendencias": []},
            "oportunidad": {"texto": "El usuario omitió el análisis de competencia.", "nivel": T4},
            "fuentes_total": 0,
            "generado_localmente": True,
        }

    feed = []
    if modo in ("feed", "ambas"):
        feed = [
            {"patron": "Testimonio de una sola persona a cámara, sin música",
             "ejemplo": "Piezas de 15 a 25 s que empiezan con una frase cotidiana",
             "fuentes": [], "nivel": T3},
            {"patron": "Antes y después con corte seco",
             "ejemplo": "El cambio se muestra, no se explica",
             "fuentes": [], "nivel": T3},
        ]

    return {
        "competencia": {"modo_solicitado": modo, "de_marca": [], "de_feed": feed,
                        "sin_datos": True},
        "mercado": {"tendencias": []},
        "oportunidad": {
            "texto": (f"Nadie en {ciudad} está usando el formato de testimonio directo "
                      f"para {cat.replace('_', ' ')}."),
            "nivel": T3},
        "fuentes_total": 0,
        "generado_localmente": True,
    }




