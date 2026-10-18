from fastapi import APIRouter, Depends, HTTPException
from ..analytics import classroom_metrics, simulate_concept
from ..learning import learning_twin, classroom_twins, validate_exam
from ..schemas import CodingAssignment, CodeSubmission, ExamAudience, ManualExam, TwinSimulation
from ..services import ai_call, course_access, exam_access, rate_limit, safe_attempt, teacher, user
from ..store import all_of, audit, db, get, now, put, uid

router = APIRouter()


@router.get("/api/courses/{course_id}/analytics")
def analytics(course_id: str, current=Depends(user)):
    with db() as conn:
        course = course_access(conn, course_id, current)
        students = course["students"] if current["role"] == "teacher" else [current["id"]]
        twins = classroom_twins(conn, course, students)
        attempts = [a for a in all_of(conn, "attempt") if a["course_id"] == course_id and a["student_id"] in students]
        if current["role"] == "student":
            attempts = [safe_attempt(conn, a, current) for a in attempts]
        return classroom_metrics(twins, attempts, course["concepts"])


@router.post("/api/courses/{course_id}/students/{student_id}/simulate")
def simulate(course_id: str, student_id: str, body: TwinSimulation, current=Depends(teacher)):
    with db() as conn:
        course = course_access(conn, course_id, current)
        if student_id not in course["students"]:
            raise HTTPException(404)
        twin = learning_twin(conn, course, student_id)
        concept = next((c for c in twin["concepts"] if c["id"] == body.concept_id), None)
        if concept is None:
            raise HTTPException(422, "Unknown course concept")
    return {"student_id": student_id, "concept_id": concept["id"], "hypothetical": True, **simulate_concept(concept, body.action, body.assumed_score, body.observations)}


@router.post("/api/courses/{course_id}/exams")
def manual_test(course_id: str, body: ManualExam, current=Depends(teacher)):
    with db() as conn:
        course = course_access(conn, course_id, current)
        if not set(body.student_ids) <= set(course["students"]) or body.blueprint.student_id and body.blueprint.student_id not in course["students"]:
            raise HTTPException(422, "Test recipients must be enrolled in this course")
        questions = [q.model_dump() for q in body.questions]
        try:
            validate_exam(body.blueprint.model_dump(), questions, course)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        exam = put(conn, "exam", {"id": uid(), "course_id": course_id, "title": body.blueprint.title, "blueprint": body.blueprint.model_dump(), "questions": questions, "status": "draft", "assigned_student_ids": body.student_ids, "source": "Teacher-authored test", "created_at": now()})
        audit(conn, current["id"], "exam.created", exam["id"])
        return exam


@router.post("/api/exams/{exam_id}/assign")
def assign_test(exam_id: str, body: ExamAudience, current=Depends(teacher)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812404)")
        exam, course = exam_access(conn, exam_id, current)
        if not set(body.student_ids) <= set(course["students"]):
            raise HTTPException(422, "Recipients must be enrolled")
        personalized_for = exam["blueprint"].get("student_id")
        if personalized_for and any(s != personalized_for for s in body.student_ids):
            raise HTTPException(422, "This personalized test can only be assigned to its selected learner; create a common blueprint for a group")
        if any(a["exam_id"] == exam_id for a in all_of(conn, "attempt")):
            raise HTTPException(409, "Test recipients are locked after the first attempt starts")
        exam["assigned_student_ids"] = list(dict.fromkeys(body.student_ids))
        audit(conn, current["id"], "exam.assigned", exam_id)
        if exam["status"] == "published":
            from ..notifications import notify, exam_recipients
            notify(conn, course, exam_recipients(course, exam), "assessment.published", "Test to complete: "+exam["title"], "Your educator assigned this test. Open Assessments to begin.", "exam", exam_id)
        return put(conn, "exam", exam)


@router.get("/api/courses/{course_id}/coding-assignments")
def coding_assignments(course_id: str, current=Depends(user)):
    with db() as conn:
        course_access(conn, course_id, current)
        assignments = [a for a in all_of(conn, "coding_assignment") if a["course_id"] == course_id and (current["role"] == "teacher" or not a["student_ids"] or current["id"] in a["student_ids"])]
        submissions = [s for s in all_of(conn, "code_review") if s["course_id"] == course_id and (current["role"] == "teacher" or s["student_id"] == current["id"])]
        tracked = [s for s in all_of(conn, "assignment_submission") if s["course_id"] == course_id and s["org"] == current["org"] and (current["role"] == "teacher" or s["student_id"] == current["id"])]
        return {"assignments": assignments, "submissions": submissions, "tracked_submissions": tracked}


