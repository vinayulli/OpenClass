import asyncio
from collections import deque
from contextlib import contextmanager
import pytest


@pytest.fixture
def a2a_config(monkeypatch):
    from backend.a2a.config import shared_secret
    shared_secret.cache_clear()
    monkeypatch.setenv("A2A_SHARED_SECRET", "test-service-secret-"+"x"*40)
    monkeypatch.setenv("A2A_ASSESSMENT_URL", "https://agents.example/assessment")
    monkeypatch.setenv("A2A_CALLBACK_URL", "https://app.example/api/a2a/webhook")
    yield
    shared_secret.cache_clear()


def test_sdk_card_nonblocking_message_and_callback_contract(a2a_config):
    from backend.a2a.protocol import card, send_request, task_document
    from backend.a2a.routes import validate_push
    request = send_request("job-1")
    assert request.params.configuration.blocking is False
    assert card().capabilities.push_notifications is True
    push = request.params.configuration.push_notification_config.model_dump(by_alias=True)
    assert validate_push(push, "job-1")["token"] == "job-1"
    with pytest.raises(ValueError):
        validate_push(push, "different-job")
    push["url"] = "http://169.254.169.254/"
    with pytest.raises(ValueError):
        validate_push(push, "job-1")
    task = task_document({"id": "job-1", "course_id": "c"}, "completed", "exam-1")
    assert task["artifacts"][0]["parts"][0]["data"]["review_required"] is True


