import os
import time
from fastapi import APIRouter, Depends, HTTPException
from .. import agents
from ..learning import objective_scores, validate_exam
from ..schemas import Answers, Blueprint, Question, ReviewGrade
from ..store import all_of, audit, db, get, now, put, uid
from ..services import user, teacher, course_access, exam_access, safe_exam, safe_attempt, own_attempt, write_evidence, rate_limit

router = APIRouter()

@router.post("/api/courses/{course_id}/exams/generate", status_code=202)
async def generate(course_id: str, body: Blueprint, current=Depends(teacher)):
    rate_limit("ai:"+current["id"], 10, 3600)
    from ..agents.coordinator.service import queue_assessment_async
    return await queue_assessment_async({"id": course_id}, current, body.model_dump())


@router.post("/api/courses/{course_id}/exams/sample")
def sample(course_id: str, current=Depends(teacher)):
    if os.getenv("OPENCLASS_DEMO", "true").lower() != "true":
        raise HTTPException(404)
    with db() as conn:
        course = course_access(conn, course_id, current)
        if course_id != "python-foundations":
            raise HTTPException(422, "Sample questions apply only to the demo Python course")
        blueprint = Blueprint(title="Functions · knowledge check", concept_ids=["functions", "parameters"], question_count=2, total_marks=4).model_dump()
        qs = [Question(id="q1", prompt="Which keyword defines a Python function?", type="mcq", concept_id="functions", objective=course["objectives"][0], difficulty="beginner", marks=2, options=["def", "class", "return", "import"], answer="def", rubric="2 marks for def; otherwise 0.", explanation="def introduces a function definition.", material_id="intro").model_dump(), Question(id="q2", prompt="What does return do inside a function?", type="mcq", concept_id="parameters", objective=course["objectives"][0], difficulty="beginner", marks=2, options=["Passes a value to the caller", "Prints every local variable", "Defines a parameter", "Imports a module"], answer="Passes a value to the caller", rubric="2 marks for passing a value to the caller.", explanation="return ends the function and provides its result to the caller.", material_id="intro").model_dump()]
        validate_exam(blueprint, qs, course)
        return put(conn, "exam", {"id": uid(), "course_id": course_id, "title": blueprint["title"], "blueprint": blueprint, "questions": qs, "status": "draft", "created_at": now(), "source": "Handwritten demo sample"})


@router.get("/api/jobs/{job_id}")
def job(job_id: str, current=Depends(user)):
    with db() as conn:
        result = get(conn, "job", job_id)
        if not result or result["user_id"] != current["id"]:
            raise HTTPException(404)
        return result


@router.put("/api/exams/{exam_id}/questions")
def edit_exam(exam_id: str, questions: list[Question], current=Depends(teacher)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812403)")
        exam, course = exam_access(conn, exam_id, current)
        if exam["status"] != "draft":
            raise HTTPException(409, "Published exams are locked")
        values = [q.model_dump() for q in questions]
        try:
            validate_exam(exam["blueprint"], values, course)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        exam["questions"] = values
        audit(conn, current["id"], "exam.edited", exam_id)
        return put(conn, "exam", exam)


@router.post("/api/exams/{exam_id}/publish")
def publish(exam_id: str, current=Depends(teacher)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812403)")
        exam, course = exam_access(conn, exam_id, current)
        validate_exam(exam["blueprint"], exam["questions"], course)
        exam.update(status="published", published_at=now())
        audit(conn, current["id"], "exam.published", exam_id)
        from ..notifications import notify, exam_recipients
        notify(conn, course, exam_recipients(course, exam), "assessment.published", "New assessment available", "Your educator published an assessment for you.", "exam", exam_id)
        return put(conn, "exam", exam)


