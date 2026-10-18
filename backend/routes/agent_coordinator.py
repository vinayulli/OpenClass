"""Authenticated specialist-to-coordinator mutations; never browser tool execution."""
import asyncio
import hashlib
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from backend.security.identity import caller_from_headers
from backend.security.policy import allow_call
from backend.runtime.tickets import verify

router = APIRouter()


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant: str
    context: dict
    name: str
    arguments: dict


def authorized_runtime(body, caller):
    import jwt
    from backend.store import db, get
    from backend.services import course_access
    # Unverified sub is used only as an input to full signature/digest validation.
    subject = jwt.decode(body.grant, options={"verify_signature": False}).get("sub")
    verify(body.grant, caller, body.context, subject, "api")
    original = body.context["_tool_runtime"]
    with db() as conn:
        actor = get(conn, "user", subject)
        course_access(conn, original["course_id"], actor)
    if not actor or actor["role"] != ("teacher" if caller == "teacher" else "student"):
        raise PermissionError("Account role no longer authorizes this action")
    from backend.agents.coordinator.service import allows_test_request
    latest = original["latest_message"]
    return {"actor": actor, "course_id": original["course_id"], "latest_message": latest,
            "allow_test_generation": caller == "teacher" and allows_test_request(latest),
            "actions": [], "sources": [], "force_local_coordinator": True}


def claim_action(identifier):
    from backend.store import db, get, now
    with db() as conn:
        inserted = conn.execute("INSERT INTO records(id,kind,data) VALUES(%s,'agent_action',%s) ON CONFLICT(id) DO NOTHING RETURNING id", (identifier, json.dumps({"id": identifier, "status": "running", "created_at": now()}))).fetchone()
        return None if inserted else get(conn, "agent_action", identifier)


def complete_action(identifier, result=None):
    from backend.store import db, put, now
    with db() as conn:
        put(conn, "agent_action", {"id": identifier, "status": "ready" if result is not None else "failed", "result": result, "updated_at": now()})


@router.post("/api/internal/agent-actions")
async def action(body: ActionRequest, request: Request):
    try:
        caller = await asyncio.to_thread(caller_from_headers, request.headers)
        allow_call(caller, "coordinator")
        if caller not in {"teacher", "tutor"}:
            raise PermissionError()
        runtime = await asyncio.to_thread(authorized_runtime, body, caller)
    except Exception as error:
        # Exception type distinguishes expired grants, identity failures and
        # scope violations without leaking assertions or learner context.
        logging.getLogger("openclass.coordinator").warning("coordinator_authorization_failed type=%s", type(error).__name__)
        raise HTTPException(403, "Verified specialist and authorized execution grant required") from None
    allowed = {"teacher": {"request_student_test", "request_student_tests", "request_class_test_variants", "start_assessment"}, "tutor": {"request_practice_test"}}
    if body.name not in allowed[caller]:
        raise HTTPException(403, "Coordinator action is not allowed")
    identifier = "agent-action:"+hashlib.sha256((body.grant+body.name+json.dumps(body.arguments, sort_keys=True)).encode()).hexdigest()
    previous = await asyncio.to_thread(claim_action, identifier)
    if previous:
        if previous["status"] == "ready":
            return previous["result"]
        raise HTTPException(409, "This action is running or requires reconciliation; it will not be duplicated")
    try:
        if body.name == "start_assessment":
            from backend.agents.classroom_advisor.dispatch import quick_blueprints, start_assessment
            expected = quick_blueprints(body.context, runtime)
            if not expected or expected != body.arguments.get("blueprint"):
                raise HTTPException(403, "Assessment shortcut does not match the signed request")
            result = {"message": await start_assessment(expected, runtime), "actions": runtime["actions"]}
        else:
            if caller == "teacher":
                from backend.agents.classroom_advisor.tools import build_tools
            else:
                from backend.agents.learning_coach.tools import build_tools
            tool = next(tool for tool in build_tools(runtime) if tool.__name__ == body.name)
            result = await tool(**body.arguments)
        await asyncio.to_thread(complete_action, identifier, result)
        return result
    except BaseException:
        await asyncio.to_thread(complete_action, identifier)
        raise
