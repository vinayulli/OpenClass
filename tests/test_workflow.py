"""Integration tests require an isolated PostgreSQL database; never use production."""
import os
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL to an isolated PostgreSQL database")


@pytest.fixture
def clients(monkeypatch):
    from urllib.parse import urlparse
    if not urlparse(os.environ["TEST_DATABASE_URL"]).path.endswith("_test"):
        pytest.fail("Integration tests require a disposable database with a name ending in _test")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("OPENCLASS_DEMO", "true")
    monkeypatch.setenv("GEAP_MEMORY_ENABLED", "false")
    monkeypatch.setenv("MODEL_ARMOR_ENABLED", "false")
    monkeypatch.setenv("OPENCLASS_REQUIRE_GOVERNANCE", "false")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("ADK_SESSION_DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    from backend.store import db
    with db() as conn:
        conn.execute("DROP TABLE IF EXISTS records, sessions, schema_version CASCADE")
    from backend.main import app, limits
    from fastapi.testclient import TestClient
    limits.clear()
    with TestClient(app) as teacher, TestClient(app) as student:
        assert teacher.post('/api/auth/login', json={"email": "teacher@openclass.demo", "password": "OpenClass123!"}).status_code == 200
        assert student.post('/api/auth/login', json={"email": "student@openclass.demo", "password": "OpenClass123!"}).status_code == 200
        yield teacher, student


def test_publish_attempt_grade_twin_and_idempotency(clients):
    teacher, student = clients
    exam = teacher.post('/api/courses/python-foundations/exams/sample').json()
    assert student.post(f'/api/exams/{exam["id"]}/attempt').status_code == 404
    assert teacher.post(f'/api/exams/{exam["id"]}/publish').status_code == 200
    assert teacher.put(f'/api/exams/{exam["id"]}/questions', json=exam['questions']).status_code == 409
    result = student.post(f'/api/exams/{exam["id"]}/attempt').json()
    assert all('answer' not in q and 'explanation' not in q for q in result['exam']['questions'])
    attempt_id = result['attempt']['id']
    assert student.put(f'/api/attempts/{attempt_id}/answers', json={"answers": {q['id']: q['answer'] for q in exam['questions']}}).status_code == 200
    first = student.post(f'/api/attempts/{attempt_id}/submit').json()
    second = student.post(f'/api/attempts/{attempt_id}/submit').json()
    assert first == second
    assert first['score'] == 4
    assert student.put(f'/api/attempts/{attempt_id}/answers', json={"answers": {}}).status_code == 409
    from backend.store import db, all_of
    with db() as conn:
        evidence = [e for e in all_of(conn, 'evidence') if e['source_id'] == attempt_id]
    assert len(evidence) == 2
    assert teacher.post(f'/api/attempts/{attempt_id}/review', json={"scores": {"q1": 0}, "reason": "Reviewed against rubric"}).status_code == 200


def test_authorization_is_enforced(clients):
    teacher, student = clients
    assert student.post('/api/courses', json={"name": "Test", "objectives": ["Learn"], "concepts": [{"id": "x", "name": "X"}]}).status_code == 403
    assert student.get('/api/courses/python-foundations/audit').status_code == 403
    own = student.get('/api/courses/python-foundations/overview').json()
    assert len(own['students']) == 1
    assert own['students'][0]['id'] == 'student-1'
    course = teacher.post('/api/courses', json={"name": "Private", "objectives": ["Learn"], "concepts": [{"id": "x", "name": "X"}]}).json()
    assert student.get(f'/api/courses/{course["id"]}/overview').status_code == 404


def test_data_mcp_enforces_student_scope_with_real_postgres(clients, monkeypatch):
    import asyncio
    from backend.cloud.capabilities import request_scope, issue, verify
    from mcp_servers.data.tools import get_student_progress
    from backend.store import db, get
    monkeypatch.setenv("OPENCLASS_GOVERNANCE_MODE", "local")
    monkeypatch.setenv("MCP_CONTEXT_SECRET", "database-scope-test-secret-at-least-32-characters")
    with db() as conn:
        student = get(conn, "user", "student-1")
    token = request_scope.set(verify(issue(student, "python-foundations", "student-1", agent="tutor")))
    try:
        result = asyncio.run(get_student_progress())
        assert result["twin"]["student_id"] == "student-1"
        with pytest.raises(PermissionError):
            asyncio.run(get_student_progress("student-2"))
    finally:
        request_scope.reset(token)


def test_selected_test_recipient_cannot_be_bypassed(clients):
    teacher, student = clients
    exam = teacher.post('/api/courses/python-foundations/exams/sample').json()
    assert teacher.post(f'/api/exams/{exam["id"]}/assign', json={"student_ids": ["student-2"]}).status_code == 200
    assert teacher.post(f'/api/exams/{exam["id"]}/publish').status_code == 200
    assert student.post(f'/api/exams/{exam["id"]}/attempt').status_code == 404
    assert all(e["id"] != exam["id"] for e in student.get('/api/courses/python-foundations/overview').json()["exams"])


def test_student_cannot_simulate_or_create_assignments(clients):
    _, student = clients
    assert student.post('/api/courses/python-foundations/students/student-2/simulate', json={"concept_id": "functions"}).status_code == 403
    assert student.post('/api/courses/python-foundations/coding-assignments', json={"title": "Example", "instructions": "Implement a function", "concept_ids": ["functions"]}).status_code == 403


def test_deployed_coach_coordinator_checks_grant_and_deduplicates_action(clients, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from backend.routes import agent_coordinator, self_study
    from backend.runtime.tickets import issue
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("MCP_SCOPE_PRIVATE_KEY", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    monkeypatch.setenv("MCP_SCOPE_PUBLIC_KEY", key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    monkeypatch.setattr(agent_coordinator, "caller_from_headers", lambda headers: "tutor")
    dispatched = []
    def generate(course, kind, request, actor):
        dispatched.append((course, kind, actor["id"]))
        return {"id": "private-test-job", "status": "queued"}
    monkeypatch.setattr(self_study, "generate_study", generate)
    context = {"question": "Create a quiz on functions", "_tool_runtime": {"actor": {"id": "student-1", "role": "student"}, "course_id": "python-foundations", "latest_message": "Create a quiz on functions", "actions": [], "sources": []}}
    body = {"context": context, "grant": issue("tutor", context, "student-1"), "name": "request_practice_test", "arguments": {"concept_ids": ["functions"], "question_count": 2}}
    _, student = clients
    first = student.post('/api/internal/agent-actions', json=body)
    second = student.post('/api/internal/agent-actions', json=body)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    assert first.json()["url"].endswith("/self-study?study=private-test-job")
    assert dispatched == [("python-foundations", "practice", "student-1")]
    body["context"]["_tool_runtime"]["course_id"] = "someone-elses-course"
    assert student.post('/api/internal/agent-actions', json=body).status_code == 403
    monkeypatch.setattr(agent_coordinator, "caller_from_headers", lambda headers: "web")
    assert student.post('/api/internal/agent-actions', json=body).status_code == 403
