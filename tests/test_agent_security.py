import asyncio
import json
import time
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


@pytest.fixture
def signing_keys(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setenv("MCP_SCOPE_PRIVATE_KEY", private)
    monkeypatch.setenv("MCP_SCOPE_PUBLIC_KEY", public)
    return private, public


def test_default_deny_agent_and_tool_graph():
    from backend.security.policy import allow_call, allow_tool
    allow_call("tutor", "web")
    allow_tool("code", "github", "inspect_public_repository")
    for caller, target in [("rogue", "exam"), ("web", "teacher"), ("code", "exam"), ("teacher", "web")]:
        with pytest.raises(PermissionError):
            allow_call(caller, target)
    for agent, service, tool in [("web", "data", "get_student_progress"), ("tutor", "github", "inspect_public_repository"), ("code", "data", "get_course_materials")]:
        with pytest.raises(PermissionError):
            allow_tool(agent, service, tool)


def test_scope_is_audience_bound_and_uses_public_key_in_managed_mode(monkeypatch, signing_keys):
    from backend.cloud.capabilities import issue, verify
    monkeypatch.setenv("OPENCLASS_GOVERNANCE_MODE", "managed")
    token = issue({"id": "s1", "org": "o1"}, "c1", "s1", agent="code", service="github", resources={"repository_url": "https://github.com/a/b"})
    monkeypatch.delenv("MCP_SCOPE_PRIVATE_KEY")
    assert verify(token, "github")["resources"]["repository_url"] == "https://github.com/a/b"
    with pytest.raises(jwt.InvalidAudienceError):
        verify(token, "data")


def test_runtime_grant_rejects_changed_payload_identity_and_undeclared_delegate(signing_keys):
    from backend.runtime.tickets import issue, verify
    context = {"question": "Explain trees", "_course_id": "c1"}
    ticket = issue("tutor", context, "s1")
    verify(ticket, "tutor", context, "s1", "api")
    verify(ticket, "web", {"question": "Decision tree tutorial"}, "s1", "tutor")
    for kind, payload, user, caller in [("tutor", {"question": "Changed"}, "s1", "api"), ("tutor", context, "s2", "api"), ("exam", context, "s1", "tutor"), ("web", {"question": "Trees", "academic_record": {}}, "s1", "tutor"), ("tutor", context, "s1", "rogue")]:
        with pytest.raises(PermissionError):
            verify(ticket, kind, payload, user, caller)


def test_identity_verifies_signature_and_exact_spiffe_subject(monkeypatch, signing_keys):
    from backend.security import identity
    private, public = signing_keys
    issuer = "https://sts.googleapis.com/v1/projects/123/locations/global/workloadIdentityPools/agents.global.proj-123.system.id.goog"
    monkeypatch.setenv("OPENCLASS_IDENTITY_ISSUER", issuer)
    monkeypatch.setenv("OPENCLASS_IDENTITY_AUDIENCE", "https://openclass.internal/workloads")
    subject = "spiffe://agents.global.proj-123.system.id.goog/resources/aiplatform/projects/123/locations/us-central1/reasoningEngines/456"
    monkeypatch.setenv("OPENCLASS_WORKLOAD_PRINCIPALS", json.dumps({"tutor": subject}))
    monkeypatch.setattr(identity, "key_client", lambda _: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=public)))
    claims = {"iss": issuer, "aud": "https://openclass.internal/workloads", "sub": subject, "iat": int(time.time()), "exp": int(time.time())+60}
    token = jwt.encode(claims, private, algorithm="RS256")
    assert identity.caller_from_headers({"x-openclass-workload-token": token}) == "tutor"
    with pytest.raises(Exception):
        identity.caller_from_headers({"x-agent-name": "tutor"})
    claims["sub"] = "spiffe://rogue"
    with pytest.raises(PermissionError):
        identity.caller_from_headers({"x-openclass-workload-token": jwt.encode(claims, private, algorithm="RS256")})


