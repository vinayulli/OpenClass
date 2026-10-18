import asyncio
from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from backend import assignments
from backend.routes import experience
from backend.schemas import CodeSubmission


class Connection:
    def execute(self, *args):
        return self


@contextmanager
def fake_db():
    yield Connection()


def test_submit_persists_before_any_github_or_model_call_and_deduplicates(monkeypatch):
    saved = []
    monkeypatch.setattr(experience, "db", fake_db)
    monkeypatch.setattr(experience, "rate_limit", lambda *args: None)
    monkeypatch.setattr(assignments, "accessible_assignment", lambda *args: ({"id": "c"}, {"id": "a"}))
    monkeypatch.setattr(experience, "all_of", lambda *args: saved)
    monkeypatch.setattr(experience, "put", lambda conn, kind, item: saved.append(item) or item)
    monkeypatch.setattr(experience, "audit", lambda *args: None)
    actor = {"id": "s", "role": "student", "org": "o"}
    body = CodeSubmission(assignment_id="a", url="https://github.com/example/repo")
    item = experience.submit_code("c", body, actor)
    assert item["status"] == "queued" and item["attempt_number"] == 1
    assert item["student_id"] == "s" and item["org"] == "o"
    assert assignments.SubmissionRecord.model_validate(item).id == item["id"]
    assert experience.submit_code("c", body, actor)["id"] == item["id"]
    assert len(saved) == 1
    with pytest.raises(HTTPException) as error:
        experience.submit_code("c", CodeSubmission(assignment_id="a", url="https://github.com/example/different"), actor)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        experience.submit_code("c", body, {**actor, "role": "teacher"})
    assert error.value.status_code == 403


def test_assignment_access_rejects_other_students_and_courses(monkeypatch):
    monkeypatch.setattr(assignments, "course_access", lambda *args: {"id": "c"})
    monkeypatch.setattr(assignments, "get", lambda *args: {"course_id": "c", "student_ids": ["s1"]})
    with pytest.raises(HTTPException):
        assignments.accessible_assignment(None, "c", "a", {"id": "s2"})
    with pytest.raises(HTTPException):
        assignments.accessible_assignment(None, "other", "a", {"id": "s1"})


def test_review_worker_saves_success_and_safe_failure(monkeypatch):
    from backend import repositories
    outcomes = []
    monkeypatch.setattr(assignments, "context", lambda item: ({"id": "s"}, {"id": "c", "concepts": []}, {"id": "a"}))
    monkeypatch.setattr(assignments, "finish", lambda *args, **kwargs: outcomes.append((args, kwargs)))
    async def repo(url):
        return {"files": [{"content": "print(1)"}], "scope": "static"}
    async def model(*args):
        return {"summary": "A report"}
    monkeypatch.setattr(repositories, "read_repository", repo)
    monkeypatch.setattr(assignments, "ai_call", model)
    item = {"id": "sub", "url": "https://github.com/example/repo"}
    asyncio.run(assignments.process(item))
    assert outcomes[-1][0][2] == {"summary": "A report"}
    async def failed(url):
        raise RuntimeError("secret infrastructure details")
    monkeypatch.setattr(repositories, "read_repository", failed)
    asyncio.run(assignments.process(item))
    assert "Repository review failed" in outcomes[-1][1]["error"]
    assert "secret" not in outcomes[-1][1]["error"]


def test_completion_links_report_and_notifies_once(monkeypatch):
    from backend import notifications
    item = {"id": "sub", "status": "processing", "lease_until": "lease", "student_id": "s", "assignment_id": "a", "course_id": "c", "url": "https://github.com/example/repo"}
    records = {"sub": dict(item)}
    events = []
    monkeypatch.setattr(assignments, "db", fake_db)
    monkeypatch.setattr(assignments, "get", lambda conn, kind, id: dict(records[id]))
    monkeypatch.setattr(assignments, "put", lambda conn, kind, data: records.update({data["id"]: data}))
    monkeypatch.setattr(notifications, "notify", lambda *args: events.append(args))
    assignments.finish(item, {"teacher_id": "t"}, {"summary": "OK"}, {"scope": "static"})
    assert records["sub"]["review_id"] == "review:sub"
    assert records["review:sub"]["submission_id"] == "sub"
    assert records["sub"]["status"] == "teacher_review_required"
    assignments.finish(item, {"teacher_id": "t"}, {"summary": "OK"}, {"scope": "static"})
    assert len(events) == 1
