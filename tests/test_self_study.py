from contextlib import contextmanager
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.routes import self_study as study


def test_private_practice_requires_owner_and_hides_answers_until_submission(monkeypatch):
    item = {"id": "p", "type": "practice", "student_id": "s", "org": "o", "course_id": "c", "status": "completed", "output": {"questions": [{"id": "q", "prompt": "Pick one", "options": ["a", "b"], "marks": 2, "concept_id": "x", "answer": "a", "explanation": "Because a", "rubric": "secret"}]}}
    assert "answer" not in study.public(item)["output"]["questions"][0]
    with pytest.raises(HTTPException) as error:
        study.owned(item, {"id": "s", "org": "o", "role": "teacher"})
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        study.owned(item, {"id": "other", "org": "o", "role": "student"})
    class Conn:
        def execute(self, *args):
            return self
    @contextmanager
    def database():
        yield Conn()
    saved = []
    monkeypatch.setattr(study, "db", database)
    monkeypatch.setattr(study, "get", lambda *args: item)
    monkeypatch.setattr(study, "access", lambda *args: {})
    monkeypatch.setattr(study, "put", lambda conn, kind, data: saved.append(kind))
    result = study.submit_practice("p", study.PracticeAnswers(answers={"q": "a"}), {"id": "s", "org": "o", "role": "student"})
    assert result["result"]["score"] == 2
    assert result["result"]["official_grade"] is False
    assert result["output"]["questions"][0]["answer"] == "a"
    assert saved == ["self_study"]


def test_teacher_cannot_access_private_self_study_api():
    app = FastAPI()
    app.include_router(study.router)
    app.dependency_overrides[study.user] = lambda: {"id": "t", "org": "o", "role": "teacher"}
    client = TestClient(app)
    assert client.get("/api/courses/c/self-study").status_code == 403
    assert client.post("/api/courses/c/self-study/practice", json={"concept_ids": ["x"]}).status_code == 403
    assert client.post("/api/self-study/p/submit", json={"answers": {}}).status_code == 403


def test_learning_path_rejects_unknown_concepts():
    from backend.agents.workflow import prepare, validate_result
    from backend.agents.learning_path.agent import SCHEMA
    course = {"concepts": [{"id": "x"}]}
    with pytest.raises(ValueError):
        prepare("path", {"course": course, "concept_ids": ["other"]})
    result = {"title": "Path", "rationale": "Practice", "steps": [{"concept_id": "other", "title": "Try", "explanation": "Read", "practice": "Try", "completion_check": "Explain", "estimated_minutes": 10}]}
    with pytest.raises(ValueError):
        validate_result("path", result, {"course": course}, SCHEMA)
