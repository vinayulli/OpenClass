"""PostgreSQL task leases and callback outbox; no model work inside a transaction."""
import hashlib
import json
import time
from ..store import db, get, put, now
from .config import concurrency
from .protocol import task_document

TERMINAL = {"completed", "failed", "canceled", "rejected"}


def accept_task(job_id, push):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("a2a:"+job_id,))
        job = get(conn, "job", job_id)
        if not job or job.get("transport") != "a2a":
            raise ValueError("Unknown A2A assessment job")
        existing = get(conn, "a2a_task", "a2a:"+job_id)
        if existing:
            return existing["task"]
        task = task_document(job, "submitted")
        put(conn, "a2a_task", {"id": "a2a:"+job_id, "job_id": job_id, "task": task, "state": "submitted", "attempts": 0, "lease_until": 0, "push": push, "created_at": now()})
        return task


def claim_job():
    with db() as conn:
        row = conn.execute("SELECT data FROM records WHERE kind='job' AND data::jsonb->>'transport'='a2a' AND data::jsonb->>'status' IN ('queued','dispatching') AND COALESCE((data::jsonb->>'lease_until')::double precision,0)<%s ORDER BY sequence FOR UPDATE SKIP LOCKED LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return None
        job = json.loads(row[0])
        job.update(status="dispatching", lease_until=time.time()+60, dispatch_attempts=job.get("dispatch_attempts", 0)+1)
        put(conn, "job", job)
        return job


def claim_task():
    with db() as conn:
        pending = conn.execute("SELECT 1 FROM records WHERE kind='a2a_task' AND data::jsonb->>'state' IN ('submitted','working') AND COALESCE((data::jsonb->>'lease_until')::double precision,0)<%s LIMIT 1", (time.time(),)).fetchone()
        if not pending:
            return None
        conn.execute("SELECT pg_advisory_xact_lock(7812410)")
        active = conn.execute("SELECT count(*) FROM records WHERE kind='a2a_task' AND data::jsonb->>'state'='working' AND (data::jsonb->>'lease_until')::double precision>%s", (time.time(),)).fetchone()[0]
        if active >= concurrency():
            return None
        row = conn.execute("SELECT data FROM records WHERE kind='a2a_task' AND data::jsonb->>'state' IN ('submitted','working') AND COALESCE((data::jsonb->>'lease_until')::double precision,0)<%s ORDER BY sequence FOR UPDATE SKIP LOCKED LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return None
        item = json.loads(row[0])
        job = get(conn, "job", item["job_id"])
        item.update(state="working", attempts=item["attempts"]+1, lease_until=time.time()+180, started_at=item.get("started_at") or now())
        item["task"] = task_document(job, "working")
        put(conn, "a2a_task", item)
        job.update(status="running", a2a_task_id=job["id"], started_at=item["started_at"])
        put(conn, "job", job)
        return item


def finish_task(job_id, state, exam_id=None):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("a2a:"+job_id,))
        item = get(conn, "a2a_task", "a2a:"+job_id)
        if item["state"] in TERMINAL:
            return item["task"]
        job = get(conn, "job", job_id)
        item.update(state=state, lease_until=0, task=task_document(job, state, exam_id), finished_at=now())
        put(conn, "a2a_task", item)
        job.update(status="awaiting_callback", a2a_task_id=job_id)
        put(conn, "job", job)
        put(conn, "a2a_delivery", {"id": "delivery:"+job_id+":"+state, "job_id": job_id, "payload": item["task"], "status": "pending", "attempts": 0, "next_at": 0, "push": item["push"]})
        return item["task"]


def receive_callback(task):
    """Replay-safe completion: callback must match the persisted service result."""
    job_id = task["id"]
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("a2a:"+job_id,))
        item = get(conn, "a2a_task", "a2a:"+job_id)
        if not item or item["state"] not in TERMINAL or item["task"] != task:
            raise ValueError("Callback does not match the persisted terminal task")
        job = get(conn, "job", job_id)
        if job.get("callback_received"):
            return {"ok": True, "duplicate": True}
        exam_id = None
        for artifact in task.get("artifacts", []):
            for part in artifact["parts"]:
                if part.get("kind") == "data":
                    exam_id = part["data"].get("exam_id")
        job.update(status="completed" if item["state"] == "completed" else "failed", completed_at=now(), callback_received=True)
        if exam_id:
            job["exam_id"] = exam_id
        else:
            job["error"] = job.get("error") or "Assessment task failed or was canceled. Review agent logs and retry."
        put(conn, "job", job)
        from ..notifications import notify
        course = get(conn, "course", job["course_id"])
        notify(conn, course, [job["user_id"]], "assessment.ready" if exam_id else "assessment.failed", "Assessment draft ready" if exam_id else "Assessment task failed", "The Assessment Generator reported completion through its webhook. Review the draft before publishing." if exam_id else job["error"], "exam" if exam_id else "job", exam_id or job_id)
        return {"ok": True, "duplicate": False}
