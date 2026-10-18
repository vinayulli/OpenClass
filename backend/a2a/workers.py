"""Durable dispatch, bounded model workers and retrying webhook delivery."""
import asyncio
import hashlib
import json
import logging
import time
import httpx
from ..store import db, get, put, audit, now
from .config import agent_url, shared_secret, concurrency
from .protocol import send_request
from .state import claim_job, claim_task, finish_task, TERMINAL

logger = logging.getLogger("openclass.a2a")


async def workload_headers(headers):
    from ..security.identity import managed
    if managed():
        from ..security.transport import workload_token
        headers["X-OpenClass-Workload-Token"] = await asyncio.to_thread(workload_token)
    return headers


def dispatch_result(job_id, success):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("a2a:"+job_id,))
        job = get(conn, "job", job_id)
        if job["status"] != "dispatching":
            return
        if success:
            job.update(status="submitted", a2a_task_id=job_id, lease_until=0)
        elif job["dispatch_attempts"] >= 5:
            job.update(status="failed", error="A2A service could not accept this job after five delivery attempts.")
        else:
            job.update(status="queued", lease_until=time.time()+min(60, 2**job["dispatch_attempts"]))
        put(conn, "job", job)


async def dispatch_once():
    job = await asyncio.to_thread(claim_job)
    if not job:
        return False
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(agent_url(), json=send_request(job["id"]).model_dump(mode="json", by_alias=True, exclude_none=True), headers=await workload_headers({"Authorization": "Bearer "+shared_secret()}))
            response.raise_for_status()
            if response.json().get("error") or response.json().get("result", {}).get("id") != job["id"]:
                raise ValueError("A2A acceptance failed")
        success = True
    except Exception as error:
        logger.warning("a2a_dispatch_failed job=%s type=%s", job["id"], type(error).__name__)
        success = False
    await asyncio.to_thread(dispatch_result, job["id"], success)
    return True


def generation_context(job_id):
    from ..services import course_access
    from ..learning import learning_twin
    with db() as conn:
        job = get(conn, "job", job_id)
        actor = get(conn, "user", job["user_id"])
        course = course_access(conn, job["course_id"], actor)
        student_id = job.get("student_id")
        if actor["role"] != "teacher" or course["teacher_id"] != actor["id"] or student_id and student_id not in course["students"]:
            raise ValueError("Assessment scope no longer authorized")
        exam_id = hashlib.sha256(("a2a-exam:"+job_id).encode()).hexdigest()[:24]
        existing = get(conn, "exam", exam_id)
        twin = learning_twin(conn, course, student_id) if student_id and job.get("batch_mode") != "standard_variants" else None
        return job, course, twin, exam_id, existing


def save_draft(job, course, exam_id, output):
    from ..learning import validate_exam
    validate_exam(job["blueprint"], output["questions"], course)
    with db() as conn:
        if job.get("batch_mode") == "standard_variants":
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("variant-batch:"+job["batch_id"],))
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("a2a:"+job["id"],))
        item = get(conn, "a2a_task", "a2a:"+job["id"])
        if item["state"] in TERMINAL:
            return False
        if not get(conn, "exam", exam_id):
            if job.get("batch_mode") == "standard_variants":
                from ..store import all_of
                from ..assessment_variants import reject_repeated_questions
                siblings = [e for e in all_of(conn, "exam") if e.get("batch_id") == job["batch_id"]]
                reject_repeated_questions(output["questions"], siblings)
            put(conn, "exam", {"id": exam_id, "course_id": course["id"], "title": job["blueprint"]["title"], "blueprint": job["blueprint"], "questions": output["questions"], "status": "draft", "created_at": now(), "source": "Gemini assessment", "trace_id": job["id"], "batch_id": job.get("batch_id"), "variant": job.get("variant"), "assigned_student_ids": [job["student_id"]] if job.get("student_id") else []})
            audit(conn, job["user_id"], "exam.generated.a2a", exam_id)
        return True


def record_variant_failure(job_id):
    with db() as conn:
        job = get(conn, "job", job_id)
        job["error"] = "The generated variant repeated a question from another student in this batch. It was rejected; generate a replacement draft and review the variants."
        put(conn, "job", job)


