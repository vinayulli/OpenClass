from backend.analytics import classroom_metrics, simulate_concept
from backend.agents.sessions import session_key


def test_lesson_completion_does_not_imply_mastery():
    c = {"mastery": None, "evidence": []}
    result = simulate_concept(c, "lesson_only", 1, 10)
    assert result["simulated"] is None
    assert result["additional_observations"] == 0


def test_simulation_uses_assumed_evidence_without_mutation():
    c = {"mastery": 50, "evidence": [{"score": .5, "confidence": 1}]}
    result = simulate_concept(c, "reassessment", 1, 1)
    assert result["simulated"] == 75
    assert c["mastery"] == 50 and len(c["evidence"]) == 1


def test_missing_evidence_is_distinct_from_a_zero_score():
    twins = [{"mastery": None, "coverage": 0, "evidence_count": 0, "concepts": []}, {"mastery": 0, "coverage": 100, "evidence_count": 3, "concepts": []}]
    result = classroom_metrics(twins, [], [])
    assert result["bands"]["no_evidence"] == 1
    assert result["bands"]["review"] == 1
    assert result["average_mastery"] == 0
    assert result["average_assessment_score"] is None


def test_session_identity_is_stable_and_scope_isolated():
    key = session_key("o", "c", "student1", "tutor")
    assert key == session_key("o", "c", "student1", "tutor")
    assert len({key, session_key("o2", "c", "student1", "tutor"), session_key("o", "c2", "student1", "tutor"), session_key("o", "c", "student2", "tutor"), session_key("o", "c", "student1", "code")}) == 5
