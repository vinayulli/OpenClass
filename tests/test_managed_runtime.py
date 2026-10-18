import asyncio
import inspect
import json
import pytest


def test_runtime_mtls_transport_uses_google_access_credentials_and_client_certificate(monkeypatch):
    import google.auth
    from google.auth.transport import requests as google_requests
    from backend.runtime.client import post
    from backend.security import transport
    captured = {}
    credentials = object()
    monkeypatch.setattr(google.auth, "default", lambda **kwargs: (credentials, "project"))
    monkeypatch.setattr(transport, "workload_token", lambda: "signed-workload-token")
    def unexpected_ingress(audience):
        raise AssertionError("Runtime must use Google access credentials, not Cloud Run ID tokens")
    monkeypatch.setattr(transport, "ingress_token", unexpected_ingress)
    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"message": "verified"}
    class Session:
        def __init__(self, value):
            assert value is credentials
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def configure_mtls_channel(self):
            captured["certificate_configured"] = True
        def post(self, url, **kwargs):
            assert captured["certificate_configured"]
            captured.update(url=url, **kwargs)
            return Response()
    monkeypatch.setattr(google_requests, "AuthorizedSession", Session)
    url = "https://us-central1-aiplatform.mtls.googleapis.com/reasoningEngines/v1/projects/123/locations/us-central1/reasoningEngines/456/api/invoke"
    assert post(url, {"grant": "bound-grant"}) == {"message": "verified"}
    assert captured["url"] == url
    assert captured["headers"] == {"X-OpenClass-Workload-Token": "signed-workload-token"}
    assert captured["allow_redirects"] is False


def test_coordinator_transport_uses_audience_specific_ingress_and_separate_workload_token(monkeypatch):
    from google.auth.transport import requests as google_requests
    from google.auth.credentials import AnonymousCredentials
    from backend.runtime.client import post
    from backend.security import transport
    captured = {}
    monkeypatch.setattr(transport, "workload_token", lambda: "signed-workload-token")
    def ingress(audience):
        captured["audience"] = audience
        return "ingress-token"
    monkeypatch.setattr(transport, "ingress_token", ingress)
    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"ok": True}
    class Session:
        def __init__(self, credentials):
            assert isinstance(credentials, AnonymousCredentials)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def configure_mtls_channel(self):
            captured["certificate_configured"] = True
        def post(self, url, **kwargs):
            assert captured["certificate_configured"]
            captured.update(url=url, **kwargs)
            return Response()
    monkeypatch.setattr(google_requests, "AuthorizedSession", Session)
    assert post("https://openclass-example.run.app/api/internal/agent-actions", {"grant": "bound-grant"}) == {"ok": True}
    assert captured["audience"] == "https://openclass-example.run.app"
    assert captured["headers"] == {"Authorization": "Bearer ingress-token", "X-OpenClass-Workload-Token": "signed-workload-token"}
    assert captured["allow_redirects"] is False


def test_release_wiring_requires_real_distinct_identities_and_keeps_bootstrap():
    import runpy
    from pathlib import Path
    from backend.runtime.deployment import KINDS
    prepare = runpy.run_path(str(Path(__file__).parents[1]/"deployment/managed/wire-release.py"))["prepare"]
    trust = "agents.global.proj-123.system.id.goog"
    values = {"runtime_environment": {}, "web_environment": {}, "mcp_environment": {"data": {}, "github": {}}}
    resources = {name: "projects/123/locations/us-central1/reasoningEngines/"+str(index+1) for index, name in enumerate(sorted(KINDS))}
    identities = {name: f"spiffe://{trust}/resources/aiplatform/{resource}" for name, resource in resources.items()}
    identities["web"] = identities["web"].removeprefix("spiffe://")
    outputs = {name: {"value": value} for name, value in {
        "runtime_names": resources, "runtime_identities": identities,
        "application_identity": f"//{trust}/resources/run/projects/123/locations/us-central1/services/openclass",
        "application_url": "https://openclass-example.run.app",
        "mcp_service_urls": {"data": "https://data-example.run.app", "github": "https://github-example.run.app"},
    }.items()}
    result = prepare(values, outputs)
    assert result["web_environment"]["OPENCLASS_DEPLOYMENT_BOOTSTRAP"] == "true"
    assert result["runtime_environment"]["DATA_MCP_AUDIENCE"] == "https://data-example.run.app"
    assert result["enable_workload_bindings"] is True
    assert result["workload_principals"]["tutor"].startswith("principal://")
    assert values["runtime_environment"] == {}
    identities["teacher"] = identities["tutor"]
    with pytest.raises(ValueError, match="own identity"):
        prepare(values, outputs)
    del outputs["application_identity"]
    with pytest.raises(ValueError, match="not ready"):
        prepare(values, outputs)


