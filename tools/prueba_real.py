"""Reproduce el flujo real contra OpenAI usando una llave del entorno.

Uso:
    OPENAI_API_KEY=sk-... python -m tools.prueba_real "Nombre de marca" "Producto"

Imprime cada fase y, si algo falla, el error completo con el texto que devolvió
el modelo. Sirve para diagnosticar sin depender de la interfaz.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import llm  # noqa: E402
from core.phases import (p0_brief, p1_research, p2_persona, p3_premisas,  # noqa: E402
                         p4_escaleta, p5_guion, p6_qa)


def main() -> int:
    if not llm.hay_llave():
        print("Falta OPENAI_API_KEY en el entorno.")
        return 2

    marca = sys.argv[1] if len(sys.argv) > 1 else "Veterinaria Patitas"
    producto = sys.argv[2] if len(sys.argv) > 2 else "Clínica veterinaria premium"

    brief = {
        "marca": {"nombre": marca, "producto": producto, "sitio_web": None},
        "ubicacion": {"pais": "Ecuador", "provincia": "Azuay", "ciudad": "Cuenca"},
        "segmento": {"edad_min": 25, "edad_max": 45, "sexo": "ambos",
                     "nse": "C+", "nse_escala_pais": "EC"},
        "objetivo": ["cta"],
        "forma": {
            "participantes": [{"nombre": "Sofía", "protagonico": True}],
            "tipo": "sketch",
            "especificaciones": "",
            "indicaciones": "",
            "tono": "moderado",
            "duracion_objetivo_s": 60,
        },
        "competencia": {"modo": "marca"},
    }

    print(f"MODELO: {llm.MODEL_MID} / {llm.MODEL_WRITE}\n")

    try:
        print("→ P0 briefing")
        b, ruta = p0_brief.ejecutar(brief, raiz_runs="runs")
        print(f"  ok · {ruta}")

        print("→ P1 investigación")
        res = p1_research.ejecutar(b)
        print(f"  ok · sin_datos={res['competencia']['sin_datos']}")

        print("→ P2 persona")
        per = p2_persona.ejecutar(b, res)
        print(f"  ok · {per['perfil']['nombre']}, {per['perfil']['edad']}")

        print("→ P3 premisas")
        pre = p3_premisas.ejecutar(b, per, res, p2_persona.inyectar(b, per))
        for p in pre["premisas"]:
            print(f"  {p['id']}: {p['proposicion'][:70]}")

        print("→ P4 escaleta")
        esc = p4_escaleta.ejecutar(b, pre["premisas"][1], p2_persona.inyectar(b, per))
        print(f"  ok · {len(esc['beats'])} unidades")

        print("→ P5 guion")
        gu = p5_guion.ejecutar(b, per, pre["premisas"][1], esc,
                               p2_persona.inyectar(b, per))
        print(f"  ok · {len(gu['parrafos'])} párrafos")

        print("→ P6 control")
        qa = p6_qa.ejecutar(b, per, gu, esc)
        print(f"  ok · hallazgos={qa['hallazgos']}")

        print("\nGUION\n" + "-" * 60)
        for p in gu["parrafos"]:
            print(f"{p['tipo']:14} {p['texto']}")
        return 0

    except Exception as e:  # noqa: BLE001
        print(f"\nFALLÓ: {type(e).__name__}: {e}\n")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

