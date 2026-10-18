"""Deterministic evidence aggregation; absence of evidence is never a zero."""
from .store import all_of


def learning_twin(conn, course, student_id, evidence=None):
    evidence = [e for e in (all_of(conn, "evidence") if evidence is None else evidence) if e["course_id"] == course["id"] and e["student_id"] == student_id]
    concepts = []
    for c in course["concepts"]:
        samples = [e for e in evidence if e["concept_id"] == c["id"]]
        weight = sum(e["confidence"] for e in samples)
        mastery = round(sum(e["score"] * e["confidence"] for e in samples) / weight * 100) if weight else None
        status = "not yet taught" if c.get("teaching_status") == "planned" and not samples else "insufficient evidence" if len(samples) < 3 else "demonstrated mastery" if mastery >= 80 else "likely mastery" if mastery >= 60 else "requires review"
        concepts.append({**c, "mastery": mastery, "confidence": round(min(.95, weight / (weight + 3)), 2), "evidence_count": len(samples), "status": status, "evidence": samples[-10:]})
    known = [c["mastery"] for c in concepts if c["mastery"] is not None]
    taught = [c for c in concepts if c.get("teaching_status") != "planned"]
    return {"taught_coverage": round(sum(c["evidence_count"] > 0 for c in taught)/len(taught)*100) if taught else 0, "student_id": student_id, "course_id": course["id"], "concepts": concepts, "mastery": round(sum(known) / len(known)) if known else None, "evidence_count": len(evidence), "coverage": round(sum(c["evidence_count"] > 0 for c in concepts) / len(concepts) * 100), "pace": "Not enough timed history", "method": "Confidence-weighted evidence average; confidence reflects coverage, not calibrated probability."}


def classroom_twins(conn, course, student_ids, evidence=None):
    """One evidence read for the entire class instead of one cloud round trip per learner."""
    evidence = all_of(conn, "evidence") if evidence is None else evidence
    return [learning_twin(conn, course, student_id, evidence=evidence) for student_id in student_ids]


def validate_exam(blueprint, questions, course):
    if len(questions) != blueprint["question_count"] or sum(q["marks"] for q in questions) != blueprint["total_marks"]:
        raise ValueError("Question count or total marks does not match blueprint")
    if len({q["id"] for q in questions}) != len(questions) or len({q["prompt"].strip().casefold() for q in questions}) != len(questions):
        raise ValueError("Duplicate questions or identifiers")
    if set(blueprint["concept_ids"]) != {q["concept_id"] for q in questions}:
        raise ValueError("Concept coverage does not match blueprint")
    materials = {m["id"] for m in course["materials"]}
    for q in questions:
        if q["type"] not in blueprint["question_types"] or q["difficulty"] != blueprint["difficulty"] or q["material_id"] not in materials or q["objective"] not in course["objectives"]:
            raise ValueError("Question format, difficulty, objective or material reference is outside the blueprint")


def objective_scores(exam, answers):
    results = []
    for q in exam["questions"]:
        objective = q["type"] == "mcq"
        score = q["marks"] if objective and answers.get(q["id"]) == q["answer"] else 0 if objective else None
        results.append({"question_id": q["id"], "concept_id": q["concept_id"], "score": score, "marks": q["marks"], "method": "objective" if objective else "teacher_review", "feedback": "Correct" if score else "Review the concept" if objective else "Awaiting teacher evaluation"})
    return results
