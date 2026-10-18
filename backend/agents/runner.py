"""Run scoped dynamic workflows; application services control persistence."""
import asyncio
import json
import logging
import os
import time
from . import assessment_generator as assessment, coding_agent as coding, intervention_planner as intervention, classroom_advisor as teacher, learning_coach as tutor, web_research
from .policy import POLICY
from . import learning_path
from ..cloud.config import enabled, validate_governance

REGISTRY = {"exam": assessment, "intervention": intervention, "code": coding, "tutor": tutor, "teacher": teacher, "web": web_research, "path": learning_path}
logger = logging.getLogger("openclass.agents")


def configured():
    return bool(os.getenv("GEMINI_API_KEY")) or enabled("GOOGLE_GENAI_USE_VERTEXAI")


def build_reasoner(kind, context_token=None, runtime=None):
    from google.adk.agents import Agent
    from google.genai import types
    specialist = REGISTRY[kind]
    from .schema_transport import wire_schema
    tools = []
    if runtime and kind == "teacher":
        from .classroom_advisor.tools import build_tools
        tools = build_tools(runtime)
    elif runtime and kind == "tutor":
        from .learning_coach.tools import build_tools
        tools = build_tools(runtime)
    elif kind == "web":
        from google.adk.tools import google_search
        tools = [google_search]
    # The workflow passes current authorized context plus six conversation turns.
    # Do not replay every historical classroom snapshot into each model call.
    return Agent(name=specialist.NAME, model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"), instruction=POLICY+"\n"+specialist.INSTRUCTION, output_schema=wire_schema(specialist.SCHEMA), tools=tools, include_contents="none", generate_content_config=types.GenerateContentConfig())


def build_agent(kind, context_token=None, runtime=None, context=None, result_sink=None):
    """Public entry points are workflows; LLM agents are internal reasoning nodes."""
    from importlib import import_module
    factory = import_module(REGISTRY[kind].__name__+".workflow").build
    return factory(build_reasoner(kind, context_token, runtime), context or {}, runtime, result_sink if result_sink is not None else {})


async def invoke(kind, context, user_id):
    from ..security.policy import current_agent, allow_call
    allow_call(current_agent.get(), kind)
    from ..security.identity import managed
    if managed() and os.getenv("OPENCLASS_AGENT_EXECUTION") != "managed":
        raise RuntimeError("Managed governance requires separate specialist runtime execution")
    if os.getenv("OPENCLASS_AGENT_EXECUTION", "local") == "managed":
        from ..runtime.client import invoke_remote
        return await invoke_remote(kind, context, user_id)
    return await invoke_local(kind, context, user_id)


async def invoke_local(kind, context, user_id):
    if not configured():
        raise RuntimeError("Add GEMINI_API_KEY to the backend .env and restart to enable Gemini agents")
    from google.adk.runners import Runner
    from google.adk.agents.run_config import RunConfig
    from google.genai import types
    validate_governance()
    if not enabled("GOOGLE_GENAI_USE_VERTEXAI"):
        # ADK's Gemini client reads GEMINI_API_KEY directly. Remove the competing
        # SDK variable so a stale inherited key cannot take precedence.
        os.environ.pop("GOOGLE_API_KEY", None)
    context = dict(context)
    context_token = context.pop("_mcp_context", None)
    runtime = context.pop("_tool_runtime", None)
    if runtime and context_token:
        runtime["data_scope_token"] = context_token
    from .sessions import session_key, session_service
    from ..security.identity import managed
    org_id = context.pop("_org_id", None) or context.get("course", {}).get("org", "standalone-evaluation")
    course_id = context.pop("_course_id", None) or context.get("course", {}).get("id", "standalone-evaluation")
    session_id = session_key(org_id, course_id, user_id, kind, context.pop("_conversation_id", None))
    from .learning_coach.dispatch import progress_summary
    from .classroom_advisor.dispatch import quick_blueprints
    deterministic = (kind == "tutor" and progress_summary(context) is not None) or (kind == "teacher" and bool(quick_blueprints(context, runtime)))
    interactive = kind == "web" or (kind in {"tutor", "teacher"} and not enabled("ADK_PERSIST_INTERACTIVE_CHECKPOINTS"))
    if deterministic or interactive or managed():
        # Interactive prompts already include recent PostgreSQL chat records.
        # Avoid duplicating each graph checkpoint across a high-latency SQL
        # link. Final replies/session IDs remain durable; A2A jobs own the
        # durable long-running task lifecycle. Full checkpoints are opt-in.
        from google.adk.sessions import InMemorySessionService
        service = InMemorySessionService()
    else:
        service = await asyncio.to_thread(session_service)
    result_sink = {}
    runner = Runner(agent=build_agent(kind, context_token, runtime, context, result_sink), app_name="openclass", session_service=service)
    started = time.monotonic()
    from ..security.policy import current_agent
    identity_token = current_agent.set(kind)
    async def run():
        session = await service.get_session(app_name="openclass", user_id=user_id, session_id=session_id)
        if session is None:
            session = await service.create_session(app_name="openclass", user_id=user_id, session_id=session_id)
        sources = []
        async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text=json.dumps(context))]), run_config=RunConfig(max_llm_calls=6)):
            grounding = getattr(event, "grounding_metadata", None)
            for chunk in getattr(grounding, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", "")
                if uri.startswith("https://"):
                    sources.append({"title": getattr(web, "title", None) or uri, "url": uri})
        if "result" not in result_sink:
            raise ValueError("Workflow did not complete validation")
        schema = REGISTRY[kind].SCHEMA
        validated = result_sink["result"]
        return validated if schema else {**validated, "session_id": session_id, "actions": runtime["actions"] if runtime else [], "sources": sources+(runtime["sources"] if runtime else []), "workflow_branch": result_sink["branch"]}
    try:
        if kind == "web" or managed():
            # Public research has no application database credential or learner
            # tools. Its ephemeral session needs no PostgreSQL advisory lock.
            return await asyncio.wait_for(run(), timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "90")))
        # Serialize one conversation across requests/processes without blocking the event loop.
        from ..store import db
        with db() as connection:
            acquired = connection.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (session_id,)).fetchone()[0]
            if not acquired:
                raise RuntimeError("This learner agent session is busy. Retry after the current response.")
            try:
                return await asyncio.wait_for(run(), timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "90")))
            finally:
                connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", (session_id,))
    finally:
        logger.info("agent kind=%s duration_ms=%.0f", kind, (time.monotonic()-started)*1000)
        try:
            await runner.close()
        finally:
            current_agent.reset(identity_token)
