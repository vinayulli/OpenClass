"""Authorized academic read model shared by API and Classroom Advisor tools."""
from fastapi import HTTPException
from .learning import learning_twin
from .services import course_access, public_user
from .store import all_of, get


def details(conn, course_id, student_id, actor):
    course = course_access(conn, course_id, actor)
    if student_id not in course["students"] or (actor["role"] != "teacher" and student_id != actor["id"]):
        raise HTTPException(404, "Learner not found")
    student = get(conn, "user", student_id)
    scoped = lambda kind: [r for r in all_of(conn, kind) if r.get("course_id") == course_id and r.get("student_id") == student_id]
    attempts = scoped("attempt")
    if actor["role"] != "teacher":
        from .services import safe_attempt
        attempts = [safe_attempt(conn, a, actor) for a in attempts]
    exams = {e["id"]: e["title"] for e in all_of(conn, "exam") if e["course_id"] == course_id}
    return {"student": public_user(student), "profile": next(iter(scoped("learner_profile")), None), "course_id": course_id, "twin": learning_twin(conn, course, student_id), "attempts": [{**a, "exam_title": exams.get(a["exam_id"], "Assessment")} for a in attempts], "coding_reports": scoped("code_review"), "interventions": [p for p in scoped("intervention") if actor["role"] == "teacher" or p["status"] == "assigned"], "twin_history": scoped("twin_history")[-20:], "memory_sync": [{k: r.get(k) for k in ("source_id", "status", "attempts", "updated_at")} for r in scoped("memory_outbox")], "note": "Only academic records in this course are included. Missing evidence is not a low-ability conclusion."}
