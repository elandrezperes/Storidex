"""Punto de entrada alternativo: ejecuta el pipeline sin interfaz.

Útil para correr los tres casos en lote y guardar los artefactos, sin abrir
el navegador. Respeta el modo seco igual que la app.

    python pipeline.py examples/caso_01_radio.json
"""
from __future__ import annotations

import json
import os
import sys

from core import export_fdx, export_pdf
from core.phases import (p0_brief, p1_research, p2_persona, p3_premisas,
                         p4_escaleta, p5_guion, p6_qa)


def correr(ruta_brief: str) -> dict:
    with open(ruta_brief, encoding="utf-8") as f:
        b0 = json.load(f)

    brief, ruta = p0_brief.ejecutar(b0)
    research = p1_research.ejecutar(brief)
    ficha = p2_persona.ejecutar(brief, research)
    persona_txt = p2_persona.inyectar(brief, ficha)
    premisas = p3_premisas.ejecutar(brief, ficha, research, persona_txt)

    premisa = premisas["premisas"][1]
    escaleta = p4_escaleta.ejecutar(brief, premisa, persona_txt)
    guion = p5_guion.ejecutar(brief, ficha, premisa, escaleta, persona_txt)
    qa = p6_qa.ejecutar(brief, ficha, guion, escaleta)

    if qa["hallazgos"]:
        guion = p5_guion.ejecutar(brief, ficha, premisa, escaleta, persona_txt,
                                  correccion=p6_qa.correccion_para(guion, qa))
        qa = p6_qa.ejecutar(brief, ficha, guion, escaleta)

    for nombre, datos in (("research.json", research), ("persona.json", ficha),
                          ("premisas.json", premisas), ("escaleta.json", escaleta),
                          ("guion.json", guion), ("qa.json", qa)):
        with open(os.path.join(ruta, nombre), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)

    export_fdx.guardar(guion, brief, os.path.join(ruta, "guion.fdx"))
    export_pdf.generar(guion, brief, os.path.join(ruta, "guion.pdf"))

    return {"run": ruta, "qa": qa, "nivel": qa["nivel_global"]}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    for arg in sys.argv[1:]:
        resultado = correr(arg)
        print(f"{arg} → {resultado['run']}")
        print(f"  nivel {resultado['nivel']} · "
              f"{len(resultado['qa']['hallazgos'])} hallazgo(s)")
        for h in resultado["qa"]["hallazgos"]:
            print(f"    - {h}")