@router.post("/api/exams/{exam_id}/attempt")
def start_attempt(exam_id: str, current=Depends(user)):
    if current["role"] != "student":
        raise HTTPException(403, "Sign in as a learner to take an assessment")
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812404)")
        exam, course = exam_access(conn, exam_id, current)
        attempt = next((a for a in all_of(conn, "attempt") if a["exam_id"] == exam_id and a["student_id"] == current["id"]), None)
        if not attempt:
            attempt = put(conn, "attempt", {"id": uid(), "exam_id": exam_id, "course_id": course["id"], "student_id": current["id"], "status": "in_progress", "answers": {}, "started_at": now(), "deadline": time.time()+exam["blueprint"]["duration_minutes"]*60})
        return {"attempt": safe_attempt(conn, attempt, current), "exam": safe_exam(exam, current)}


@router.put("/api/attempts/{attempt_id}/answers")
def save_answers(attempt_id: str, body: Answers, current=Depends(user)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812404)")
        attempt = own_attempt(conn, attempt_id, current)
        if attempt["status"] != "in_progress" or time.time() > attempt["deadline"]:
            raise HTTPException(409, "Attempt is submitted or time has expired. Submit your saved answers.")
        exam = get(conn, "exam", attempt["exam_id"])
        if not set(body.answers) <= {q["id"] for q in exam["questions"]} or any(len(v) > 20000 for v in body.answers.values()):
            raise HTTPException(422, "Invalid answer payload")
        attempt.update(answers=body.answers, saved_at=now())
        put(conn, "attempt", attempt)
        return {"saved_at": attempt["saved_at"]}


@router.post("/api/attempts/{attempt_id}/submit")
def submit(attempt_id: str, current=Depends(user)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812404)")
        attempt = own_attempt(conn, attempt_id, current)
        if attempt["status"] == "in_progress":
            exam = get(conn, "exam", attempt["exam_id"])
            results = objective_scores(exam, attempt["answers"])
            attempt.update(results=results, status="review_required" if any(r["score"] is None for r in results) else "graded", score=sum(r["score"] or 0 for r in results), total_marks=exam["blueprint"]["total_marks"], submitted_at=now())
            put(conn, "attempt", attempt)
            write_evidence(conn, attempt)
            audit(conn, current["id"], "attempt.submitted", attempt_id)
            from ..notifications import notify
            course = get(conn, "course", attempt["course_id"])
            notify(conn, course, [course["teacher_id"]], "attempt.submitted:"+attempt_id, "Learner assessment submitted", "A learner submitted an assessment. Open their profile to review the evidence.", "learner", attempt["student_id"])
            notify(conn, course, [current["id"]], "attempt.received", "Assessment submission received", "Your saved answers were submitted and learning evidence updated.", "exam", exam["id"])
        return safe_attempt(conn, attempt, current)


@router.post("/api/attempts/{attempt_id}/review")
def review(attempt_id: str, body: ReviewGrade, current=Depends(teacher)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812404)")
        attempt = get(conn, "attempt", attempt_id)
        if not attempt:
            raise HTTPException(404)
        course_access(conn, attempt["course_id"], current)
        if attempt["status"] == "in_progress":
            raise HTTPException(409, "Cannot grade an active attempt")
        if not set(body.scores) <= {r["question_id"] for r in attempt["results"]}:
            raise HTTPException(422, "Unknown question")
        for r in attempt["results"]:
            if r["question_id"] in body.scores:
                score = body.scores[r["question_id"]]
                if not 0 <= score <= r["marks"]:
                    raise HTTPException(422, "Score outside question marks")
                r.update(score=score, method="teacher_review", feedback=body.reason)
        attempt.update(score=sum(r["score"] or 0 for r in attempt["results"]), status="review_required" if any(r["score"] is None for r in attempt["results"]) else "graded")
        put(conn, "attempt", attempt)
        write_evidence(conn, attempt)
        audit(conn, current["id"], "grade.reviewed: "+body.reason, attempt_id)
        from ..notifications import notify
        course = get(conn, "course", attempt["course_id"])
        notify(conn, course, [attempt["student_id"]], "grade.reviewed", "Assessment review updated", "Your educator reviewed an assessment. Feedback follows the test release policy.", "exam", attempt["exam_id"])
        return attempt