def test_github_decodes_embedded_resource_instead_of_losing_file_body():
    from backend.cloud.mcp_client import decode_result
    from mcp.types import CallToolResult, EmbeddedResource, TextResourceContents, TextContent
    result = CallToolResult(content=[TextContent(type="text", text="successfully downloaded text file"), EmbeddedResource(type="resource", resource=TextResourceContents(uri="repo://a/b/contents/main.py", text="print('hello')"))])
    assert decode_result(result)["content"] == "print('hello')"
    result.isError = True
    with pytest.raises(RuntimeError):
        decode_result(result)


def test_official_github_reader_pins_commit_and_rejects_private_repository(monkeypatch):
    from mcp_servers.github import upstream
    monkeypatch.setenv("GITHUB_UPSTREAM_MCP_URL", "https://api.githubcopilot.com/mcp/")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "unit-test-not-a-token")
    monkeypatch.setenv("OPENCLASS_GOVERNANCE_MODE", "local")
    calls = []
    async def call(url, tool, arguments, headers):
        calls.append((tool, arguments))
        if tool == "search_repositories":
            return {"items": [{"full_name": "a/b", "private": False}]}
        if tool == "list_commits":
            return [{"sha": "a"*40}]
        assert arguments["sha"] == "a"*40
        if not arguments["path"]:
            return [{"path": "main.py", "type": "file", "size": 10}, {"path": "huge.py", "type": "file", "size": 16000}]
        return {"encoding": "utf-8", "content": "print(1)"}
    monkeypatch.setattr(upstream, "call", call)
    result = asyncio.run(upstream.inspect_repository("https://github.com/a/b"))
    assert result["files"][0]["content"] == "1: print(1)"
    assert len(calls) == 4
    async def private(*args):
        return {"items": [{"full_name": "a/b", "private": True}]}
    monkeypatch.setattr(upstream, "call", private)
    with pytest.raises(PermissionError):
        asyncio.run(upstream.inspect_repository("https://github.com/a/b"))


def test_github_scope_cannot_change_repository(monkeypatch):
    from backend.cloud.capabilities import request_scope
    from mcp_servers.github.server import inspect_public_repository
    monkeypatch.setenv("OPENCLASS_GOVERNANCE_MODE", "local")
    token = request_scope.set({"agent": "code", "permissions": ["inspect_public_repository"], "resources": {"repository_url": "https://github.com/a/b"}})
    try:
        with pytest.raises(PermissionError):
            asyncio.run(inspect_public_repository("https://github.com/a/other"))
    finally:
        request_scope.reset(token)


