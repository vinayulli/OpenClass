"""Validate contracts and relationships offline; no database or model calls."""
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def validate():
    from backend.schemas import Blueprint, CodeOutput, CourseInput, ExamOutput, InterventionOutput
    from backend.learning import learning_twin, validate_exam
    accounts = load("accounts.json")
    courses = load("courses.json")
    evidence = load("evidence.json")
    exams = load("exams.json")
    plans = load("interventions.json")
    attempts = load("attempts.json")
    assignments = load("coding_assignments.json")
    reports = load("code_reviews.json")
    all_records = accounts + courses + evidence + exams + plans + attempts + assignments + reports
    assert len({r["id"] for r in all_records}) == len(all_records), "Fixture IDs must be globally unique"
    assert all(r.get("synthetic") and r["id"].startswith("mock-") for r in all_records)
    users = {u["id"]: u for u in accounts}
    course_map = {c["id"]: c for c in courses}
    for course in courses:
        CourseInput.model_validate(course)
        assert users[course["teacher_id"]]["role"] == "teacher"
        assert all(users[s]["role"] == "student" and users[s]["org"] == course["org"] for s in course["students"])
    for item in evidence:
        course = course_map[item["course_id"]]
        assert item["student_id"] in course["students"]
        assert item["concept_id"] in {c["id"] for c in course["concepts"]}
        assert 0 <= item["score"] <= 1 and 0 < item["confidence"] <= 1
    for exam in exams:
        Blueprint.model_validate(exam["blueprint"])
        ExamOutput.model_validate(exam)
        validate_exam(exam["blueprint"], exam["questions"], course_map[exam["course_id"]])
    for plan in plans:
        InterventionOutput.model_validate(plan)
        assert plan["student_id"] in course_map[plan["course_id"]]["students"]
    exam_map = {e["id"]: e for e in exams}
    for attempt in attempts:
        assert attempt["exam_id"] in exam_map
        assert attempt["student_id"] in course_map[attempt["course_id"]]["students"]
        assert attempt["score"] == sum(r["score"] for r in attempt["results"])
        assert 0 <= attempt["score"] <= attempt["total_marks"]
    for assignment in assignments:
        assert assignment["course_id"] in course_map
    for report in reports:
        CodeOutput.model_validate(report["report"])
        assert report["assignment_id"] in {a["id"] for a in assignments}
    for file in (ROOT / "agent_cases").glob("*.json"):
        case = json.loads(file.read_text(encoding="utf-8"))
        schema = {"exam": ExamOutput, "intervention": InterventionOutput, "code": CodeOutput}.get(case["agent"])
        if schema:
            schema.model_validate(case["example_output"])
        else:
            assert isinstance(case["example_output"]["message"], str)
    with patch("backend.learning.all_of", return_value=evidence):
        for snapshot in load("learning_twins.json"):
            assert learning_twin(None, course_map[snapshot["course_id"]], snapshot["student_id"]) == snapshot, "Regenerate Twin snapshots after changing the evidence algorithm"
    return all_records


if __name__ == "__main__":
    print(f"Validated {len(validate())} synthetic records, five agent cases and derived Twin snapshots; no database writes.")
