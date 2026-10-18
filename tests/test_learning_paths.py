from contextlib import contextmanager
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from backend import learning_paths
from backend.class_context import summarize_class


def test_path_refresh_versions_and_pending_deduplication(monkeypatch):
    saved = []
    monkeypatch.setattr(learning_paths, "put", lambda conn, kind, item: saved.append(item) or item)
    course = {"id": "c", "org": "o"}
    previous = {"id": "old", "type": "path", "course_id": "c", "student_id": "s", "status": "completed", "version": 2, "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}
    pending = learning_paths.enqueue(None, course, "s", ["x"], "teacher", [previous])
    assert pending["version"] == 3 and pending["previous_path_id"] == "old"
    assert learning_paths.enqueue(None, course, "s", ["x"], "teacher", [previous, pending])["id"] == pending["id"]
    assert len(saved) == 1
    assert learning_paths.latest_ready([previous, pending]) == previous
    assert learning_paths.refresh_due(previous)


def test_feedback_is_scoped_and_bounded(monkeypatch):
    feedback = [{"course_id": "c", "student_id": "s", "org": "o", "comment": str(i)} for i in range(25)]
    feedback += [{"course_id": "c", "student_id": "other", "org": "o", "comment": "PRIVATE"}]
    monkeypatch.setattr(learning_paths, "all_of", lambda *args: feedback)
    result = learning_paths.feedback_context(None, {"course_id": "c", "student_id": "s", "org": "o"})
    assert len(result) == 20 and result[0]["comment"] == "5"
    assert "PRIVATE" not in str(result)


def test_anonymous_class_context_handles_ties_unknowns_and_small_cohorts():
    twins = [{"student_id": f"s{i}", "mastery": score, "coverage": 100} for i, score in enumerate([90, 80, 80, 70, 60])]
    twins.append({"student_id": "unassessed", "mastery": None, "coverage": 0})
    result = summarize_class(twins, "s2")
    assert result["your_rank"] == 2 and result["ties_at_your_score"] == 2
    assert result["enrolled_learners"] == 6 and result["comparable_learners"] == 5
    assert result["class_mean_mastery"] == 76
    assert "s1" not in str(result) and "student_id" not in result
    assert summarize_class(twins[:3], "s0")["your_rank"] is None
    assert summarize_class(twins, "unassessed")["your_rank"] is None


def test_coach_test_tool_delegates_and_returns_a_private_open_link(monkeypatch):
    from backend.agents.learning_coach.tools import build_tools
    from backend.routes import self_study
    requests = []
    def generate(course_id, kind, body, actor):
        requests.append((course_id, kind, body.concept_ids, actor["id"]))
        return {"id": "private-test", "status": "queued"}
    monkeypatch.setattr(self_study, "generate_study", generate)
    runtime = {"actor": {"id": "s", "role": "student", "org": "o"}, "course_id": "c", "latest_message": "Create a test on functions", "actions": [], "sources": []}
    tool = next(t for t in build_tools(runtime) if t.__name__ == "request_practice_test")
    result = asyncio.run(tool(["functions"], 5))
    assert result["url"] == "/courses/c/self-study?study=private-test"
    assert requests == [("c", "practice", ["functions"], "s")]
    asyncio.run(tool(["functions"], 5))
    assert len(requests) == 1 and len(runtime["actions"]) == 1
    runtime["latest_message"] = "Do not create a test"
    with pytest.raises(ValueError):
        asyncio.run(tool(["functions"], 5))


def test_teacher_path_view_never_includes_private_tests(monkeypatch):
    from backend.routes import learning_paths as routes
    @contextmanager
    def database():
        yield None
    monkeypatch.setattr(routes, "db", database)
    monkeypatch.setattr(routes, "course_access", lambda *args: {"students": ["s"]})
    private = {"type": "practice", "course_id": "c", "student_id": "s", "status": "completed", "result": {"score": 99}, "output": {"questions": "PRIVATE"}}
    monkeypatch.setattr(routes, "all_of", lambda conn, kind: [private] if kind == "self_study" else [])
    result = routes.classroom_paths("c", {"id": "t", "org": "o", "role": "teacher"})
    assert result[0]["path"] is None and result[0]["latest_request"] is None
    assert "PRIVATE" not in str(result) and "99" not in str(result)


def test_focused_demo_has_ten_distinct_learners_with_feedback():
    fixtures = json.loads(Path("mock_data/focused_demo.json").read_text())["students"]
    assert len(fixtures) == len({s["student_id"] for s in fixtures}) == 10
    assert all(len(s["concept_scores"]) == 5 and s["feedback"]["comment"] for s in fixtures)


def test_focused_demo_seeds_each_path_once_and_preserves_existing_evidence(monkeypatch):
    from mock_data import focused_demo
    fixtures = json.loads(Path("mock_data/focused_demo.json").read_text())["students"]
    course = {"id": "python-foundations", "org": "demo", "teacher_id": "teacher-demo", "students": [f"student-{i+1}" for i in range(30)], "concepts": [{"id": key, "name": key} for key in fixtures[0]["concept_scores"]]}
    existing = {"id": "existing", "course_id": course["id"], "student_id": "student-1", "concept_id": "functions", "score": 1, "confidence": 1}
    records = {("course", course["id"]): course, ("evidence", "existing"): existing}
    for row in fixtures:
        records[("user", row["student_id"])] = {"id": row["student_id"], "name": row["name"], "org": "demo"}
    monkeypatch.setattr(focused_demo, "get", lambda conn, kind, id: records.get((kind, id)))
    monkeypatch.setattr(focused_demo, "put", lambda conn, kind, data: records.update({(kind, data["id"]): data}) or data)
    monkeypatch.setattr(focused_demo, "all_of", lambda conn, kind: [data for (k, _), data in records.items() if k == kind])
    focused_demo.seed(None)
    assert len(course["students"]) == 10
    assert sum(kind == "self_study" for kind, _ in records) == 10
    assert sum(kind == "learning_feedback" for kind, _ in records) == 10
    assert records[("evidence", "existing")] == existing
    size = len(records)
    focused_demo.seed(None)
    assert len(records) == size


def test_direct_rank_question_uses_anonymous_context_without_reasoning():
    from backend.agents.learning_coach.dispatch import progress_summary
    context = {"question": "What is my rank in class compared to others on overall progress?", "class_performance": {"your_rank": 2, "comparable_learners": 10, "enrolled_learners": 10, "learners_with_evidence": 10, "class_mean_mastery": 65}}
    reply = progress_summary(context)
    assert "2 of 10" in reply and "65%" in reply and "provisional" in reply
