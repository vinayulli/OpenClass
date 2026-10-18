"""Student-owned conversation threads; academic memory spans threads."""
from fastapi import HTTPException
from .store import get, put, uid, now


def authorize(conn, conversation_id, course_id, actor):
    item = get(conn, "chat_session", conversation_id)
    if not item or (item["user_id"], item["course_id"], item["org"]) != (actor["id"], course_id, actor["org"]):
        raise HTTPException(404, "Conversation not found")
    return item


def create(conn, course_id, actor):
    return put(conn, "chat_session", {"id": uid(), "course_id": course_id, "org": actor["org"], "user_id": actor["id"], "title": "New conversation", "created_at": now(), "updated_at": now()})


def academic_snapshot(records, course, student_id):
    """Allowlisted academic data: never include exam questions or answer keys."""
    exams = {e["id"]: e for e in records["exam"] if e["course_id"] == course["id"]}
    attempts = [{k: a[k] for k in ("id", "exam_id", "status", "submitted_at", "created_at") if k in a} for a in records["attempt"] if a["student_id"] == student_id and a["exam_id"] in exams]
    for attempt in attempts:
        exam = exams[attempt["exam_id"]]
        attempt["title"] = exam["title"]
        original = next(a for a in records["attempt"] if a["id"] == attempt["id"])
        attempt["feedback_withheld"] = not exam["blueprint"].get("release_feedback", False)
        if original["status"] == "graded" and not attempt["feedback_withheld"]:
            attempt["score"] = original.get("score")
            attempt["concept_results"] = [{k: r.get(k) for k in ("concept_id", "score", "marks", "method")} for r in original.get("results", [])]
    assignments = [{k: a.get(k) for k in ("id", "title", "instructions", "concept_ids", "created_at")} for a in records["coding_assignment"] if a["course_id"] == course["id"] and (not a.get("student_ids") or student_id in a["student_ids"])]
    submissions = [{k: s.get(k) for k in ("id", "assignment_id", "url", "status", "report", "created_at")} for s in records["code_review"] if s["course_id"] == course["id"] and s["student_id"] == student_id]
    plans = [{k: p.get(k) for k in ("id", "title", "concept_id", "status", "lesson", "exercise")} for p in records["intervention"] if p["course_id"] == course["id"] and p["student_id"] == student_id and p["status"] == "assigned"]
    available = [{"id": e["id"], "title": e["title"]} for e in exams.values() if e["status"] == "published" and (not e.get("assigned_student_ids") or student_id in e["assigned_student_ids"]) and (not e["blueprint"].get("student_id") or e["blueprint"]["student_id"] == student_id)]
    tracked = [{k: s.get(k) for k in ("id", "assignment_id", "url", "status", "created_at", "error", "review_id")} for s in records.get("assignment_submission", []) if s["course_id"] == course["id"] and s["student_id"] == student_id]
    return {"assignment_submissions": tracked[-30:], "assessment_history": attempts[-30:], "available_tests": available, "coding_assignments": assignments, "submitted_repositories": submissions[-20:], "assigned_learning_plans": plans, "counts": {"assessment_attempts": len(attempts), "repository_submissions": len(submissions)}, "note": "Repository ratings are provisional, not final grades. Recent history is bounded; mastery evidence is in the Learning Twin."}
