from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from ..services import user, teacher, course_access, rate_limit
from ..store import db, all_of, get, put, uid, now
from ..learning_paths import paths_for, latest_ready, refresh_due, enqueue
from .self_study import owned, access, public

router = APIRouter()


class Feedback(BaseModel):
    helpfulness: Literal["helpful", "partly_helpful", "not_helpful"]
    difficulty: Literal["too_easy", "right_level", "too_hard"]
    comment: str = Field(default="", max_length=2000)


class RefreshPaths(BaseModel):
    student_ids: list[str] = Field(default_factory=list, max_length=50)


@router.post("/api/self-study/{path_id}/feedback", status_code=201)
def feedback(path_id: str, body: Feedback, actor=Depends(user)):
    with db() as conn:
        item = owned(get(conn, "self_study", path_id), actor)
        course_access(conn, item["course_id"], actor)
        if item["type"] != "path" or item["status"] != "completed":
            raise HTTPException(409, "Feedback requires a completed learning path")
        return put(conn, "learning_feedback", {**body.model_dump(), "id": uid(), "path_id": path_id, "course_id": item["course_id"], "org": actor["org"], "student_id": actor["id"], "created_at": now()})


@router.post("/api/self-study/{path_id}/refresh", status_code=202)
def refresh_path(path_id: str, actor=Depends(user)):
    rate_limit("path-refresh:"+actor["id"], 15, 3600)
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812416)")
        item = owned(get(conn, "self_study", path_id), actor)
        course = access(conn, item["course_id"], actor)
        if item["type"] != "path":
            raise HTTPException(404)
        return public(enqueue(conn, course, actor["id"], item["request"]["concept_ids"], actor["id"]))


@router.get("/api/courses/{course_id}/learning-paths")
def classroom_paths(course_id: str, actor=Depends(teacher)):
    with db() as conn:
        course = course_access(conn, course_id, actor)
        records = all_of(conn, "self_study")
        feedback = all_of(conn, "learning_feedback")
        result = []
        for student_id in course["students"]:
            paths = paths_for(records, course_id, student_id)
            ready = latest_ready(paths)
            result.append({"student_id": student_id, "path": public(ready) if ready else None, "latest_request": public(max(paths, key=lambda s: s["created_at"])) if paths else None, "refresh_due": refresh_due(ready), "feedback": [f for f in feedback if f["course_id"] == course_id and f["student_id"] == student_id and f["org"] == actor["org"]][-5:]})
        return result


@router.post("/api/courses/{course_id}/learning-paths/regenerate", status_code=202)
def regenerate(course_id: str, body: RefreshPaths, actor=Depends(teacher)):
    rate_limit("path-refresh:"+actor["id"], 15, 3600)
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812416)")
        course = course_access(conn, course_id, actor)
        ids = body.student_ids or course["students"]
        if len(set(ids)) != len(ids) or not set(ids) <= set(course["students"]):
            raise HTTPException(422, "Select distinct enrolled students")
        records = all_of(conn, "self_study")
        from ..learning import classroom_twins
        twins = classroom_twins(conn, course, ids)
        paths = []
        for student_id, twin in zip(ids, twins):
            taught = [c for c in twin["concepts"] if c.get("teaching_status") != "planned"]
            targets = sorted(taught, key=lambda c: c["mastery"] if c["mastery"] is not None else -1)[:5]
            if not targets:
                raise HTTPException(422, "Mark course topics as taught before requesting a learning plan")
            paths.append(public(enqueue(conn, course, student_id, [c["id"] for c in targets], actor["id"], records)))
        return {"paths": paths}
