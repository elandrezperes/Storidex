"""Piloto técnico reproducible; no sustituye jueces, público ni lectura cronometrada.

python -m tools.piloto [--live] [--case caso_02_producto] [--output output/piloto]
Las credenciales se reciben del entorno. Nunca se imprimen ni se guardan.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import platform
import random
from datetime import datetime, timezone
from xml.etree import ElementTree

from core import contracts, export_fdx, export_pdf, llm
import sites_backend


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def call(path, data=None):
    raw = json.dumps(data).encode() if data is not None else b""
    state = []
    env = {"REQUEST_METHOD": "GET" if data is None else "POST", "PATH_INFO": path,
           "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw),
           "HTTP_AUTHORIZATION": "Bearer " + os.environ["STORIDEX_PROXY_SECRET"],
           "HTTP_X_STORIDEX_VIEWER": "b" * 64}
    body = b"".join(sites_backend.application(env, lambda status, headers: state.append(status)))
    if state[0] != "200 OK":
        raise RuntimeError(json.loads(body).get("error", state[0]))
    return body if path.endswith(("/pdf", "/fdx")) else json.loads(body)


def run(args):
    llm.DRY = not args.live
    if args.sin_busqueda:
        os.environ["STORIDEX_RESEARCH_ENABLED"] = "false"
    if args.live and not llm.hay_llave():
        raise RuntimeError("Falta configurar la clave de redacción.")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["STORIDEX_RUNS_DIR"] = str(output / "runs")
    os.environ.setdefault("STORIDEX_PROXY_SECRET", "piloto-local")
    root = Path(__file__).resolve().parents[1]
    sources = sorted([*root.glob("core/**/*.py"), *root.glob("core/prompts/*.md"),
                      *root.glob("core/schemas/*.json"), root / "sites_backend.py"])
    manifest = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(), "tipo": "piloto_tecnico",
        "modo": "API_real" if args.live else "seco", "python": platform.python_version(),
        "busqueda": "desactivada por decisión del autor" if args.sin_busqueda else "según disponibilidad",
        "modelos": {"redaccion": llm.MODEL_WRITE, "intermedias": llm.MODEL_MID,
                    "research": llm.MODEL_RESEARCH},
        "limite_estimado_por_run_usd": llm.MAX_COST,
        "max_output_tokens": llm.OUTPUT_LIMIT, "seed_orden": 231123,
        "seleccion_premisa": "B, fijada antes de generar", "replicas_por_condicion": 1,
        "condiciones": ["MIIA", "prompt_unico_enriquecido"],
        "evaluacion_humana": "pendiente; no hay participantes ni puntuaciones inventadas",
        "alcance": "Tres casos de conveniencia; no permite demostrar superioridad ni generalizar.",
        "archivos_sha256": {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    write(output / "manifest.json", manifest)
    cases = args.case or ["caso_01_radio", "caso_02_producto", "caso_03_servicio"]
    results, blind = [], []
    for case in cases:
        print(f"Iniciando {case}", flush=True)
        source = json.loads((root / "examples" / f"{case}.json").read_text())
        case_dir = output / case
        case_dir.mkdir()
        write(case_dir / "brief_congelado.json", source)
        record = {"caso": case, "condicion": "MIIA"}
        directory = None
        try:
            project = call("/api/proyectos", source)
            path = "/api/proyectos/" + project["id"]
            directory = sites_backend._root() / "usuarios" / ("b" * 64) / project["id"]
            for action in ("investigar", "persona"):
                project = call(path + "/" + action, {})
            project = call(path + "/audiencia", {"version": 1, "campos": {}})
            project = call(path + "/premisas", {})
            project = call(path + "/escaleta", {"premisa": "B"})
            for _ in range(5):
                project = call(path + "/preparar", {})
                if project.get("guion") or project.get("agotado"):
                    break
            directory = sites_backend._root() / "usuarios" / ("b" * 64) / project["id"]
            record.update({"run_id": project["id"], "entregado": bool(project.get("guion")),
                           "agotado": project.get("agotado", False)})
            research = sites_backend._read(directory, "research")
            record["fuentes_grounding"] = len(research.get("_fuentes_grounding", []))
            record["sin_busqueda"] = research.get("sin_busqueda", False)
            if project.get("guion"):
                fdx, pdf = call(path + "/fdx"), call(path + "/pdf")
                ElementTree.fromstring(fdx)
                assert pdf.startswith(b"%PDF")
                (case_dir / "miia.fdx").write_bytes(fdx)
                (case_dir / "miia.pdf").write_bytes(pdf)
                blind.append((case, "MIIA", sites_backend._read(directory, "guion")))
                record["exportaciones_validas"] = True
            record["costo_estimado_usd"] = sites_backend._read(directory, "trace").get("costo_estimado", 0)
            results.append(record)
        except Exception as exc:
            results.append({"caso": case, "condicion": "MIIA", "entregado": False,
                            "tipo_error": type(exc).__name__, "mensaje": str(exc)[:300]})
        try:
            # Igual información documental y recursos; sin ficha ni escaleta generada.
            baseline_dir = case_dir / "baseline"
            baseline_dir.mkdir()
            brief = sites_backend._read(directory, "brief")
            research = sites_backend._read(directory, "research")
            frozen = {"brief": brief, "research": research}
            write(baseline_dir / "entrada_congelada.json", frozen)
            from core import local
            with llm.auditar(baseline_dir):
                baseline = llm.pedir_validado(llm.cargar_prompt("v1_baseline_piloto.md"),
                    json.dumps(frozen, ensure_ascii=False),
                    lambda data: contracts.validar("p5_guion", data), esquema="p5_guion", modelo=llm.MODEL_WRITE,
                    seco=local.guion(brief, local.persona(brief),
                        local.premisas(brief, local.persona(brief))["premisas"][1],
                        local.escaleta(brief, {"proposicion": "Caso de prueba"})) if llm.DRY else None,
                    temperatura=0.65)
            write(baseline_dir / "guion.json", baseline)
            (case_dir / "baseline.fdx").write_bytes(export_fdx.generar(baseline, brief))
            export_pdf.generar(baseline, brief, str(case_dir / "baseline.pdf"))
            blind.append((case, "prompt_unico_enriquecido", baseline))
            results.append({"caso": case, "condicion": "prompt_unico_enriquecido", "entregado": True,
                "costo_estimado_usd": json.loads((baseline_dir / "trace.json").read_text())["costo_estimado"]})
        except Exception as exc:
            results.append({"caso": case, "condicion": "prompt_unico_enriquecido", "entregado": False,
                            "tipo_error": type(exc).__name__, "mensaje": str(exc)[:300]})
        write(output / "resultados.json", results)
        print(f"Finalizado {case}: {results[-1]['entregado']}", flush=True)
    random.Random(231123).shuffle(blind)
    package = output / "guiones_ciegos"
    package.mkdir()
    mapping = []
    for i, (case, condition, script) in enumerate(blind, 1):
        identifier = f"G{i:02}"
        write(package / f"{identifier}.json", {"parrafos": script["parrafos"]})
        brief = json.loads((output / case / "brief_congelado.json").read_text())
        export_pdf.generar(script, brief, str(package / f"{identifier}.pdf"))
        mapping.append({"id": identifier, "caso": case, "condicion": condition})
    write(output / "clave_investigador.json", mapping)
    write(output / "revision_humana_pendiente.json", {
        "estado": "pendiente", "lecturas_cronometradas": [], "jueces": [], "publico": []})
    print(json.dumps({"output": str(output), "condiciones_ejecutadas": len(results),
                      "entregas": sum(r['entregado'] for r in results)}, ensure_ascii=False))
    return 0 if all(r["entregado"] for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--sin-busqueda", action="store_true")
    parser.add_argument("--case", action="append")
    parser.add_argument("--output", required=True)
    raise SystemExit(run(parser.parse_args()))