@router.post("/api/courses/{course_id}/coding-assignments")
def create_assignment(course_id: str, body: CodingAssignment, current=Depends(teacher)):
    with db() as conn:
        course = course_access(conn, course_id, current)
        if not set(body.concept_ids) <= {c["id"] for c in course["concepts"]} or not set(body.student_ids) <= set(course["students"]):
            raise HTTPException(422, "Use concepts and learners from this course")
        from ..assignments import AssignmentRecord
        result = put(conn, "coding_assignment", AssignmentRecord(**body.model_dump(), id=uid(), course_id=course_id, org=current["org"], teacher_id=current["id"], created_at=now()).model_dump())
        audit(conn, current["id"], "coding_assignment.created", result["id"])
        from ..notifications import notify
        notify(conn, course, body.student_ids or course["students"], "coding_assignment.created", "New coding assignment", "Your educator created a Git repository assignment.", "assignment", result["id"])
        return result


@router.post("/api/courses/{course_id}/coding-submissions", status_code=202)
def submit_code(course_id: str, body: CodeSubmission, current=Depends(user)):
    if current["role"] != "student":
        raise HTTPException(403, "Learner submission required")
    rate_limit("ai:"+current["id"], 10, 3600)
    from ..assignments import SubmissionRecord, accessible_assignment
    import re
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", body.url):
        raise HTTPException(422, "Use a public https://github.com/owner/repository URL")
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812415)")
        course, assignment = accessible_assignment(conn, course_id, body.assignment_id, current)
        previous = [s for s in all_of(conn, "assignment_submission") if s["assignment_id"] == body.assignment_id and s["student_id"] == current["id"]]
        active = next((s for s in previous if s["status"] in {"queued", "processing"}), None)
        if active:
            if active["url"] != body.url:
                raise HTTPException(409, "An assignment review is already running. Wait for it to finish before submitting another repository.")
            return active
        item = SubmissionRecord(id=uid(), assignment_id=body.assignment_id, course_id=course_id, org=current["org"], student_id=current["id"], url=body.url, created_at=now(), updated_at=now(), attempt_number=len(previous)+1).model_dump()
        put(conn, "assignment_submission", item)
        audit(conn, current["id"], "coding_assignment.submitted", item["id"])
        return item


@router.post("/api/coding-submissions/{submission_id}/retry", status_code=202)
def retry_submission(submission_id: str, current=Depends(user)):
    from ..assignments import accessible_assignment
    rate_limit("ai:"+current["id"], 10, 3600)
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812415)")
        conn.execute("SELECT data FROM records WHERE id=%s FOR UPDATE", (submission_id,))
        item = get(conn, "assignment_submission", submission_id)
        if not item or item["student_id"] != current["id"] or item["org"] != current["org"]:
            raise HTTPException(404)
        accessible_assignment(conn, item["course_id"], item["assignment_id"], current)
        if item["status"] != "failed":
            raise HTTPException(409, "Only failed reviews can be retried")
        active = any(s["id"] != item["id"] and s["assignment_id"] == item["assignment_id"] and s["student_id"] == current["id"] and s["status"] in {"queued", "processing"} for s in all_of(conn, "assignment_submission"))
        if active:
            raise HTTPException(409, "Another review is already running for this assignment")
        item.update(status="queued", error=None, lease_until=None, updated_at=now())
        return put(conn, "assignment_submission", item)


@router.get("/api/courses/{course_id}/agent-sessions")
def agent_sessions(course_id: str, current=Depends(teacher)):
    from ..agents.runner import REGISTRY
    from ..agents.sessions import session_key
    with db() as conn:
        course_access(conn, course_id, current)
    return [{"kind": kind, "name": agent.NAME, "session_id": session_key(current["org"], course_id, current["id"], kind), "storage": "PostgreSQL chat records" if kind in {"teacher", "tutor"} else "Saved agent sessions", "note": "Shared agent definition, isolated actor/course identity. Interactive chat keeps its history/session ID in PostgreSQL and uses temporary graph checkpoints by default. Full interactive checkpoints are opt-in. A2A tasks remain durable; personalized assessments use the selected learner's assessment session."} for kind, agent in REGISTRY.items()]
