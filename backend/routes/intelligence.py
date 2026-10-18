import os
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException
from ..learning import learning_twin
from ..repositories import inspect_for_actor
from ..schemas import Chat, RepoInput
from ..store import all_of, audit, db, get, now, put, uid
from ..services import user, teacher, course_access, ai_call, rate_limit

router = APIRouter()

async def run_chat(course_id: str, body: Chat, current, progress=None):
    question_at = now()
    started = time.monotonic()
    async def announce(stage, message):
        if progress:
            await progress(stage, message)
    await announce("records", "Reading your progress, assessment history and submitted assignments")
    rate_limit("ai:"+current["id"], 30, 3600)
    from ..chat_context import build_context, save_chat
    context = await asyncio.to_thread(build_context, course_id, body, current)
    if os.getenv("DATA_MCP_ENABLED", "false").lower() == "true":
        from ..cloud.capabilities import issue
        context["_mcp_context"] = issue(current, course_id, current["id"] if current["role"] == "student" else body.student_id)
    memory = None
    if current["role"] == "student":
        from ..cloud.memory import retrieve_for_chat
        from ..agents.learning_coach.dispatch import is_progress_request, is_rank_request
        if not (is_progress_request(body.message) or is_rank_request(body.message)):
            from ..cloud.config import enabled
            if enabled("GEAP_MEMORY_ENABLED"):
                await announce("memory", "Checking your course-scoped Memory Bank")
        memory = {"status": "not_requested", "memories": []} if (is_progress_request(body.message) or is_rank_request(body.message)) else await retrieve_for_chat(current["org"], course_id, current["id"], body.message)
        context["learner_memories"] = memory["memories"]
        context["memory_status"] = {k: v for k, v in memory.items() if k != "memories"}
    context["_course_id"] = course_id
    context["_conversation_id"] = body.conversation_id
    from ..agents.coordinator.service import allows_test_request
    context["_tool_runtime"] = {"actor": current, "course_id": course_id, "latest_message": body.message, "allow_test_generation": current["role"] == "teacher" and allows_test_request(body.message), "actions": [], "sources": [], "memory_lookup": memory}
    await announce("response", "Preparing an answer grounded in your course evidence")
    result = await ai_call("tutor" if current["role"] == "student" else "teacher", context, current)
    lookups = context["_tool_runtime"].get("learner_memory_lookups", {})
    statuses = [item["status"] for item in lookups.values()]
    result["memory_status"] = memory["status"] if memory else "unavailable" if "unavailable" in statuses else "available" if "available" in statuses else "disabled" if "disabled" in statuses else "not_requested"
    result["question_at"] = question_at
    result["response_at"] = now()
    result["duration_ms"] = round((time.monotonic()-started)*1000)
    await announce("saving", "Saving your conversation")
    await asyncio.to_thread(save_chat, {"id": uid(), "course_id": course_id, "user_id": current["id"], "session_id": result.get("session_id"), "conversation_id": body.conversation_id, "memory_status": result["memory_status"], "workflow_branch": result.get("workflow_branch"), "question": body.message, "response": result["message"], "actions": result.get("actions", []), "sources": result.get("sources", []), "question_at": question_at, "response_at": result["response_at"], "duration_ms": result["duration_ms"], "at": result["response_at"]})
    return result




@router.post("/api/courses/{course_id}/chat")
async def chat(course_id: str, body: Chat, current=Depends(user)):
    return await run_chat(course_id, body, current)


@router.post("/api/courses/{course_id}/chat/stream")
async def stream_chat(course_id: str, body: Chat, current=Depends(user)):
    from ..chat_stream import stream_response
    return stream_response(lambda progress: run_chat(course_id, body, current, progress))


@router.get("/api/courses/{course_id}/students/{student_id}/memories")
async def learner_memories(course_id: str, student_id: str, current=Depends(user)):
    with db() as conn:
        course = course_access(conn, course_id, current)
        if student_id not in course["students"] or (current["role"] == "student" and student_id != current["id"]):
            raise HTTPException(404)
        sync = [{k: item.get(k) for k in ("source_id", "status", "attempts", "updated_at")} for item in all_of(conn, "memory_outbox") if item["course_id"] == course_id and item["student_id"] == student_id]
    from ..cloud.config import enabled
    if not enabled("GEAP_MEMORY_ENABLED"):
        return {"provider": "disabled", "memories": [], "sync": sync}
    from ..cloud.memory import retrieve
    try:
        facts = await retrieve(current["org"], course_id, student_id, "Learning goals, learning preferences and demonstrated concept understanding")
        return {"provider": "GEAP Memory Bank", "memories": facts, "sync": sync}
    except Exception as error:
        raise HTTPException(503, "Managed learner memory is unavailable") from error