def test_generated_gateway_rules_have_exact_principals_and_tool_conditions():
    path = Path(__file__).parents[1]/"deployment/managed/render-policy.py"
    spec = importlib.util.spec_from_file_location("render_policy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = ["api", "teacher", "tutor", "exam", "code", "path", "intervention", "web"]
    inventory = {"principals": {name: "spiffe://agents.global.proj-123.system.id.goog/resources/aiplatform/projects/123/locations/us-central1/reasoningEngines/"+str(n) for n, name in enumerate(names)}, "registered_agents": {name: "projects/123/locations/us-central1/agents/"+name for name in names if name != "api"}, "registered_mcp_servers": {name: "projects/123/locations/us-central1/mcpServers/"+name for name in ["data", "github"]}}
    rules = module.render(inventory)
    code = [rule for rule in rules if rule["description"] == "code to github tools"][0]
    assert "inspect_public_repository" in code["conditions"]["iap.googleapis.com"]["expression"]
    assert "== 'projects/123/locations/" in code["conditions"]["iap.googleapis.com"]["expression"]
    assert all("principalSet" not in json.dumps(rule) for rule in rules)
    inventory["google_api_context"] = {"project_number": "123", "region": "us-central1", "model": "gemini-3.8-flash", "armor_template": "projects/123/locations/us-central1/templates/openclass"}
    expanded = module.render(inventory)
    assert len(expanded) == len(rules)+31
    google_rules = expanded[len(rules):]
    assert all("destination.unregistered.host" in item["conditions"]["iap.googleapis.com"]["expression"] for item in google_rules)
    assert all(len(item["principals"]) == 7 for item in google_rules[-3:])
    assert all("https://" not in item["conditions"]["iap.googleapis.com"]["expression"] for item in google_rules)
    compiled = module.compile_policy(expanded)
    assert compiled == expanded
    assert all(len(item["conditions"]["iap.googleapis.com"]["expression"]) <= 1024 for item in compiled)
    assert all("has(" not in item["conditions"]["iap.googleapis.com"]["expression"] for item in compiled)
    web_principal = inventory["principals"]["web"].replace("spiffe://", "principal://")
    assert all("mcpServers/" not in item["conditions"]["iap.googleapis.com"]["expression"] for item in compiled if web_principal in item["principals"])
    inventory["coordinator_url"] = "https://openclass-example.run.app/api/internal/agent-actions"
    coordinator_rules = module.render(inventory)[-2:]
    assert {item["description"] for item in coordinator_rules} == {"teacher to exact coordinator HTTP route", "tutor to exact coordinator HTTP route"}
    assert {item["principals"][0] for item in coordinator_rules} == {inventory["principals"][name].replace("spiffe://", "principal://") for name in ["teacher", "tutor"]}
    for item in coordinator_rules:
        expression = item["conditions"]["iap.googleapis.com"]["expression"]
        assert "host == 'openclass-example.run.app'" in expression
        assert "method == 'POST'" in expression
        assert "path == '/api/internal/agent-actions'" in expression
    inventory["coordinator_url"] += "?token=invalid"
    with pytest.raises(ValueError, match="exact deployed coordinator"):
        module.render(inventory)
    inventory.pop("coordinator_url")
    inventory["principals"]["code"] = inventory["principals"]["tutor"]
    with pytest.raises(ValueError):
        module.render(inventory)


def test_separate_mcp_http_catalogues_reject_cross_service_tokens(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.cloud.capabilities import issue
    from mcp_servers.data.server import app as data
    from mcp_servers.github.server import app as github
    monkeypatch.setenv("OPENCLASS_GOVERNANCE_MODE", "local")
    monkeypatch.setenv("MCP_CONTEXT_SECRET", "local-test-only-secret-with-at-least-32-characters")
    actor = {"id": "s1", "org": "o1", "role": "student"}
    data_token = issue(actor, "c1", "s1", agent="tutor")
    github_token = issue(actor, "c1", "s1", agent="code", service="github", resources={"repository_url": "https://github.com/a/b"})
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    for app, valid, wrong, expected in [(data, data_token, github_token, {"get_course_materials", "get_learning_twin", "get_student_progress", "get_class_summary", "search_learner_memory"}), (github, github_token, data_token, {"inspect_public_repository"})]:
        with TestClient(app, base_url="http://127.0.0.1:8001") as client:
            assert client.post("/mcp", json=request, headers=headers).status_code == 403
            assert client.post("/mcp", json=request, headers={**headers, "X-OpenClass-Context": wrong}).status_code == 403
            response = client.post("/mcp", json=request, headers={**headers, "X-OpenClass-Context": valid})
            assert response.status_code == 200, response.text
            assert {tool["name"] for tool in response.json()["result"]["tools"]} == expected


def test_managed_mcp_rejects_valid_scope_from_wrong_workload(monkeypatch, signing_keys):
    from fastapi.testclient import TestClient
    from backend.cloud.capabilities import issue
    from mcp_servers.common import auth
    from mcp_servers.data.server import app
    monkeypatch.setenv("OPENCLASS_GOVERNANCE_MODE", "managed")
    token = issue({"id": "s1", "org": "o1"}, "c1", "s1", agent="tutor")
    monkeypatch.setattr(auth, "caller_from_headers", lambda headers: "web")
    # Rejection happens in the authorization wrapper before MCP lifecycle or IO.
    client = TestClient(app, base_url="http://127.0.0.1:8001")
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"X-OpenClass-Context": token})
    assert response.status_code == 403
