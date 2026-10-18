import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
import pytest


def test_classroom_reads_evidence_once_and_preserves_unknowns(monkeypatch):
    from backend import learning
    reads = []
    evidence = [{"course_id": "c", "student_id": "s1", "concept_id": "x", "score": 1, "confidence": 1}]
    def read(conn, kind):
        reads.append(kind)
        return evidence
    monkeypatch.setattr(learning, "all_of", read)
    twins = learning.classroom_twins(None, {"id": "c", "concepts": [{"id": "x"}]}, [f"s{i}" for i in range(1, 31)])
    assert reads == ["evidence"]
    assert twins[0]["mastery"] == 100
    assert all(t["mastery"] is None for t in twins[1:])


def test_learner_resolution_is_unique_and_scoped_to_roster():
    from backend.chat_context import resolve_learner
    roster = [{"id": "s1", "name": "Jamie Chen"}, {"id": "s2", "name": "Aarav Patel"}]
    assert resolve_learner("check jamie chen", roster) == "s1"
    assert resolve_learner("Jamie Chen and Aarav Patel", roster) is None
    assert resolve_learner("Jamie Chenoweth", roster) is None
    assert resolve_learner("Outsider Name", roster) is None


def test_student_context_excludes_other_learners_and_pauses_active_attempt(monkeypatch):
    from backend import chat_context
    from fastapi import HTTPException
    @contextmanager
    def fake_db():
        yield None
    monkeypatch.setattr(chat_context, "db", fake_db)
    course = {"id": "c", "students": ["s1", "s2"], "name": "Python", "objectives": [], "concepts": [], "materials": []}
    monkeypatch.setattr(chat_context, "course_access", lambda *args: course)
    records = {"attempt": [], "chat": [{"course_id": "c", "user_id": "s2", "question": "private", "response": "private"}]}
    monkeypatch.setattr(chat_context, "all_of", lambda conn, kind: records.get(kind, []))
    monkeypatch.setattr(chat_context, "many_of", lambda conn, kinds: {kind: records.get(kind, []) for kind in kinds})
    selected = []
    def twins(conn, course, ids, **kwargs):
        selected.extend(ids)
        return [{"student_id": s} for s in ids]
    monkeypatch.setattr(chat_context, "classroom_twins", twins)
    actor = {"id": "s1", "role": "student"}
    body = SimpleNamespace(student_id=None, message="my progress")
    context = chat_context.build_context("c", body, actor)
    assert selected == ["s1", "s2"]
    assert "s2" not in str(context["class_performance"])
    assert context["conversation"] == []
    assert "learner_roster" not in context
    records["attempt"] = [{"student_id": "s1", "status": "in_progress"}]
    with pytest.raises(HTTPException) as error:
        chat_context.build_context("c", body, actor)
    assert error.value.status_code == 409


def test_unavailable_memory_returns_explicit_fallback(monkeypatch):
    from backend.cloud import memory
    monkeypatch.setenv("GEAP_MEMORY_ENABLED", "true")
    async def unavailable(*args):
        raise TimeoutError()
    monkeypatch.setattr(memory, "retrieve", unavailable)
    result = asyncio.run(memory.retrieve_for_chat("org", "course", "student", "question"))
    assert result["status"] == "unavailable"
    assert result["memories"] == []


def test_memory_filter_rejection_never_becomes_availability_fallback(monkeypatch):
    from backend.cloud import memory, model_armor
    monkeypatch.setenv("GEAP_MEMORY_ENABLED", "true")
    async def retrieve(*args):
        return ["untrusted fact"]
    async def blocked(*args):
        raise model_armor.ContentBlocked("blocked")
    monkeypatch.setattr(memory, "retrieve", retrieve)
    monkeypatch.setattr(model_armor, "inspect", blocked)
    with pytest.raises(model_armor.ContentBlocked):
        asyncio.run(memory.retrieve_for_chat("org", "course", "student", "question"))
