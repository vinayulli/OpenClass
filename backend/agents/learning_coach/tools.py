import re
import asyncio


def public_query(query, actor):
    if not query.strip() or len(query) > 500:
        raise ValueError("Use a general educational query of 1–500 characters")
    private = [actor.get(k, "") for k in ("id", "name", "email", "org")]
    if any(value and value.casefold() in query.casefold() for value in private) or re.search(r"@|\b(?:student[-_]?\d+|session[_ -]?id|mastery|my grade|my score)\b", query, re.I):
        raise ValueError("Web queries must not include learner identities, records, scores or session identifiers")
    return query.strip()


def build_tools(runtime):
    actor, course_id = runtime["actor"], runtime["course_id"]

    def load_progress():
        from ...store import db
        from ...learner_details import details
        with db() as conn:
            return details(conn, course_id, actor["id"], actor)

    async def get_my_progress() -> dict:
        """Read only the authenticated learner's course progress and academic evidence."""
        from ...cloud.config import enabled
        if enabled("DATA_MCP_ENABLED"):
            from ...cloud.mcp_client import call_scoped
            return await call_scoped("data", "get_student_progress", {}, runtime["data_scope_token"])
        return await asyncio.to_thread(load_progress)

    async def search_my_memories(query: str) -> dict:
        """Read the current turn's course-scoped GEAP memory lookup for the authenticated learner."""
        await get_my_progress()
        if runtime.get("memory_lookup") is not None:
            return runtime["memory_lookup"]
        from ...cloud.memory import retrieve_for_chat
        from ...cloud.model_armor import inspect
        if not query or len(query) > 2000:
            raise ValueError("Invalid memory query length")
        from ...cloud.config import enabled
        if enabled("DATA_MCP_ENABLED"):
            from ...cloud.mcp_client import call_scoped
            runtime["memory_lookup"] = await call_scoped("data", "search_learner_memory", {"query": query}, runtime["data_scope_token"])
            return runtime["memory_lookup"]
        await inspect(query)
        runtime["memory_lookup"] = await retrieve_for_chat(actor["org"], course_id, actor["id"], query)
        return runtime["memory_lookup"]

    async def search_public_learning(query: str) -> dict:
        """Search the public web for a general educational question. Never include private learner/course facts."""
        from ...agents.runner import invoke
        public = public_query(query, actor)
        result = await invoke("web", {"question": public, "_course_id": course_id, "_org_id": actor["org"]}, actor["id"])
        runtime["sources"].extend(result.get("sources", []))
        return {"message": result["message"], "sources": result.get("sources", [])}

    async def request_practice_test(concept_ids: list[str], question_count: int = 5) -> dict:
        """Delegate a private topic test to Assessment Generator; returns a saved task and open-test link. Ask about topics/count if unclear. Never create teacher-visible exams."""
        from fastapi import HTTPException
        from ..coordinator.service import allows_test_request
        if not allows_test_request(runtime.get("latest_message", "")):
            raise ValueError("The student must explicitly request creation of a test")
        if runtime.get("practice_action"):
            return runtime["practice_action"]
        from ...routes.self_study import generate_study, StudyRequest
        item = await asyncio.to_thread(generate_study, course_id, "practice", StudyRequest(concept_ids=concept_ids, question_count=question_count), actor)
        action = {"type": "private_practice", "course_id": course_id, "study_id": item["id"], "status": item["status"], "url": "/courses/"+course_id+"/self-study?study="+item["id"]}
        runtime["actions"].append(action)
        runtime["practice_action"] = action
        return action

    if runtime.get("coordinator_remote"):
        from ...runtime.tool_proxy import remote_tool
        request_practice_test = remote_tool(request_practice_test, runtime)
    return [get_my_progress, search_my_memories, search_public_learning, request_practice_test]
