"""Durable private practice and learning-path generation worker."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from .store import db, get, put, now
from .services import ai_call
from .learning import learning_twin
from .routes.self_study import access

logger = logging.getLogger(__name__)


def claim():
    with db() as conn:
        row = conn.execute("SELECT data FROM records WHERE kind='self_study' AND (data::jsonb->>'status'='queued' OR (data::jsonb->>'status'='processing' AND data::jsonb->>'lease_until'<%s)) ORDER BY sequence FOR UPDATE SKIP LOCKED LIMIT 1", (now(),)).fetchone()
        if not row:
            return None
        item = json.loads(row[0])
        if item["status"] == "processing":
            item.update(status="failed", error="Generation was interrupted. Create a new request.", updated_at=now(), lease_until=None)
            put(conn, "self_study", item)
            return None
        item.update(status="processing", lease_until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(), updated_at=now())
        return put(conn, "self_study", item)


def load(item):
    with db() as conn:
        actor = get(conn, "user", item["student_id"])
        if not actor or actor["org"] != item["org"]:
            raise ValueError("Student unavailable")
        course = access(conn, item["course_id"], actor)
        twin = learning_twin(conn, course, actor["id"])
    return actor, course, twin


def finish(item, output=None, error=None):
    with db() as conn:
        conn.execute("SELECT data FROM records WHERE id=%s FOR UPDATE", (item["id"],))
        current = get(conn, "self_study", item["id"])
        if current["status"] != "processing" or current["lease_until"] != item["lease_until"]:
            return
        current.update(status="failed" if error else "completed", output=output, error=error, updated_at=now(), lease_until=None)
        put(conn, "self_study", current)
        # No teacher notifications, audit records or official assessment/evidence writes.
        from .notifications import notify
        course = get(conn, "course", item["course_id"])
        if course:
            notify(conn, course, [item["student_id"]], "self_study.finished", "Private self-study update", "Generation failed. Open your self-study workspace to retry." if error else "Your private practice test or learning path is ready.", "self_study", item["id"])


async def process(item):
    try:
        actor, course, twin = await asyncio.to_thread(load, item)
        request = item["request"]
        if item["type"] == "practice":
            blueprint = {"title": "Private topic practice", "kind": "practice", "concept_ids": request["concept_ids"], "question_count": request["question_count"], "total_marks": request["question_count"]*2, "duration_minutes": 20, "difficulty": "beginner", "question_types": ["mcq"], "release_feedback": True, "student_id": actor["id"]}
            output = await ai_call("exam", {"course": course, "blueprint": blueprint, "twin": twin, "_course_id": course["id"]}, actor)
        else:
            from .learning_paths import feedback_context
            def load_feedback():
                with db() as conn:
                    previous = get(conn, "self_study", item["previous_path_id"]) if item.get("previous_path_id") else None
                    return feedback_context(conn, item), previous.get("output") if previous else None
            feedback, previous_path = await asyncio.to_thread(load_feedback)
            from .learning_resources import for_course
            resources = for_course(course)
            output = await ai_call("path", {"course": course, "twin": twin, "concept_ids": request["concept_ids"], "learning_resources": resources, "student_feedback": feedback, "previous_path": previous_path, "previous_path_id": item.get("previous_path_id"), "_course_id": course["id"]}, actor)
            output["reference_catalog"] = resources
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning("self_study_failed id=%s type=%s", item["id"], type(error).__name__)
        await asyncio.to_thread(finish, item, error="Generation could not complete. Check course materials and model availability, then create a new request.")
    else:
        await asyncio.to_thread(finish, item, output)


async def worker():
    while True:
        try:
            item = await asyncio.to_thread(claim)
            if item:
                await process(item)
            else:
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("self_study_worker_failed")
            await asyncio.sleep(5)