@router.get("/api/courses/{course_id}/chat")
def chat_history(course_id: str, conversation_id: str | None = None, current=Depends(user)):
    with db() as conn:
        course_access(conn, course_id, current)
        if conversation_id:
            from ..conversations import authorize
            authorize(conn, conversation_id, course_id, current)
        return [m for m in all_of(conn, "chat") if m["course_id"] == course_id and m["user_id"] == current["id"] and m.get("conversation_id") == conversation_id][-100:]


@router.post("/api/courses/{course_id}/students/{student_id}/interventions")
async def intervention(course_id: str, student_id: str, current=Depends(teacher)):
    rate_limit("ai:"+current["id"], 10, 3600)
    with db() as conn:
        course = course_access(conn, course_id, current)
        if student_id not in course["students"]:
            raise HTTPException(404)
        twin = learning_twin(conn, course, student_id)
    output = await ai_call("intervention", {"course": course, "twin": twin}, current)
    if output["concept_id"] not in {c["id"] for c in course["concepts"]}:
        raise HTTPException(502, "Intervention referenced an unknown concept")
    with db() as conn:
        result = put(conn, "intervention", {**output, "id": uid(), "course_id": course_id, "student_id": student_id, "status": "draft", "created_at": now()})
        from ..notifications import notify
        notify(conn, course, [current["id"]], "intervention.ready", "Learning plan draft ready", "Review the generated support plan before assigning it.", "intervention", result["id"])
        return result


@router.post("/api/interventions/{intervention_id}/assign")
def assign(intervention_id: str, current=Depends(teacher)):
    with db() as conn:
        item = get(conn, "intervention", intervention_id)
        if not item:
            raise HTTPException(404)
        course = course_access(conn, item["course_id"], current)
        item.update(status="assigned", assigned_at=now())
        audit(conn, current["id"], "intervention.assigned", intervention_id)
        from ..notifications import notify
        notify(conn, course, [item["student_id"]], "intervention.assigned", "New learning plan", "Your educator assigned a learning plan.", "intervention", intervention_id)
        return put(conn, "intervention", item)


@router.post("/api/courses/{course_id}/code-reviews")
async def code_review(course_id: str, body: RepoInput, current=Depends(user)):
    rate_limit("ai:"+current["id"], 10, 3600)
    with db() as conn:
        course = course_access(conn, course_id, current)
    try:
        repository = await inspect_for_actor(body.url, current, course_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Repository unavailable. Use a public GitHub repository and retry.") from error
    agent_context = {"concepts": course["concepts"], "repository": repository, "_course_id": course_id}
    from ..security.identity import managed
    if managed():
        from ..cloud.capabilities import issue
        agent_context["_github_context"] = issue(current, course_id, current["id"], agent="code", service="github", resources={"repository_url": body.url})
    output = await ai_call("code", agent_context, current)
    with db() as conn:
        audit(conn, current["id"], "repository.reviewed", course_id)
        result = put(conn, "code_review", {"id": uid(), "course_id": course_id, "student_id": current["id"], "report": output, "url": body.url, "scope": repository["scope"], "status": "teacher_review_required", "created_at": now()})
        from ..notifications import notify
        notify(conn, course, [current["id"], course["teacher_id"]], "coding_report.ready", "Coding report ready", "Source inspection completed. Review the provisional evidence and rating.", "code_review", result["id"])
        return result


@router.get("/api/courses/{course_id}/audit")
def audit_log(course_id: str, current=Depends(teacher)):
    with db() as conn:
        course_access(conn, course_id, current)
        targets = {course_id} | {r["id"] for kind in ("exam", "attempt", "intervention") for r in all_of(conn, kind) if r["course_id"] == course_id}
        return [a for a in all_of(conn, "audit") if a["target"] in targets][-100:]


@router.get("/api/courses/{course_id}/coach-sessions")
def coach_sessions(course_id: str, current=Depends(user)):
    with db() as conn:
        course_access(conn, course_id, current)
        items = [s for s in all_of(conn, "chat_session") if s["course_id"] == course_id and s["user_id"] == current["id"] and s["org"] == current["org"]]
        return sorted(items, key=lambda s: s["updated_at"], reverse=True)


@router.post("/api/courses/{course_id}/coach-sessions", status_code=201)
def new_coach_session(course_id: str, current=Depends(user)):
    rate_limit("sessions:"+current["id"], 60, 3600)
    from ..conversations import create
    with db() as conn:
        course_access(conn, course_id, current)
        return create(conn, course_id, current)
