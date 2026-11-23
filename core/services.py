"""Adaptadores externos: referencias auditables y ayudas de producción opcionales."""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
import time
from urllib.parse import urlsplit, quote
from uuid import uuid4

from . import llm

PROVIDERS = {
    "firecrawl": ("Firecrawl", "FIRECRAWL_API_KEY", "Referencias web sobre tu mercado y otras marcas."),
    "trends": ("Google Trends", "FIRECRAWL_API_KEY", "Búsquedas en tendencia del país. No demuestra demanda local."),
    "vidiq": ("YouTube · vidIQ", "VIDIQ_API_KEY", "Videos de referencia para estudiar temas y formatos."),
    "elevenlabs": ("ElevenLabs", "ELEVENLABS_API_KEY", "Lectura sintética para explorar el ritmo del diálogo."),
    "canva": ("Canva", "CANVA_ACCESS_TOKEN", "Abre una copia editable del PDF del guion."),
}


def states():
    result = {}
    for key, (name, credential, purpose) in PROVIDERS.items():
        configured = bool(os.getenv(credential, "").strip())
        if key == "elevenlabs":
            configured = configured and bool(os.getenv("ELEVENLABS_VOICE_ID", "").strip())
        result[key] = {"name": name, "configured": configured, "purpose": purpose,
                       "status": "ready" if configured else "not_configured"}
    return result


def _headers(key):
    return {"Authorization": "Bearer " + os.environ[key]}


def _json(provider, url, **kwargs):
    data, _ = llm.servicio_json(provider, url, **kwargs)
    if not isinstance(data, dict) or data.get("success") is False or data.get("error"):
        raise llm.ServicioNoDisponible("El servicio no devolvió datos utilizables.")
    return data


def _cached(provider, options, fetch):
    run = llm._RUN.get()
    path = None
    if run is not None:
        directory = run.parent / ".services-cache"
        directory.mkdir(exist_ok=True)
        digest = sha256(json.dumps([provider, options], sort_keys=True).encode()).hexdigest()
        path = directory / f"{digest}.json"
        if path.exists() and time.time() - path.stat().st_mtime < 86400:
            llm.registrar_servicio(provider, "success", cache=True)
            return json.loads(path.read_text()), True
    result = fetch()
    if path is not None:
        llm._guardar_json(path, result)
    llm.registrar_servicio(provider, "success", units=1)
    return result, False


def _web(brief):
    location = brief["ubicacion"]
    query = f'{brief["marca"]["producto"]} {location["ciudad"]} {location["pais"]}'[:350]
    return _json("firecrawl", "https://api.firecrawl.dev/v2/search", retry=True,
                 headers=_headers("FIRECRAWL_API_KEY"), body={"query": query, "limit": 4})


def _country(brief):
    value = brief["ubicacion"]["pais"].strip()
    aliases = {"ecuador": "EC", "colombia": "CO", "perú": "PE", "peru": "PE",
               "méxico": "MX", "mexico": "MX", "españa": "ES", "chile": "CL",
               "argentina": "AR", "estados unidos": "US"}
    country = aliases.get(value.casefold(), value.upper())
    return country if re.fullmatch(r"[A-Z]{2}", country) else None


def _trends(brief):
    country = _country(brief)
    if country is None:
        return {"records": [], "scope": "unsupported_country"}
    # No reintento de ejecución: los proveedores de Alexandria cobran por llamada.
    return _json("firecrawl", "https://api.firecrawl.dev/v2/scrape",
                 headers={**_headers("FIRECRAWL_API_KEY"), "x-request-id": str(uuid4())},
                 body={"alexandria": {"provider": "firecrawl-trends",
                       "capability": "trends/trending_now", "options": {"geo": country, "hours": 24}}})


def _youtube(brief):
    headers = {**_headers("VIDIQ_API_KEY"), "Accept": "application/json, text/event-stream"}
    url = "https://mcp.vidiq.com/mcp"
    initialized, response_headers = llm.servicio_json("vidiq", url, headers=headers, body={
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "storidex", "version": "1.0"}}})
    if "result" not in initialized:
        raise llm.ServicioNoDisponible("No se pudo iniciar la conexión con vidIQ.")
    session = next((v for k, v in response_headers.items() if k.lower() == "mcp-session-id"), None)
    headers["MCP-Protocol-Version"] = initialized["result"]["protocolVersion"]
    if session:
        headers["MCP-Session-Id"] = session
    llm.servicio_json("vidiq", url, headers=headers, body={
        "jsonrpc": "2.0", "method": "notifications/initialized"})
    args = {"query": brief["marca"]["producto"][:200], "type": ["video"], "limit": 4}
    if country := _country(brief):
        args["regionCode"] = country
    response = _json("vidiq", url, headers=headers, body={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "vidiq_youtube_search", "arguments": args}})
    result = response.get("result", {})
    if result.get("isError"):
        raise llm.ServicioNoDisponible("YouTube no está disponible en este momento.")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                data = json.loads(block["text"])
                if isinstance(data, dict) and isinstance(data.get("results"), list):
                    return data
            except ValueError:
                continue
    raise llm.ServicioNoDisponible("YouTube no devolvió resultados estructurados.")


