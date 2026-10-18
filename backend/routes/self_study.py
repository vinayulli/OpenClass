"""Owner-only self-study records, deliberately separate from teacher assessments."""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..services import user, course_access, rate_limit
from ..store import db, all_of, get, put, now, uid

router = APIRouter()


class StudyRequest(BaseModel):
    concept_ids: list[str] = Field(min_length=1, max_length=5)
    question_count: int = Field(default=5, ge=1, le=10)


class PracticeAnswers(BaseModel):
    answers: dict[str, str] = Field(max_length=10)


def require_student(actor):
    if actor["role"] != "student":
        raise HTTPException(403, "Private self-study is available only to students")


def access(conn, course_id, actor):
    require_student(actor)
    course = course_access(conn, course_id, actor)
    if any(a["student_id"] == actor["id"] and a["status"] == "in_progress" for a in all_of(conn, "attempt")):
        raise HTTPException(409, "Self-study generation is paused during an active assessment")
    return course


def owned(item, actor):
    require_student(actor)
    if not item or item["student_id"] != actor["id"] or item["org"] != actor["org"]:
        raise HTTPException(404)
    return item


def public(item):
    result = {k: v for k, v in item.items() if k not in {"output", "lease_until"}}
    if item["status"] == "completed":
        if item["type"] == "path":
            result["output"] = item["output"]
        elif item.get("result"):
            result["output"] = item["output"]
        else:
            result["output"] = {"questions": [{k: q[k] for k in ("id", "prompt", "options", "marks", "concept_id")} for q in item["output"]["questions"]]}
    return result


@router.get("/api/courses/{course_id}/self-study")
def list_study(course_id: str, actor=Depends(user)):
    require_student(actor)
    with db() as conn:
        course_access(conn, course_id, actor)
        return [public(s) for s in all_of(conn, "self_study") if s["course_id"] == course_id and s["student_id"] == actor["id"] and s["org"] == actor["org"]]


@router.post("/api/courses/{course_id}/self-study/{kind}", status_code=202)
def generate_study(course_id: str, kind: str, body: StudyRequest, actor=Depends(user)):
    require_student(actor)
    if kind not in {"practice", "path"}:
        raise HTTPException(404)
    rate_limit("self-study:"+actor["id"], 15, 3600)
    with db() as conn:
        course = access(conn, course_id, actor)
        if len(set(body.concept_ids)) != len(body.concept_ids) or not set(body.concept_ids) <= {c["id"] for c in course["concepts"]}:
            raise HTTPException(422, "Select distinct course topics")
        if kind == "practice" and body.question_count < len(body.concept_ids):
            raise HTTPException(422, "Choose at least one question per topic")
        if kind == "path":
            conn.execute("SELECT pg_advisory_xact_lock(7812416)")
            from ..learning_paths import enqueue
            return public(enqueue(conn, course, actor["id"], body.concept_ids, actor["id"]))
        return public(put(conn, "self_study", {"id": uid(), "type": kind, "course_id": course_id, "org": actor["org"], "student_id": actor["id"], "request": body.model_dump(), "status": "queued", "created_at": now(), "updated_at": now(), "error": None}))


@router.post("/api/self-study/{study_id}/submit")
def submit_practice(study_id: str, body: PracticeAnswers, actor=Depends(user)):
    require_student(actor)
    with db() as conn:
        conn.execute("SELECT data FROM records WHERE id=%s FOR UPDATE", (study_id,))
        item = owned(get(conn, "self_study", study_id), actor)
        access(conn, item["course_id"], actor)
        if item["type"] != "practice" or item["status"] != "completed":
            raise HTTPException(409, "This practice test is not ready")
        if item.get("result"):
            return public(item)
        questions = item["output"]["questions"]
        if set(body.answers) != {q["id"] for q in questions} or any(body.answers[q["id"]] not in q["options"] for q in questions):
            raise HTTPException(422, "Answer every question using one of its options")
        score = sum(q["marks"] for q in questions if body.answers[q["id"]] == q["answer"])
        item["result"] = {"answers": body.answers, "score": score, "total_marks": sum(q["marks"] for q in questions), "submitted_at": now(), "private": True, "official_grade": False}
        item["updated_at"] = now()
        put(conn, "self_study", item)
        return public(item)
