"""Bound educator tools; course and actor are supplied by the server, not the model."""
from fastapi import HTTPException
import asyncio


def build_tools(runtime):
    actor, course_id = runtime["actor"], runtime["course_id"]

    def load_details(student_id):
        from ...store import db
        from ...learner_details import details
        with db() as conn:
            return details(conn, course_id, student_id, actor)

    async def get_learner_details(student_id: str) -> dict:
        """Read an enrolled learner's academic progress, assessed attempts, coding reports and support plans."""
        from ...cloud.config import enabled
        if enabled("DATA_MCP_ENABLED") and not runtime.get("force_local_coordinator"):
            from ...cloud.mcp_client import call_scoped
            return await call_scoped("data", "get_student_progress", {"student_id": student_id}, runtime["data_scope_token"])
        return await asyncio.to_thread(load_details, student_id)

    async def search_learner_memories(student_id: str, query: str) -> dict:
        """Search only an enrolled learner's course-scoped GEAP Memory Bank facts."""
        await get_learner_details(student_id)
        cache = runtime.setdefault("learner_memory_lookups", {})
        if student_id in cache:
            return cache[student_id]
        if not query or len(query) > 2000:
            raise ValueError("Use a memory query of 1–2000 characters")
        from ...cloud.config import enabled
        if enabled("DATA_MCP_ENABLED"):
            from ...cloud.mcp_client import call_scoped
            cache[student_id] = await call_scoped("data", "search_learner_memory", {"student_id": student_id, "query": query}, runtime["data_scope_token"])
            return cache[student_id]
        if not enabled("GEAP_MEMORY_ENABLED"):
            return {"status": "disabled", "memories": [], "note": "Use the academic evidence provided; managed memory is not enabled."}
        from ...cloud.memory import retrieve_for_chat
        from ...cloud.model_armor import inspect
        await inspect(query)
        cache[student_id] = await retrieve_for_chat(actor["org"], course_id, student_id, query)
        return cache[student_id]

    async def request_student_test(student_id: str, instructions: str, concept_ids: list[str], question_count: int = 5, total_marks: int = 10, duration_minutes: int = 20, difficulty: str = "beginner", question_types: list[str] = ["mcq"]) -> dict:
        """Delegate an explicitly teacher-requested learner test to the Assessment Generator. Returns a draft-generation job, never publishes."""
        if not runtime.get("allow_test_generation"):
            return {"status": "not_authorized", "message": "Ask the educator to explicitly request creation of a test in the latest message."}
        if runtime["actions"]:
            return runtime["actions"][0]
        if not instructions or len(instructions) > 4000:
            raise ValueError("Provide teacher instructions of 1–4000 characters")
        await get_learner_details(student_id)
        from ...store import db
        from ...services import course_access
        from ..coordinator.service import queue_assessment_async
        from ...cloud.model_armor import inspect
        await inspect(instructions)
        with db() as conn:
            course = course_access(conn, course_id, actor)
        selected = concept_ids or [c["id"] for c in course["concepts"]][:question_count]
        if not 1 <= question_count <= 20 or total_marks < question_count or duration_minutes < 1:
            raise ValueError("Use valid question count, marks and duration")
        # Retain the actual teacher message so the delegate does not rely only on a model paraphrase.
        request = runtime["latest_message"]+"\nAdvisor interpretation: "+instructions
        job = await queue_assessment_async(course, actor, {"title": "Personalized test draft", "kind": "practice", "concept_ids": selected, "question_count": question_count, "total_marks": total_marks, "duration_minutes": duration_minutes, "difficulty": difficulty, "question_types": question_types, "release_feedback": True, "student_id": student_id}, teacher_request=request)
        action = {"type": "assessment_job", "job_id": job["id"], "status": job["status"], "student_id": student_id}
        runtime["actions"].append(action)
        return action

    async def request_student_tests(student_ids: list[str], instructions: str, concept_ids: list[str], question_count: int = 5, total_marks: int = 10, duration_minutes: int = 20, difficulty: str = "beginner", question_types: list[str] = ["mcq"]) -> dict:
        """Queue one A2A Assessment Generator task per explicitly selected learner, with bounded parallel execution and webhook completion."""
        if not runtime.get("allow_test_generation"):
            return {"status": "not_authorized", "message": "The latest teacher message must explicitly request assessment creation."}
        if runtime["actions"]:
            return runtime["actions"][0]
        if not instructions or len(instructions) > 4000:
            raise ValueError("Invalid assessment instructions")
        from ...cloud.model_armor import inspect
        from ..coordinator.service import queue_batch_assessments
        await inspect(instructions)
        template = None
        if concept_ids:
            template = {"title": "Personalized practice draft", "kind": "practice", "concept_ids": concept_ids, "question_count": question_count, "total_marks": total_marks, "duration_minutes": duration_minutes, "difficulty": difficulty, "question_types": question_types, "release_feedback": True}
        else:
            # Preserve requested settings while letting the coordinator choose
            # each learner's evidenced concepts independently.
            template = {"title": "Personalized practice draft", "kind": "practice", "concept_ids": [], "question_count": question_count, "total_marks": total_marks, "duration_minutes": duration_minutes, "difficulty": difficulty, "question_types": question_types, "release_feedback": True}
        batch = await queue_batch_assessments(course_id, actor, student_ids, template, teacher_request=runtime["latest_message"]+"\nAdvisor interpretation: "+instructions)
        action = {"type": "assessment_batch", "batch_id": batch["id"], "status": "queued", "student_count": len(batch["jobs"])}
        runtime["actions"].append(action)
        return action

    async def request_class_test_variants(instructions: str, concept_ids: list[str], question_count: int = 5, total_marks: int = 10, duration_minutes: int = 20, difficulty: str = "beginner", question_types: list[str] = ["mcq"]) -> dict:
        """Generate a standard test for EVERY enrolled student: same concepts/blueprint, distinct questions per student. Use only for an explicit whole-class request; not a selected subgroup."""
        import re
        text = runtime.get("latest_message", "")
        if not re.search(r"\b(?:everyone|every one|everybody|all (?:the )?students|every student|whole class|entire class|class[- ]wide)\b", text, re.I):
            return {"status": "not_authorized", "message": "Ask whether the teacher means the whole class or selected learners."}
        if not concept_ids:
            raise ValueError("Specify the common course concepts before generating variants")
        from ...store import db
        from ...services import course_access
        def roster():
            with db() as conn:
                return course_access(conn, course_id, actor)["students"]
        students = await asyncio.to_thread(roster)
        return await request_student_tests(students, instructions+" Same shared concepts and settings for every student; distinct question variants.", concept_ids, question_count, total_marks, duration_minutes, difficulty, question_types)

    mutations = [request_student_test, request_student_tests, request_class_test_variants]
    if runtime.get("coordinator_remote"):
        from ...runtime.tool_proxy import remote_tool
        mutations = [remote_tool(function, runtime) for function in mutations]
    return [get_learner_details, search_learner_memories, *mutations]