def _reference(source, url, text, brief, fetched_at, *, scope="contextual"):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        return None
    return {"fuente": source, "url": url[:1000], "hallazgo": text[:1500],
            "fecha": fetched_at, "mercado": brief["ubicacion"], "origen": "servicio_externo",
            "nivel": "T3", "veracidad": "sin_verificacion", "scope": scope}


def _references(key, data, brief, fetched_at):
    records = []
    if key == "firecrawl":
        web = data.get("data", {})
        web = web.get("web", []) if isinstance(web, dict) else web
        for item in web if isinstance(web, list) else []:
            if isinstance(item, dict):
                records.append(_reference("firecrawl", item.get("url", ""),
                    str(item.get("title", "")) + ". " + str(item.get("description", "")), brief, fetched_at))
    elif key == "vidiq":
        for item in data.get("results", []):
            video = item.get("id", "") if isinstance(item, dict) else ""
            if isinstance(video, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
                records.append(_reference("youtube", f"https://www.youtube.com/watch?v={video}",
                    str(item.get("title", "")) + ". " + str(item.get("description") or ""),
                    brief, fetched_at, scope="creative_reference"))
    else:
        envelope = data.get("data", {})
        calls = envelope.get("alexandria", []) if isinstance(envelope, dict) else []
        if any(call.get("error") for call in calls):
            raise llm.ServicioNoDisponible("Google Trends no estuvo disponible.")
        # Solo títulos pertinentes al producto. El resto queda en el artefacto bruto.
        words = {w for w in re.findall(r"\w+", brief["marca"]["producto"].casefold()) if len(w) > 3}
        for call in calls:
            payload = call.get("data", {})
            rows = call.get("records") or (payload.get("trends", payload.get("records", [])) if isinstance(payload, dict) else payload)
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                title = row.get("term") or row.get("title") or row.get("query") or row.get("trend") or ""
                if isinstance(title, str) and words.intersection(re.findall(r"\w+", title.casefold())):
                    records.append(_reference("trends", payload.get("source_url") or "https://trends.google.com/trending?geo=" + _country(brief),
                        "Tendencia nacional observada: " + title + ". No acredita interés del segmento ni demanda local.",
                        brief, fetched_at, scope="national_trending_24h"))
    return [record for record in records if record][:4]


def research(brief, dossier):
    dossier = deepcopy(dossier)
    status = states()
    if brief["competencia"]["modo"] == "ninguna" or llm.DRY:
        for key in ("firecrawl", "trends", "vidiq"):
            status[key]["status"] = "skipped"
        return dossier, status
    for key, fetch in (("firecrawl", _web), ("trends", _trends), ("vidiq", _youtube)):
        if not status[key]["configured"]:
            continue
        try:
            options = {"product": brief["marca"]["producto"], "location": brief["ubicacion"], "version": 1}
            def fetch_snapshot():
                snapshot = {"fetched_at": datetime.now(timezone.utc).isoformat(), "data": fetch(brief)}
                _references(key, snapshot["data"], brief, snapshot["fetched_at"])
                return snapshot

            snapshot, cached = _cached(key, options, fetch_snapshot)
            refs = _references(key, snapshot["data"], brief, snapshot["fetched_at"])
            status[key].update(status="success" if refs else "no_relevant_data", cached=cached,
                               fetched_at=snapshot["fetched_at"], count=len(refs))
            for ref in refs:
                ref["id"] = f"E{len(dossier['referencias']) + 1}"
                dossier["referencias"].append(ref)
            run = llm._RUN.get()
            if run is not None:
                llm._guardar_json(run / f"service_{key}.json", snapshot)
        except (llm.ServicioNoDisponible, ValueError, TypeError, KeyError):
            status[key]["status"] = "unavailable"
            llm.error_servicio(key)
            llm.registrar_servicio(key, "unavailable")
    return dossier, status


def speech(script):
    if not states()["elevenlabs"]["configured"]:
        raise llm.ServicioNoDisponible("La lectura sintética aún no está configurada.")
    text = "\n".join(p["texto"] for p in script["parrafos"] if p["tipo"] == "dialogue")
    if not text.strip() or len(text) > 3000:
        raise llm.ServicioNoDisponible("La lectura requiere entre 1 y 3 000 caracteres de diálogo.")
    voice = os.environ["ELEVENLABS_VOICE_ID"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", voice):
        raise llm.ServicioNoDisponible("La voz configurada no es válida.")
    data = _json("elevenlabs", f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, body={
                     "text": text, "model_id": "eleven_multilingual_v2"})
    audio = base64.b64decode(data["audio_base64"], validate=True)
    times = (data.get("normalized_alignment") or data.get("alignment") or {}).get("character_end_times_seconds", [])
    duration = max(times) if times else None
    llm.registrar_servicio("elevenlabs", "success", units=len(text))
    return audio, {"duration_s": duration, "characters": len(text), "synthetic": True,
                   "scope": "Solo diálogo leído por una voz sintética. Excluye acciones, pausas de puesta en escena y montaje."}


def canva_import(pdf, title):
    if not states()["canva"]["configured"]:
        raise llm.ServicioNoDisponible("La exportación a Canva aún no está configurada.")
    metadata = {"title_base64": base64.b64encode(title[:100].encode()).decode(), "mime_type": "application/pdf"}
    data = _json("canva", "https://api.canva.com/rest/v1/imports", body=pdf,
                 headers={**_headers("CANVA_ACCESS_TOKEN"), "Content-Type": "application/octet-stream",
                          "Import-Metadata": json.dumps(metadata)})
    job = data.get("job", {})
    if not isinstance(job.get("id"), str):
        raise llm.ServicioNoDisponible("Canva no confirmó la importación.")
    llm.registrar_servicio("canva", "submitted", units=1)
    return {"job_id": job["id"], "status": job.get("status", "in_progress")}


def canva_status(job):
    data = _json("canva", "https://api.canva.com/rest/v1/imports/" + quote(job["job_id"], safe=""),
                 headers=_headers("CANVA_ACCESS_TOKEN"), retry=True)
    result = data.get("job", {})
    designs = result.get("result", {}).get("designs", [])
    url = designs[0].get("urls", {}).get("edit_url") if designs else None
    if url and (urlsplit(url).scheme != "https" or urlsplit(url).hostname not in {"www.canva.com", "canva.com"}):
        url = None
    return {**job, "status": result.get("status", "in_progress"), "edit_url": url}


def media_id(script):
    return sha256(json.dumps(script, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def media_state(directory, script):
    path = directory / f"media_{media_id(script)}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def production(directory, brief, script, action):
    """El bloqueo del proyecto lo mantiene el llamante. Nunca reenvía una escritura incierta."""
    from . import export_pdf
    from tempfile import TemporaryDirectory

    state = media_state(directory, script)
    provider = "elevenlabs" if action == "voz" else "canva"
    if not states()[provider]["configured"]:
        raise llm.ServicioNoDisponible("Este servicio aún no está configurado en Storidex.")
    path = directory / f"media_{media_id(script)}.json"
    previous = state.get(provider, {})
    if previous.get("status") in {"unknown", "submitting"}:
        raise llm.ServicioNoDisponible("La solicitud anterior no pudo confirmarse. Revisa el proveedor antes de repetirla.")
    if provider == "elevenlabs" and previous.get("status") == "success":
        return state
    if provider == "canva" and previous.get("job_id"):
        state[provider] = canva_status(previous)
        llm._guardar_json(path, state)
        return state
    state[provider] = {"status": "submitting"}
    llm._guardar_json(path, state)
    try:
        if provider == "elevenlabs":
            audio, info = speech(script)
            audio_path = directory / f"speech_{media_id(script)}.mp3"
            audio_path.write_bytes(audio)
            state[provider] = {**info, "status": "success"}
        else:
            with TemporaryDirectory() as folder:
                from pathlib import Path
                pdf = Path(folder) / "guion.pdf"
                export_pdf.generar(script, brief, str(pdf))
                state[provider] = canva_import(pdf.read_bytes(), "Storidex · " + brief["marca"]["nombre"])
    except Exception:
        state[provider] = {"status": "unknown"}
        llm._guardar_json(path, state)
        llm.error_servicio(provider)
        raise llm.ServicioNoDisponible("No se pudo confirmar la operación. Se conservó el diagnóstico y no se repetirá automáticamente.") from None
    llm._guardar_json(path, state)
    return state
