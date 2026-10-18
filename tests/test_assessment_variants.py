import asyncio
from contextlib import contextmanager
import pytest
from backend.assessment_variants import variant_spec, reject_repeated_questions, DuplicateVariantError


def test_variants_have_distinct_briefs_and_reject_repeated_question_text():
    variants = [variant_spec(i, 10, "b") for i in range(10)]
    assert len({v["scenario"] for v in variants}) == 10
    assert [v["index"] for v in variants] == list(range(1, 11))
    with pytest.raises(DuplicateVariantError):
        reject_repeated_questions([{"prompt": "  WHAT does return do?!"}], [{"questions": [{"prompt": "What does return do?"}]}])
    reject_repeated_questions([{"prompt": "Predict the returned value in the code sample."}], [{"questions": [{"prompt": "What does return do?"}]}])


@pytest.mark.parametrize("kind", ["practice", "formal"])
def test_standard_batches_preserve_shared_concepts_and_have_one_task_per_student(monkeypatch, kind):
    from backend.agents.coordinator import service
    from backend import store, services, notifications, learning
    class Conn:
        def execute(self, *args):
            pass
        @contextmanager
        def pipeline(self):
            yield
    @contextmanager
    def db():
        yield Conn()
    course = {"id": "c", "teacher_id": "t", "org": "o", "students": ["s1", "s2"], "materials": [{"id": "m"}], "concepts": [{"id": "functions"}, {"id": "testing"}]}
    saved = []
    monkeypatch.setattr(service, "db", db)
    monkeypatch.setattr(services, "course_access", lambda *args: course)
    monkeypatch.setattr(store, "get", lambda *args: None)
    monkeypatch.setattr(service, "put", lambda conn, entity, item: saved.append((entity, item)) or item)
    monkeypatch.setattr(service, "audit", lambda *args: None)
    monkeypatch.setattr(notifications, "notify", lambda *args: None)
    def forbidden(*args):
        raise AssertionError("Standard variants must not pick concepts from individual Twins")
    monkeypatch.setattr(learning, "classroom_twins", forbidden)
    blueprint = {"title": "Standard functions test", "kind": kind, "concept_ids": ["functions"], "question_count": 5, "total_marks": 10, "difficulty": "intermediate"}
    result = service.prepare_batch("c", {"id": "t", "org": "o", "role": "teacher"}, ["s1", "s2"], blueprint)
    assert result["mode"] == "standard_variants"
    assert len(result["jobs"]) == 2
    assert len({j["variant"]["scenario"] for j in result["jobs"]}) == 2
    for job in result["jobs"]:
        assert job["blueprint"]["concept_ids"] == ["functions"]
        assert job["blueprint"]["difficulty"] == "intermediate"
        assert job["blueprint"]["question_count"] == 5
        if kind == "formal":
            assert job["blueprint"]["student_id"] is None
        else:
            assert job["blueprint"]["student_id"] == job["student_id"]


def test_advisor_whole_class_tool_resolves_the_roster_and_uses_shared_concepts(monkeypatch):
    from backend.agents.classroom_advisor.tools import build_tools
    from backend.agents.coordinator import service
    from backend import services, store
    from backend.cloud import model_armor
    @contextmanager
    def db():
        yield None
    monkeypatch.setattr(store, "db", db)
    monkeypatch.setattr(services, "course_access", lambda *args: {"students": ["s1", "s2"]})
    async def inspect(*args):
        pass
    monkeypatch.setattr(model_armor, "inspect", inspect)
    calls = []
    async def queue(course, actor, students, template, **kwargs):
        calls.append((students, template))
        return {"id": "b", "jobs": [{}, {}]}
    monkeypatch.setattr(service, "queue_batch_assessments", queue)
    runtime = {"actor": {"id": "t", "role": "teacher"}, "course_id": "c", "latest_message": "Generate a standard test on functions for everyone", "allow_test_generation": True, "actions": []}
    tool = next(t for t in build_tools(runtime) if t.__name__ == "request_class_test_variants")
    action = asyncio.run(tool("Test functions at the same difficulty", ["functions"]))
    assert action["student_count"] == 2
    assert calls[0][0] == ["s1", "s2"]
    assert calls[0][1]["concept_ids"] == ["functions"]
    runtime["latest_message"] = "Generate a test for two students"
    assert asyncio.run(tool("Test functions", ["functions"]))["status"] == "not_authorized"
