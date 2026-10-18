from fastapi import APIRouter, Depends, Header, HTTPException
from ..schemas import AssessmentBatch
from ..services import teacher, course_access
from ..store import db, get, all_of, put

router = APIRouter()


@router.post("/api/courses/{course_id}/assessment-batches", status_code=202)
async def create_batch(course_id: str, body: AssessmentBatch, current=Depends(teacher), idempotency_key: str | None = Header(default=None)):
    from ..agents.coordinator.service import queue_batch_assessments
    from ..cloud.model_armor import inspect
    if idempotency_key and len(idempotency_key) > 160:
        raise HTTPException(422, "Idempotency key too long")
    await inspect(body.teacher_request)
    result = await queue_batch_assessments(course_id, current, body.student_ids, body.blueprint.model_dump() if body.blueprint else None, body.teacher_request, idempotency_key)
    return {"id": result["id"], "status": "queued", "student_count": len(result["jobs"]), "job_ids": result["job_ids"]}


@router.get("/api/assessment-batches/{batch_id}")
def batch_status(batch_id: str, current=Depends(teacher)):
    with db() as conn:
        batch = get(conn, "assessment_batch", batch_id)
        if not batch or batch["user_id"] != current["id"]:
            raise HTTPException(404)
        course_access(conn, batch["course_id"], current)
        wanted = set(batch["job_ids"])
        jobs = [j for j in all_of(conn, "job") if j["id"] in wanted]
        complete = sum(j["status"] == "completed" for j in jobs)
        failed = sum(j["status"] in {"failed", "canceled", "callback_failed"} for j in jobs)
        return {"id": batch_id, "course_id": batch["course_id"], "status": "completed" if complete == len(wanted) else "finished_with_errors" if complete+failed == len(wanted) else "running", "total": len(wanted), "completed": complete, "failed": failed, "jobs": [{k: j.get(k) for k in ("id", "student_id", "status", "exam_id", "error", "callback_received", "started_at", "completed_at")} for j in jobs]}


@router.post("/api/jobs/{job_id}/retry-webhook")
def retry_webhook(job_id: str, current=Depends(teacher)):
    with db() as conn:
        job = get(conn, "job", job_id)
        if not job or job["user_id"] != current["id"]:
            raise HTTPException(404)
        course_access(conn, job["course_id"], current)
        count = 0
        for delivery in all_of(conn, "a2a_delivery"):
            if delivery["job_id"] == job_id and delivery["status"] == "failed":
                delivery.update(status="pending", attempts=0, next_at=0)
                put(conn, "a2a_delivery", delivery)
                count += 1
        if count:
            job["status"] = "awaiting_callback"
            put(conn, "job", job)
        return {"queued": count}
