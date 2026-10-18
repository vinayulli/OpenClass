import pytest
from fastapi import HTTPException
from backend import conversations
from backend.agents.sessions import session_key


def test_conversation_scope_and_session_identity(monkeypatch):
    item = {"user_id": "s1", "org": "o", "course_id": "c"}
    monkeypatch.setattr(conversations, "get", lambda *args: item)
    actor = {"id": "s1", "org": "o"}
    assert conversations.authorize(None, "thread", "c", actor) == item
    for changed in ({"id": "s2", "org": "o"}, {"id": "s1", "org": "other"}):
        with pytest.raises(HTTPException) as error:
            conversations.authorize(None, "thread", "c", changed)
        assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        conversations.authorize(None, "thread", "other-course", actor)
    assert session_key("o", "c", "s1", "tutor", "one") != session_key("o", "c", "s1", "tutor", "two")
    assert session_key("o", "c", "s1", "tutor") == session_key("o", "c", "s1", "tutor", None)


def test_academic_snapshot_never_exposes_keys_or_other_students():
    records = {kind: [] for kind in ("exam", "attempt", "coding_assignment", "code_review", "intervention")}
    records["exam"] = [{"id": "e", "course_id": "c", "title": "Test", "status": "published", "blueprint": {"release_feedback": False}, "questions": [{"answer": "SECRET"}]}]
    records["attempt"] = [{"id": "a", "exam_id": "e", "student_id": "s1", "status": "graded", "score": 99, "answers": {"q": "SECRET"}}]
    records["code_review"] = [{"id": "mine", "course_id": "c", "student_id": "s1", "report": {"summary": "My work"}}, {"id": "other", "course_id": "c", "student_id": "s2", "report": {"summary": "PRIVATE"}}]
    snapshot = conversations.academic_snapshot(records, {"id": "c"}, "s1")
    assert "SECRET" not in str(snapshot) and "PRIVATE" not in str(snapshot)
    assert "score" not in snapshot["assessment_history"][0]
    assert snapshot["counts"]["repository_submissions"] == 1
    records["exam"][0]["blueprint"]["release_feedback"] = True
    assert conversations.academic_snapshot(records, {"id": "c"}, "s1")["assessment_history"][0]["score"] == 99


def test_context_filters_conversation_history(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from backend import chat_context
    @contextmanager
    def database():
        yield None
    monkeypatch.setattr(chat_context, "db", database)
    monkeypatch.setattr(conversations, "authorize", lambda *args: {})
    monkeypatch.setattr(chat_context, "course_access", lambda *args: {"id": "c", "students": ["s"], "name": "Python", "objectives": [], "concepts": [], "materials": []})
    def records(conn, kinds):
        result = {k: [] for k in kinds}
        result["chat"] = [{"course_id": "c", "user_id": "s", "conversation_id": thread, "question": thread, "response": thread} for thread in ("one", "two", None)]
        return result
    monkeypatch.setattr(chat_context, "many_of", records)
    monkeypatch.setattr(chat_context, "classroom_twins", lambda *args, **kwargs: [{"student_id": "s", "mastery": 63}])
    body = SimpleNamespace(student_id=None, message="Help", conversation_id="one")
    context = chat_context.build_context("c", body, {"id": "s", "role": "student"})
    assert context["conversation"] == [{"question": "one", "response": "one"}]
    assert context["twin"]["mastery"] == 63 and "academic_record" in context