def test_cloud_run_fallback_wiring_uses_verified_distinct_origins_without_vertex_ids(monkeypatch):
    import runpy
    from pathlib import Path
    from backend.runtime.deployment import KINDS, endpoints
    prepare = runpy.run_path(str(Path(__file__).parents[1]/"deployment/managed/wire-release.py"))["prepare"]
    trust = "agents.global.proj-123.system.id.goog"
    origins = {name: f"https://openclass-agent-{name}-example.run.app" for name in KINDS}
    identities = {name: f"//{trust}/resources/run/projects/123/locations/us-central1/services/openclass-agent-{name}" for name in KINDS}
    values = {"agent_hosting": "cloud_run", "runtime_environment": {}, "web_environment": {}, "mcp_environment": {"data": {}, "github": {}}}
    outputs = {name: {"value": value} for name, value in {
        "cloud_run_agent_urls": origins, "cloud_run_agent_identities": identities,
        "application_identity": f"//{trust}/resources/run/projects/123/locations/us-central1/services/openclass",
        "application_url": "https://openclass-example.run.app",
        "mcp_service_urls": {"data": "https://data-example.run.app", "github": "https://github-example.run.app"},
    }.items()}
    result = prepare(values, outputs)
    environment = result["runtime_environment"]
    assert environment["OPENCLASS_AGENT_RESOURCES"] == ""
    monkeypatch.setenv("OPENCLASS_AGENT_RESOURCES", environment["OPENCLASS_AGENT_RESOURCES"])
    monkeypatch.setenv("OPENCLASS_AGENT_URLS", environment["OPENCLASS_AGENT_URLS"])
    assert endpoints()["teacher"] == origins["teacher"]+"/invoke"
    assert result["web_environment"]["OPENCLASS_DEPLOYMENT_BOOTSTRAP"] == "true"
    origins["web"] = "https://rogue.example.com"
    with pytest.raises(ValueError, match="Cloud Run origin"):
        prepare(values, outputs)


def test_resource_names_resolve_to_authenticated_platform_endpoints(monkeypatch):
    from backend.runtime.deployment import endpoints, KINDS
    resources = {name: "projects/123/locations/us-central1/reasoningEngines/"+str(index) for index, name in enumerate(sorted(KINDS))}
    monkeypatch.setenv("OPENCLASS_AGENT_RESOURCES", json.dumps(resources))
    values = endpoints()
    assert values["tutor"].startswith("https://us-central1-aiplatform.mtls.googleapis.com/reasoningEngines/v1/projects/123/")
    assert values["tutor"].endswith("/api/invoke")
    resources["tutor"] = "https://rogue.example.com"
    monkeypatch.setenv("OPENCLASS_AGENT_RESOURCES", json.dumps(resources))
    with pytest.raises(ValueError):
        endpoints()


def test_remote_tool_preserves_model_schema_and_never_runs_local_mutation(monkeypatch):
    from backend.runtime import tool_proxy
    calls = []
    async def request_action(name, arguments):
        calls.append((name, arguments))
        return {"type": "private_practice", "study_id": "saved-study"}
    monkeypatch.setattr(tool_proxy, "request_action", request_action)
    async def create_test(concept_ids: list[str], question_count: int = 5) -> dict:
        raise AssertionError("Database mutation must execute in the API")
    runtime = {"actions": []}
    wrapped = tool_proxy.remote_tool(create_test, runtime)
    assert inspect.signature(wrapped) == inspect.signature(create_test)
    result = asyncio.run(wrapped(["trees"]))
    assert result["study_id"] == "saved-study"
    asyncio.run(wrapped(["trees"]))
    assert calls == [("create_test", {"concept_ids": ["trees"], "question_count": 5})]


def test_unknown_or_shared_runtime_endpoints_are_rejected(monkeypatch):
    from backend.runtime.deployment import endpoints, KINDS
    monkeypatch.delenv("OPENCLASS_AGENT_RESOURCES", raising=False)
    monkeypatch.setenv("OPENCLASS_AGENT_URLS", json.dumps({name: "https://same.example.com/invoke" for name in KINDS}))
    with pytest.raises(RuntimeError):
        endpoints()


def test_application_invokes_fixed_remote_coach_and_validates_result(monkeypatch):
    from backend.runtime import client
    from backend.runtime.deployment import KINDS
    monkeypatch.delenv("OPENCLASS_AGENT_RESOURCES", raising=False)
    monkeypatch.setenv("OPENCLASS_AGENT_URLS", json.dumps({name: "https://"+name+".example.com/invoke" for name in KINDS}))
    requests = []
    monkeypatch.setattr(client, "issue", lambda kind, context, user: "test-grant")
    def post(url, body):
        requests.append((url, body))
        return {"message": "Your learning progress", "actions": [], "sources": [], "session_id": "opaque-session"}
    monkeypatch.setattr(client, "post", post)
    result = asyncio.run(client.invoke_remote("tutor", {"question": "My progress?", "_tool_runtime": {"actor": {"id": "s1", "password": "never-send-this"}}}, "s1"))
    assert result["session_id"] == "opaque-session"
    assert requests[0][0] == "https://tutor.example.com/invoke"
    assert "password" not in requests[0][1]["context"]["_tool_runtime"]["actor"]
    monkeypatch.setattr(client, "post", lambda *args: {"message": ""})
    with pytest.raises(ValueError):
        asyncio.run(client.invoke_remote("tutor", {"question": "My progress?"}, "s1"))
