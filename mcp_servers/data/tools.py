"""Read-only database projections; no arbitrary SQL, mutations, or model-selected tenancy."""
import asyncio
from backend.store import db, get, many_of
from backend.services import course_access
from backend.learning import learning_twin, classroom_twins
from backend.cloud.model_armor import inspect
from mcp_servers.common.auth import require_tool


def authorize(tool, requested_student=None):
    claims = require_tool("data", tool)
    with db() as conn:
        actor = get(conn, "user", claims["sub"])
        if not actor or actor["org"] != claims["org"]:
            raise PermissionError("Unknown actor")
        course = course_access(conn, claims["course"], actor)
        if actor["role"] == "student":
            attempts = many_of(conn, ("attempt",))["attempt"]
            if any(a["course_id"] == course["id"] and a["student_id"] == actor["id"] and a["status"] == "in_progress" for a in attempts):
                raise PermissionError("Learning tools are paused during an active assessment")
    student = requested_student or (claims["student"] if claims["student"] != "*" else None)
    if claims["student"] != "*" and student != claims["student"]:
        raise PermissionError("Learner scope mismatch")
    if actor["role"] == "student" and (claims["student"] != actor["id"] or student != actor["id"]):
        raise PermissionError("Private learner scope required")
    if student and student not in course["students"]:
        raise PermissionError("Learner is not enrolled")
    return claims, actor, course, student


async def get_learning_twin(student_id: str = "") -> dict:
    """Read a learner's assessed evidence. Teachers can select an enrolled learner within their signed scope."""
    _, _, course, student = await asyncio.to_thread(authorize, "get_learning_twin", student_id or None)
    if not student:
        raise ValueError("Select a learner")
    def read():
        with db() as conn:
            return learning_twin(conn, course, student)
    return await asyncio.to_thread(read)


async def get_course_materials() -> dict:
    """Read approved course references; never exam questions or answer keys."""
    _, _, course, _ = await asyncio.to_thread(authorize, "get_course_materials")
    for item in course["materials"]:
        await inspect(item["content"])
    return {k: course[k] for k in ("name", "objectives", "concepts", "materials")}


async def get_student_progress(student_id: str = "") -> dict:
    """Read scoped progress, assignment history and released result summaries without raw exam answers."""
    _, actor, course, student = await asyncio.to_thread(authorize, "get_student_progress", student_id or None)
    if not student:
        raise ValueError("Select a learner")
    def read():
        from backend.conversations import academic_snapshot
        with db() as conn:
            records = many_of(conn, ("attempt", "exam", "coding_assignment", "code_review", "intervention", "assignment_submission", "evidence"))
            if actor["role"] == "student" and any(a["course_id"] == course["id"] and a["student_id"] == student and a["status"] == "in_progress" for a in records["attempt"]):
                raise PermissionError("Learning tools are paused during an active assessment")
            return {"twin": learning_twin(conn, course, student, evidence=records["evidence"]), "academic_record": academic_snapshot(records, course, student)}
    return await asyncio.to_thread(read)


async def get_class_summary() -> dict:
    """Return anonymous class aggregates and the current student's own provisional rank only."""
    _, actor, course, _ = await asyncio.to_thread(authorize, "get_class_summary")
    def read():
        from backend.class_context import summarize_class
        with db() as conn:
            return summarize_class(classroom_twins(conn, course, course["students"]), actor["id"])
    return await asyncio.to_thread(read)


async def search_learner_memory(query: str, student_id: str = "") -> dict:
    """Retrieve course-scoped long-term learning memories for one authorized learner."""
    _, actor, course, student = await asyncio.to_thread(authorize, "search_learner_memory", student_id or None)
    if not student or not query or len(query) > 2000:
        raise ValueError("Select a learner and a query of 1-2000 characters")
    await inspect(query)
    from backend.cloud.memory import retrieve_for_chat
    result = await retrieve_for_chat(actor["org"], course["id"], student, query)
    for fact in result["memories"]:
        await inspect(fact, "output")
    return result