def test_jsonrpc_requires_service_auth_and_returns_task_without_waiting(monkeypatch, a2a_config):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.a2a import routes
    from backend.a2a.protocol import send_request, task_document
    from backend.a2a.config import shared_secret
    accepted = []
    def accept(job_id, push):
        accepted.append(job_id)
        return task_document({"id": job_id, "course_id": "c"}, "submitted")
    monkeypatch.setattr(routes, "accept_task", accept)
    app = FastAPI();app.include_router(routes.router)
    with TestClient(app) as client:
        payload = send_request("job-1").model_dump(mode="json", by_alias=True, exclude_none=True)
        assert client.post('/a2a/assessment', json=payload).status_code == 401
        response = client.post('/a2a/assessment', json=payload, headers={"Authorization": "Bearer "+shared_secret()})
        assert response.status_code == 200
        assert response.json()["result"]["status"]["state"] == "submitted"
        assert accepted == ["job-1"]
        task = task_document({"id": "job-1", "course_id": "c"}, "completed", "e")
        assert client.post('/api/a2a/webhook', json=task, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_callback_replay_does_not_duplicate_completion_or_notification(monkeypatch):
    from backend.a2a import state
    from backend.a2a.protocol import task_document
    from backend import notifications
    task = task_document({"id": "j", "course_id": "c"}, "completed", "e")
    records = {("a2a_task", "a2a:j"): {"state": "completed", "task": task}, ("job", "j"): {"id": "j", "status": "awaiting_callback", "user_id": "t", "course_id": "c"}, ("course", "c"): {"id": "c"}}
    class Connection:
        def execute(self, *args):
            pass
    @contextmanager
    def db():
        yield Connection()
    monkeypatch.setattr(state, "db", db)
    monkeypatch.setattr(state, "get", lambda conn, kind, key: records.get((kind, key)))
    monkeypatch.setattr(state, "put", lambda conn, kind, item: records.update({(kind, item["id"]): item}))
    emitted = []
    monkeypatch.setattr(notifications, "notify", lambda *args: emitted.append(args))
    assert state.receive_callback(task)["duplicate"] is False
    assert state.receive_callback(task)["duplicate"] is True
    assert len(emitted) == 1
    assert records[("job", "j")]["exam_id"] == "e"
    changed = {**task, "metadata": {"job_id": "other"}}
    with pytest.raises(ValueError):
        state.receive_callback(changed)


def test_ten_tasks_use_distinct_learner_sessions_and_bounded_workers(monkeypatch):
    from backend.a2a import workers
    from backend import agents
    pending = deque({"job_id": str(i), "attempts": 1} for i in range(10))
    def claim():
        try:return pending.popleft()
        except IndexError:return None
    monkeypatch.setattr(workers, "claim_task", claim)
    monkeypatch.setattr(workers, "generation_context", lambda job_id: ({"id": job_id, "student_id": "student-"+job_id, "user_id": "teacher", "blueprint": {}}, {"id": "c", "org": "o"}, {}, "exam-"+job_id, None))
    monkeypatch.setattr(workers, "save_draft", lambda *args: True)
    finished = []
    monkeypatch.setattr(workers, "finish_task", lambda job_id, *args: finished.append(job_id))
    active = 0;peak = 0;identities = []
    async def invoke(kind, context, user_id):
        nonlocal active, peak
        identities.append(user_id);active += 1;peak = max(peak, active)
        await asyncio.sleep(.02)
        active -= 1
        return {"questions": []}
    monkeypatch.setattr(agents, "invoke", invoke)
    async def worker():
        while await workers.generate_once():
            pass
    async def run():
        await asyncio.gather(*(worker() for _ in range(3)))
    asyncio.run(run())
    assert len(finished) == 10 and len(set(identities)) == 10
    assert 1 < peak <= 3


def test_shortcuts_do_not_discard_custom_teacher_requirements():
    from backend.agents.classroom_advisor.dispatch import quick_blueprint
    runtime = {"actor": {"role": "teacher"}, "allow_test_generation": True}
    learner = {"student": {"id": "s"}, "twin": {"concepts": [{"id": "a", "mastery": 30, "evidence_count": 3}]}}
    assert quick_blueprint({"question": "Generate a practice test for the selected learner", "selected_learner": learner}, runtime)["student_id"] == "s"
    assert quick_blueprint({"question": "Generate 12 advanced coding questions for the selected learner", "selected_learner": learner}, runtime) is None


def test_progress_summary_is_evidence_based_and_keeps_unknowns():
    from backend.agents.learning_coach.dispatch import progress_summary
    context = {"question": "Summarize my progress", "twin": {"mastery": None, "evidence_count": 0, "concepts": [{"id": "a", "name": "Functions", "mastery": None, "evidence_count": 0, "status": "insufficient evidence"}]}}
    text = progress_summary(context)
    assert "not assessed" in text and "unknown" in text and "0%" not in text


def test_dynamic_progress_branch_does_not_call_reasoning_node(monkeypatch):
    from google.adk.workflow import FunctionNode
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from backend.agents.workflow import build_workflow
    from backend import store, services
    from backend.cloud import model_armor
    @contextmanager
    def db():
        yield object()
    monkeypatch.setattr(store, "db", db)
    monkeypatch.setattr(store, "all_of", lambda *args: [])
    monkeypatch.setattr(services, "course_access", lambda *args: {})
    async def inspect(*args, **kwargs):
        pass
    monkeypatch.setattr(model_armor, "inspect", inspect)
    monkeypatch.setattr(model_armor, "inspect_context", inspect)
    def forbidden(node_input):
        raise AssertionError("Progress arithmetic must not call the model")
    context = {"question": "Summarize my progress", "twin": {"mastery": None, "evidence_count": 0, "concepts": []}}
    runtime = {"actor": {"id": "s", "role": "student"}, "course_id": "c", "actions": [], "sources": []}
    sink = {}
    agent = build_workflow("tutor", FunctionNode(name="forbidden_model", func=forbidden), context, runtime, sink)
    async def run():
        runner = InMemoryRunner(agent=agent, app_name="progress_test")
        session = await runner.session_service.create_session(app_name="progress_test", user_id="s")
        try:
            async for _ in runner.run_async(user_id="s", session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text=context["question"])])):
                pass
        finally:
            await runner.close()
    asyncio.run(run())
    assert sink["branch"] == "evidence_summary"
    assert "unknown" in sink["result"]["message"]
