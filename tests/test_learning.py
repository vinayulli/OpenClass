import pytest
from backend.learning import objective_scores, validate_exam
from backend.schemas import Blueprint, CourseInput


def question(**changes):
    return {"id": "q1", "prompt": "Which keyword defines a Python function?", "marks": 2, "concept_id": "functions", "difficulty": "beginner", "type": "mcq", "answer": "def", "material_id": "m1", "objective": "Write functions", **changes}


def test_no_credit_for_missing_or_incorrect_answers():
    exam = {"questions": [question()]}
    assert objective_scores(exam, {})[0]["score"] == 0
    assert objective_scores(exam, {"q1": "class"})[0]["score"] == 0
    assert objective_scores(exam, {"q1": "def"})[0]["score"] == 2


def test_free_text_waits_for_review():
    result = objective_scores({"questions": [question(type="coding")]}, {"q1": "some code"})[0]
    assert result["score"] is None
    assert result["method"] == "teacher_review"


def test_validate_exact_blueprint():
    blueprint = Blueprint(title="Test", concept_ids=["functions"], question_count=1, total_marks=2).model_dump()
    course = {"materials": [{"id": "m1"}], "objectives": ["Write functions"]}
    validate_exam(blueprint, [question()], course)
    for q in [question(marks=3), question(concept_id="other"), question(material_id="made-up"), question(objective="Invented objective"), question(difficulty="advanced")]:
        with pytest.raises(ValueError):
            validate_exam(blueprint, [q], course)


def test_cycles_are_rejected():
    with pytest.raises(ValueError):
        CourseInput(name="Test", objectives=["Learn"], concepts=[{"id": "a", "name": "A", "prerequisites": ["b"]}, {"id": "b", "name": "B", "prerequisites": ["a"]}])


def test_formal_personalization_disallowed():
    with pytest.raises(ValueError):
        Blueprint(title="Formal", kind="formal", student_id="s", concept_ids=["a"])


def test_missing_evidence_is_unknown(monkeypatch):
    import backend.learning as learning
    monkeypatch.setattr(learning, "all_of", lambda *_: [])
    twin = learning.learning_twin(None, {"id": "c", "concepts": [{"id": "functions", "name": "Functions", "prerequisites": []}]}, "s")
    assert twin["mastery"] is None
    assert twin["concepts"][0]["status"] == "insufficient evidence"
