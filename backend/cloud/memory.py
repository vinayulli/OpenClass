"""GEAP Memory Bank with immutable server-derived learner/course scopes."""
import asyncio
import hashlib
import json
import logging
from .config import enabled, required


def scope(org_id, course_id, student_id):
    if not all((org_id, course_id, student_id)):
        raise ValueError("Memory scope requires organization, course and learner")
    # Fixed tuple encoding prevents ambiguous concatenations and keeps PII out of scope IDs.
    import json
    digest = lambda parts: hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()
    return {"app_name": "openclass_"+digest([org_id, course_id])[:32], "user_id": "learner_"+digest([org_id, student_id])[:32]}


def service():
    if not enabled("GEAP_MEMORY_ENABLED"):
        raise RuntimeError("GEAP Memory Bank is disabled; enable it and configure the Memory Bank resource")
    from google.adk.memory import VertexAiMemoryBankService
    return VertexAiMemoryBankService(project=required("GOOGLE_CLOUD_PROJECT"), location=required("GOOGLE_CLOUD_LOCATION"), agent_engine_id=required("GEAP_MEMORY_BANK_ID"))


async def retrieve(org_id, course_id, student_id, query):
    bank = await asyncio.to_thread(service)
    response = await asyncio.wait_for(bank.search_memory(**scope(org_id, course_id, student_id), query=query), timeout=30)
    return ["".join(part.text or "" for part in entry.content.parts) for entry in response.memories[:8]]


async def retrieve_for_chat(org_id, course_id, student_id, query):
    """Memory is optional context; a slow bank must not block evidence-based chat."""
    if not enabled("GEAP_MEMORY_ENABLED"):
        return {"status": "disabled", "memories": []}
    try:
        facts = await asyncio.wait_for(retrieve(org_id, course_id, student_id, query), timeout=12)
    except Exception as error:
        logging.getLogger("openclass.memory").warning("chat_memory_unavailable type=%s code=%s", type(error).__name__, getattr(error, "code", "unavailable"))
        return {"status": "unavailable", "memories": [], "note": "Managed memory was unavailable. Answer from the supplied course evidence, disclose this limitation, and do not retry memory in this response."}
    # Inspection happens outside the availability fallback: blocked content never
    # becomes an uninspected fallback response.
    from .model_armor import inspect
    if facts:
        await inspect(json.dumps(facts))
    return {"status": "available", "memories": facts}


async def remember(org_id, course_id, student_id, fact):
    """Generate memories from approved evidence summaries, never raw answer keys."""
    from google.adk.events import Event
    from google.adk.sessions import Session
    from google.genai import types
    from .model_armor import inspect
    await inspect(fact)
    s = scope(org_id, course_id, student_id)
    session = Session(id=hashlib.sha256(fact.encode()).hexdigest()[:32], **s, events=[Event(author="user", content=types.Content(role="user", parts=[types.Part(text=fact)]))])
    bank = await asyncio.to_thread(service)
    await asyncio.wait_for(bank.add_session_to_memory(session), timeout=60)
