from collections import Counter
from mock_data.machine_learning import fixture_records
from backend.learning import learning_twin, validate_exam
from backend.schemas import CourseInput, ExamOutput, CodeOutput
from backend.agents.learning_path.agent import SCHEMA


def test_ml_demo_has_ten_distinct_profiles_and_exact_70_percent_taught():
    fixture, records = fixture_records()
    course = fixture["course"]
    CourseInput.model_validate(course)
    assert len(course["concepts"]) == 20 and len(course["students"]) == 10
    assert sum(c["teaching_status"] == "taught" for c in course["concepts"]) == 14
    assert course["syllabus_progress"]["percent_complete"] == 70
    profiles = [r for k,r in records if k == "learner_profile"]
    assert len({r["headline"] for r in profiles}) == 10
    evidence = [r for k,r in records if k == "evidence"]
    planned = {c["id"] for c in course["concepts"] if c["teaching_status"] == "planned"}
    assert all(r["concept_id"] not in planned for r in evidence)
    twins = [learning_twin(None, course, id, evidence=evidence) for id in course["students"]]
    assert len({t["mastery"] for t in twins}) >= 7
    assert any(t["taught_coverage"] < 100 for t in twins)
    assert all(c["status"] == "not yet taught" for t in twins for c in t["concepts"] if c["id"] in planned)


def test_ml_fixtures_include_valid_detailed_paths_tests_and_reports():
    fixture, records = fixture_records()
    assert len({r["id"] for _, r in records}) == len(records)
    counts = Counter(kind for kind, _ in records)
    assert counts["self_study"] == counts["learning_feedback"] == 10
    assert counts["attempt"] >= 20 and counts["coding_assignment"] == 2
    for kind, item in records:
        if kind == "self_study":
            plan = SCHEMA.model_validate(item["output"])
            allowed = {r["id"] for r in item["output"]["reference_catalog"]}
            assert all(ref.resource_id in allowed for step in plan.steps for ref in step.references)
        elif kind == "exam":
            ExamOutput.model_validate(item)
            validate_exam(item["blueprint"], item["questions"], fixture["course"])
        elif kind == "code_review":
            CodeOutput.model_validate(item["report"])
