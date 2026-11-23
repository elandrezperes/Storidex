"""Contratos de servicios, independencia de evidencia y escrituras idempotentes."""
import base64
from copy import deepcopy
import json
from pathlib import Path

import pytest

from core import export_pdf, llm, referencias, services
from core.phases import p1_research
from tests.test_sites import preparar_proyecto, api  # noqa: F401


@pytest.fixture
def brief():
    return json.loads(Path("examples/caso_02_producto.json").read_text())


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for _, credential, _ in services.PROVIDERS.values():
        monkeypatch.delenv(credential, raising=False)


def test_no_credentials_does_not_call_network(brief, monkeypatch):
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.setattr(llm, "servicio_json", lambda *a, **k: pytest.fail("Unexpected API call"))
    dossier = referencias.congelar(brief)
    result, states = services.research(brief, dossier)
    assert result == dossier
    assert all(not state["configured"] for state in states.values())


def test_research_cached_snapshot_and_provenance(brief, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-secret")
    calls = []

    def request(provider, url, **kwargs):
        calls.append(url)
        if url.endswith("search"):
            return {"data": {"web": [{"url": "https://example.org/reference", "title": "Producto", "description": "Dato observado"}]}}, {}
        return {"data": {"alexandria": [{"data": {"trends": [{"term": "Tema ajeno"}]}}]}}, {}

    monkeypatch.setattr(llm, "servicio_json", request)
    original = referencias.congelar(brief)
    with llm.auditar(tmp_path):
        first, states = services.research(brief, original)
        second, repeated = services.research(brief, original)
    assert len(calls) == 2
    assert original["referencias"] == []
    assert first == second
    ref = first["referencias"][0]
    assert ref["nivel"] == "T3" and ref["origen"] == "servicio_externo"
    assert states["trends"]["status"] == "no_relevant_data"
    assert repeated["firecrawl"]["cached"] is True
    assert (tmp_path / "service_firecrawl.json").exists()
    assert "test-secret" not in (tmp_path / "trace.json").read_text()


def test_trends_keeps_scope_and_provider_source(brief):
    brief["marca"]["producto"] = "Café artesanal"
    data = {"data": {"alexandria": [{"data": {
        "source_url": "https://trends.firecrawl.dev/trending?geo=EC&hours=24",
        "trends": [{"term": "café nuevo"}, {"term": "fútbol"}],
    }}]}}
    refs = services._references("trends", data, brief, "2026-11-19")
    assert len(refs) == 1 and refs[0]["scope"] == "national_trending_24h"
    assert refs[0]["url"].startswith("https://trends.firecrawl.dev/")


def test_provider_failure_does_not_block_and_logs_safely(brief, tmp_path, monkeypatch):
    brief["marca"]["producto"] = "Producto sin caché"
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-secret")

    def fail(*args, **kwargs):
        raise llm.ServicioNoDisponible("test-secret should not leak")

    monkeypatch.setattr(llm, "servicio_json", fail)
    with llm.auditar(tmp_path):
        dossier, state = services.research(brief, referencias.congelar(brief))
    assert state["firecrawl"]["status"] == "unavailable"
    assert not dossier["referencias"]
    assert "test-secret" not in (tmp_path / "errors.json").read_text()
    assert not (tmp_path / "service_firecrawl.json").exists()


def test_external_pages_never_become_grounded_competitors(brief, monkeypatch):
    monkeypatch.setattr(llm, "DRY", False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fixture")
    monkeypatch.setattr(services, "_web", lambda b: {"data": {"web": [{"url": "https://example.org", "title": "Otra marca"}]}})
    monkeypatch.setattr(services, "_trends", lambda b: {})
    result = p1_research.ejecutar(brief)
    assert not result["competencia"]["de_marca"]
    assert result["dossier_referencias"]["referencias"][0]["fuente"] == "firecrawl"
    assert result["fuentes_total"] == 0


def test_http_rejects_redirect_destinations_before_network():
    with pytest.raises(llm.ServicioNoDisponible):
        llm.servicio_json("canva", "https://example.org/credentials")


def test_mcp_session_and_public_video_contract(brief, monkeypatch):
    monkeypatch.setenv("VIDIQ_API_KEY", "fixture")
    requests = []

    def request(provider, url, **kwargs):
        requests.append(kwargs)
        method = kwargs["body"]["method"]
        if method == "initialize":
            return {"result": {"protocolVersion": "2025-03-26"}}, {"Mcp-Session-Id": "session"}
        if method == "notifications/initialized":
            return {}, {}
        assert kwargs["headers"]["MCP-Session-Id"] == "session"
        assert kwargs["body"]["params"]["name"] == "vidiq_youtube_search"
        return {"result": {"structuredContent": {"results": [
            {"id": "abcdEFG1234", "kind": "video", "title": "Ejemplo"}]}}}, {}

    monkeypatch.setattr(llm, "servicio_json", request)
    data = services._youtube(brief)
    refs = services._references("vidiq", data, brief, "2026-11-19")
    assert len(requests) == 3
    assert refs[0]["url"] == "https://www.youtube.com/watch?v=abcdEFG1234"


def test_streamable_http_stops_after_rpc_result(monkeypatch):
    import io

    class Stream(io.BytesIO):
        headers = {"Content-Type": "text/event-stream"}

        def read(self, *args):
            pytest.fail("Must consume SSE events without waiting for the whole stream")

    class Opener:
        def open(self, request, **kwargs):
            return Stream(b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
                          b'data: {"jsonrpc":"2.0","id":2,\ndata: "result":{"content":[]}}\n\n')

    monkeypatch.setattr(llm, "build_opener", lambda *args: Opener())
    result, headers = llm.servicio_json("vidiq", "https://mcp.vidiq.com/mcp", body={"id": 2})
    assert result["result"] == {"content": []}


def test_speech_reads_dialogue_only_and_is_versioned(brief, tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fixture")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice1")
    script = {"parrafos": [{"tipo": "action", "texto": "No se lee"},
                           {"tipo": "dialogue", "texto": "Hola"}]}
    calls = []

    def request(*args, **kwargs):
        calls.append(kwargs["body"])
        return {"audio_base64": base64.b64encode(b"fake-audio").decode(),
                "alignment": {"character_end_times_seconds": [0.5, 1.2]}}, {}

    monkeypatch.setattr(llm, "servicio_json", request)
    with llm.auditar(tmp_path):
        services.production(tmp_path, brief, script, "voz")
        result = services.production(tmp_path, brief, script, "voz")
    assert calls == [{"text": "Hola", "model_id": "eleven_multilingual_v2"}]
    assert result["elevenlabs"]["duration_s"] == 1.2
    changed = deepcopy(script)
    changed["parrafos"][-1]["texto"] = "Otro diálogo"
    assert services.media_state(tmp_path, changed) == {}


def test_uncertain_write_is_not_replayed(brief, tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fixture")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice1")
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise llm.ServicioNoDisponible("timeout")

    monkeypatch.setattr(services, "speech", timeout)
    for _ in range(2):
        with pytest.raises(llm.ServicioNoDisponible):
            services.production(tmp_path, brief, {"parrafos": []}, "voz")
    assert len(calls) == 1


def test_canva_polls_existing_job_instead_of_importing_again(brief, tmp_path, monkeypatch):
    monkeypatch.setenv("CANVA_ACCESS_TOKEN", "fixture")
    monkeypatch.setattr(export_pdf, "generar",
                        lambda g, b, path: Path(path).write_bytes(b"pdf"))
    imports = []

    def submit(*args):
        imports.append(1)
        return {"job_id": "job1", "status": "in_progress"}

    monkeypatch.setattr(services, "canva_import", submit)
    monkeypatch.setattr(services, "canva_status", lambda job: {**job, "status": "success", "edit_url": "https://www.canva.com/design/example/edit"})
    services.production(tmp_path, brief, {"parrafos": []}, "canva")
    result = services.production(tmp_path, brief, {"parrafos": []}, "canva")
    assert len(imports) == 1 and result["canva"]["edit_url"]


def test_server_disallows_unconfigured_media_without_sending(api):
    path, project = preparar_proyecto(api)
    for _ in range(3):
        project = api(path + "/preparar", {})
    assert "guion" in project
    assert not project["services"]["elevenlabs"]["configured"]
    result = api(path + "/voz", {"version": 0}, expected=503)
    assert "configurado" in result["error"]
    api(path + "/audio", expected=404)
