"""Durable memory synchronization. Submitted learning evidence commits before remote calls."""
import asyncio
import logging
from .config import enabled
from .memory import remember
from ..store import all_of, db, get, now, put, uid

logger = logging.getLogger("openclass.memory")


def enqueue(conn, org_id, course_id, student_id, source_id, summary):
    key = "memory:" + source_id
    # Each source has one outbox record; updates are retried without discarding evidence.
    return put(conn, "memory_outbox", {"id": key, "org_id": org_id, "course_id": course_id, "student_id": student_id, "source_id": source_id, "summary": summary, "status": "pending", "attempts": 0, "updated_at": now()})


async def sync_one():
    with db() as conn:
        # MVP runs one worker. A transaction lock serializes claiming across processes.
        conn.execute("SELECT pg_advisory_xact_lock(7812405)")
        items = [i for i in all_of(conn, "memory_outbox") if i["status"] == "pending" and i["attempts"] < 3]
        if not items:
            return
        item = items[0]
        item.update(status="processing", attempts=item["attempts"]+1)
        put(conn, "memory_outbox", item)
    try:
        await remember(item["org_id"], item["course_id"], item["student_id"], item["summary"])
        status = "synced"
    except Exception as error:
        logger.warning("memory_sync_failed source=%s type=%s", item["source_id"], type(error).__name__)
        status = "failed" if item["attempts"] >= 3 else "pending"
    with db() as conn:
        current = get(conn, "memory_outbox", item["id"])
        if current and current["updated_at"] == item["updated_at"]:
            current.update(status=status, completed_at=now() if status == "synced" else None)
            put(conn, "memory_outbox", current)
            if status in ("synced", "failed"):
                from ..notifications import notify
                course = get(conn, "course", item["course_id"])
                if course:
                    recipients = [item["student_id"]] if status == "synced" else [course["teacher_id"]]
                    notify(conn, course, recipients, "memory."+status, "Learner memory synchronized" if status == "synced" else "Learner memory sync needs attention", "The memory request was accepted; new facts may be eventually consistent." if status == "synced" else "A source summary exhausted its retries. Review managed memory configuration.", "memory", item["id"])


async def worker():
    while True:
        if enabled("GEAP_MEMORY_ENABLED"):
            try:
                await sync_one()
            except Exception as error:
                logger.warning("memory_worker_failed type=%s", type(error).__name__)
        await asyncio.sleep(3)
