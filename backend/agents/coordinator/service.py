"""Authorize and enqueue specialist work; never let model text publish an assessment."""
import asyncio
import re
from fastapi import HTTPException
from ...store import all_of, audit, db, now, put, uid


def allows_test_request(message):
    text = message.casefold()
    if re.search(r"\b(?:do not|don't|dont|never|without)\s+(?:\w+\s+){0,2}(?:generate|create|build|draft|prepare)", text):
        return False
    if re.search(r"\b(?:how|what happens|explain how)\b.{0,35}\b(?:generate|create|build|draft|prepare)\b", text):
        return False
    return bool(re.search(r"\b(?:generate|create|build|draft|prepare)\b", text) and re.search(r"\b(?:test|quiz|exam|assessment)\b", text))


def prepare_assessment(course, current, blueprint, teacher_request=None):
    from ...agents import configured
    from ...schemas import Blueprint
    from ...services import course_access
    from ...notifications import notify
    if not configured():
        raise HTTPException(503, "Configure Gemini before generating a test")
    blueprint = Blueprint.model_validate(blueprint).model_dump()
    with db() as conn:
        course = course_access(conn, course["id"], current)
        if current["role"] != "teacher" or course["teacher_id"] != current["id"]:
            raise HTTPException(403, "Educator access required")
        if not course["materials"] or not set(blueprint["concept_ids"]) <= {c["id"] for c in course["concepts"]}:
            raise HTTPException(422, "Use approved course materials and valid concept IDs")
        student_id = blueprint.get("student_id")
        if student_id and student_id not in course["students"]:
            raise HTTPException(404, "Learner not enrolled")
        twin = None
        job = put(conn, "job", {"id": uid(), "user_id": current["id"], "course_id": course["id"], "student_id": student_id, "status": "queued", "created_at": now(), "trigger": "classroom_advisor" if teacher_request else "test_studio", "transport": "a2a", "blueprint": blueprint, "teacher_request": teacher_request, "lease_until": 0})
        audit(conn, current["id"], "assessment.queued", job["id"])
        notify(conn, course, [current["id"]], "assessment.queued", "Assessment generation started", "The Assessment Generator is preparing a draft for review.", "job", job["id"])
    return job, course, blueprint, twin


def schedule(prepared, current, teacher_request):
    job, course, blueprint, twin = prepared
    # The durable A2A dispatcher claims this record; HTTP request lifetime does
    # not own the task, and restarting the API does not discard queued work.
    return job


def queue_assessment(course, current, blueprint, teacher_request=None):
    from ...services import rate_limit
    rate_limit("assessment-jobs:"+current["id"], 10, 3600)
    return schedule(prepare_assessment(course, current, blueprint, teacher_request), current, teacher_request)


async def queue_assessment_async(course, current, blueprint, teacher_request=None):
    from ...services import rate_limit
    rate_limit("assessment-jobs:"+current["id"], 10, 3600)
    prepared = await asyncio.to_thread(prepare_assessment, course, current, blueprint, teacher_request)
    return schedule(prepared, current, teacher_request)


def prepare_batch(course_id, current, student_ids, blueprint=None, teacher_request=None, idempotency_key=None):
    import hashlib
    import json
    from ...store import get
    from ...schemas import Blueprint
    from ...services import course_access
    from ...learning import classroom_twins
    from ..classroom_advisor.dispatch import personalized_blueprint
    from ...notifications import notify
    if not student_ids or len(student_ids) > 50 or len(set(student_ids)) != len(student_ids):
        raise HTTPException(422, "Select between 1 and 50 distinct enrolled learners")
    request_hash = hashlib.sha256(json.dumps([course_id, sorted(student_ids), blueprint, teacher_request], sort_keys=True).encode()).hexdigest()
    batch_id = hashlib.sha256(json.dumps([current["org"], current["id"], idempotency_key]).encode()).hexdigest()[:24] if idempotency_key else uid()
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("batch:"+batch_id,))
        course = course_access(conn, course_id, current)
        if current["role"] != "teacher" or course["teacher_id"] != current["id"]:
            raise HTTPException(403, "Educator access required")
        if not set(student_ids) <= set(course["students"]) or not course["materials"]:
            raise HTTPException(422, "Use enrolled learners and approved course materials")
        existing = get(conn, "assessment_batch", batch_id)
        if existing:
            if existing["request_hash"] != request_hash:
                raise HTTPException(409, "Idempotency key was already used for another batch")
            return {**existing, "jobs": [get(conn, "job", j) for j in existing["job_ids"]]}
        standard = bool(blueprint and blueprint.get("concept_ids"))
        twins = [None]*len(student_ids) if standard else classroom_twins(conn, course, student_ids)
        jobs = []
        for index, (student_id, twin) in enumerate(zip(student_ids, twins)):
            spec = {**blueprint, "student_id": None if blueprint.get("kind") == "formal" else student_id} if blueprint else personalized_blueprint(twin, student_id)
            if not spec.get("concept_ids"):
                spec["concept_ids"] = personalized_blueprint(twin, student_id)["concept_ids"][:spec.get("question_count", 5)]
            spec = Blueprint.model_validate(spec).model_dump()
            if not set(spec["concept_ids"]) <= {c["id"] for c in course["concepts"]}:
                raise HTTPException(422, "Unknown concept in batch blueprint")
            from ...assessment_variants import variant_spec
            variant = variant_spec(index, len(student_ids), batch_id) if standard else None
            jobs.append({"batch_mode": "standard_variants" if standard else "personalized", "variant": variant, "id": uid(), "user_id": current["id"], "course_id": course_id, "student_id": student_id, "batch_id": batch_id, "status": "queued", "transport": "a2a", "blueprint": spec, "teacher_request": teacher_request, "created_at": now(), "lease_until": 0, "trigger": "classroom_advisor_batch"})
        batch = {"mode": "standard_variants" if standard else "personalized", "id": batch_id, "user_id": current["id"], "course_id": course_id, "student_ids": student_ids, "job_ids": [j["id"] for j in jobs], "request_hash": request_hash, "created_at": now()}
        with conn.pipeline():
            for job in jobs:
                put(conn, "job", job)
            put(conn, "assessment_batch", batch)
            audit(conn, current["id"], "assessment.batch_queued", batch_id)
        notify(conn, course, [current["id"]], "assessment.batch_queued", "Assessment batch queued", f"{len(jobs)} individual assessment tasks were queued for bounded parallel generation.", "assessment_batch", batch_id)
        return {**batch, "jobs": jobs}


async def queue_batch_assessments(course_id, current, student_ids, blueprint=None, teacher_request=None, idempotency_key=None):
    from ...agents import configured
    from ...services import rate_limit
    if not configured():
        raise HTTPException(503, "Configure Gemini before generating assessments")
    rate_limit("assessment-batches:"+current["id"], 10, 3600)
    return await asyncio.to_thread(prepare_batch, course_id, current, student_ids, blueprint, teacher_request, idempotency_key)