def load_variant_context(job):
    if job.get("batch_mode") != "standard_variants":
        return {}
    from ..store import all_of
    with db() as conn:
        prompts = [q["prompt"] for exam in all_of(conn, "exam") if exam.get("batch_id") == job["batch_id"] for q in exam["questions"]]
    return {"variant": job["variant"], "avoid_question_prompts": prompts[:1000]}


async def generate_once():
    item = await asyncio.to_thread(claim_task)
    if not item:
        return False
    job_id = item["job_id"]
    try:
        if item["attempts"] > 3:
            raise RuntimeError("Task exhausted crash-recovery attempts")
        job, course, twin, exam_id, existing = await asyncio.to_thread(generation_context, job_id)
        if not existing:
            from ..agents import invoke
            # Each learner has an independent assessment session and lock. Ten
            # learners do not compete for one teacher-wide model conversation.
            variant_context = await asyncio.to_thread(load_variant_context, job)
            output = await asyncio.wait_for(invoke("exam", {**variant_context, "course": course, "blueprint": job["blueprint"], "learning_twin": twin, "teacher_request": job.get("teacher_request"), "_org_id": course["org"], "_course_id": course["id"]}, job.get("student_id") or job["user_id"]), timeout=120)
            if not await asyncio.to_thread(save_draft, job, course, exam_id, output):
                return True
        await asyncio.to_thread(finish_task, job_id, "completed", exam_id)
    except asyncio.CancelledError:
        raise  # Lease expires after process shutdown; persisted work can resume.
    except Exception as error:
        logger.warning("a2a_generation_failed job=%s type=%s code=%s", job_id, type(error).__name__, getattr(error, "code", "unavailable"))
        from ..assessment_variants import DuplicateVariantError
        if isinstance(error, DuplicateVariantError):
            await asyncio.to_thread(record_variant_failure, job_id)
        await asyncio.to_thread(finish_task, job_id, "failed")
    return True


def claim_delivery():
    with db() as conn:
        row = conn.execute("SELECT data FROM records WHERE kind='a2a_delivery' AND data::jsonb->>'status' IN ('pending','sending') AND (data::jsonb->>'next_at')::double precision<%s ORDER BY sequence FOR UPDATE SKIP LOCKED LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return None
        delivery = json.loads(row[0])
        delivery.update(status="sending", attempts=delivery["attempts"]+1, next_at=time.time()+30)
        put(conn, "a2a_delivery", delivery)
        return delivery


def delivered(delivery, success):
    with db() as conn:
        current = get(conn, "a2a_delivery", delivery["id"])
        current.update(status="delivered" if success else "failed" if current["attempts"] >= 8 else "pending", next_at=time.time()+min(300, 2**current["attempts"]), updated_at=now())
        put(conn, "a2a_delivery", current)
        if current["status"] == "failed":
            from ..notifications import notify
            job = get(conn, "job", current["job_id"])
            course = get(conn, "course", job["course_id"])
            job.update(status="callback_failed", error="Agent finished but webhook delivery needs a retry.")
            put(conn, "job", job)
            notify(conn, course, [job["user_id"]], "a2a.callback_failed", "Agent callback needs attention", job["error"], "job", job["id"])


async def deliver_once():
    delivery = await asyncio.to_thread(claim_delivery)
    if not delivery:
        return False
    push = delivery["push"]
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(push["url"], json=delivery["payload"], headers=await workload_headers({"Authorization": "Bearer "+push["authentication"]["credentials"], "X-A2A-Notification-Token": push["token"]}))
            response.raise_for_status()
        success = True
    except Exception as error:
        logger.warning("a2a_callback_failed job=%s type=%s", delivery["job_id"], type(error).__name__)
        success = False
    await asyncio.to_thread(delivered, delivery, success)
    return True


async def loop(operation):
    while True:
        try:
            worked = await operation()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("a2a_worker_failed operation=%s type=%s", operation.__name__, type(error).__name__)
            worked = False
        await asyncio.sleep(.2 if worked else 5)


def start_workers():
    operations = [dispatch_once, deliver_once]+[generate_once]*concurrency()
    return [asyncio.create_task(loop(operation), name="a2a:"+operation.__name__) for operation in operations]
