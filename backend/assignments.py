"""Typed assignment records and durable, leased repository review processing."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, Field
from fastapi import HTTPException
from .store import db, get, put, now, uid, audit
from .services import course_access, ai_call

logger = logging.getLogger(__name__)


class AssignmentRecord(BaseModel):
    id: str
    course_id: str
    org: str
    teacher_id: str
    title: str
    instructions: str
    concept_ids: list[str]
    student_ids: list[str] = Field(default_factory=list)
    status: Literal["published"] = "published"
    created_at: str
    schema_version: int = 1


class SubmissionRecord(BaseModel):
    id: str
    assignment_id: str
    course_id: str
    org: str
    student_id: str
    url: str
    status: Literal["queued", "processing", "teacher_review_required", "failed"] = "queued"
    created_at: str
    updated_at: str
    attempt_number: int
    review_id: str | None = None
    error: str | None = None
    lease_until: str | None = None
    schema_version: int = 1


def accessible_assignment(conn, course_id, assignment_id, actor):
    course = course_access(conn, course_id, actor)
    item = get(conn, "coding_assignment", assignment_id)
    if not item or item["course_id"] != course_id or item.get("student_ids") and actor["id"] not in item["student_ids"]:
        raise HTTPException(404, "Assignment not found")
    return course, item


def claim():
    with db() as conn:
        row = conn.execute("SELECT data FROM records WHERE kind='assignment_submission' AND (data::jsonb->>'status'='queued' OR (data::jsonb->>'status'='processing' AND data::jsonb->>'lease_until'<%s)) ORDER BY sequence FOR UPDATE SKIP LOCKED LIMIT 1", (now(),)).fetchone()
        if not row:
            return None
        import json
        item = json.loads(row[0])
        # Expired reviews are surfaced for explicit retry; do not repeat model spend automatically.
        if item["status"] == "processing":
            item.update(status="failed", error="Review interrupted or exceeded its processing lease. Retry the review.", lease_until=None, updated_at=now())
            put(conn, "assignment_submission", item)
            return None
        item.update(status="processing", updated_at=now(), lease_until=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat())
        return put(conn, "assignment_submission", item)


def context(item):
    with db() as conn:
        actor = get(conn, "user", item["student_id"])
        if not actor or actor["org"] != item["org"]:
            raise HTTPException(404)
        course, assignment = accessible_assignment(conn, item["course_id"], item["assignment_id"], actor)
        return actor, course, assignment


def finish(item, course, report=None, repository=None, error=None):
    from .notifications import notify
    with db() as conn:
        conn.execute("SELECT data FROM records WHERE id=%s FOR UPDATE", (item["id"],))
        current = get(conn, "assignment_submission", item["id"])
        if current["status"] != "processing" or current["lease_until"] != item["lease_until"]:
            return
        if error:
            current.update(status="failed", error=error)
            if course:
                notify(conn, course, [item["student_id"]], "coding_review.failed", "Assignment review needs attention", error, "assignment", item["assignment_id"])
        else:
            review_id = "review:"+item["id"]
            put(conn, "code_review", {"id": review_id, "submission_id": item["id"], "assignment_id": item["assignment_id"], "course_id": item["course_id"], "student_id": item["student_id"], "url": item["url"], "report": report, "scope": repository["scope"], "status": "teacher_review_required", "created_at": now()})
            current.update(status="teacher_review_required", review_id=review_id, error=None)
            notify(conn, course, [item["student_id"], course["teacher_id"]], "coding_report.ready", "Coding assessment ready", "Your assignment report is ready. The rating is provisional and requires educator review.", "code_review", review_id)
        current.update(updated_at=now(), lease_until=None)
        put(conn, "assignment_submission", current)


async def process(item):
    from .repositories import inspect_for_actor
    course = None
    try:
        actor, course, assignment = await asyncio.to_thread(context, item)
        repository = await asyncio.wait_for(inspect_for_actor(item["url"], actor, course["id"]), timeout=90)
        agent_context = {"_course_id": course["id"], "concepts": course["concepts"], "assignment": assignment, "repository": repository}
        from .security.identity import managed
        if managed():
            from .cloud.capabilities import issue
            agent_context["_github_context"] = issue(actor, course["id"], actor["id"], agent="code", service="github", resources={"repository_url": item["url"]})
        report = await ai_call("code", agent_context, actor)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning("assignment_review_failed submission=%s type=%s", item["id"], type(error).__name__)
        message = error.detail if isinstance(error, HTTPException) and isinstance(error.detail, str) else "Repository review failed. Check that the GitHub repository is public and contains supported source files, then retry."
        await asyncio.to_thread(finish, item, course, error=message)
    else:
        await asyncio.to_thread(finish, item, course, report, repository)


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
            logger.exception("assignment_worker_failed")
            await asyncio.sleep(5)
