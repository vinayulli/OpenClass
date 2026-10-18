"""Dynamic ADK scheduling with deterministic gates around each reasoning node.

Request context and validation sinks are invocation-local, never session state.
No database writes or automatic retries occur in this workflow.
"""
import json
import asyncio


def prepare(kind, context):
    """Pure input checks; return an explicit execution branch and safe context."""
    from ..schemas import Blueprint
    context = dict(context)
    branch = "reason"
    if kind == "exam":
        blueprint = Blueprint.model_validate(context["blueprint"]).model_dump()
        course = context["course"]
        if not set(blueprint["concept_ids"]) <= {c["id"] for c in course["concepts"]}:
            raise ValueError("Assessment references an unknown course concept")
        if not course.get("materials"):
            raise ValueError("Add course materials before generating an assessment")
        if blueprint.get("student_id") and blueprint["student_id"] not in course["students"]:
            raise ValueError("Assessment learner is not enrolled")
        context["blueprint"] = blueprint
        branch = "personalized" if blueprint.get("student_id") else "common_blueprint"
    elif kind == "code":
        files = context.get("repository", {}).get("files", [])
        if not files or not any(f.get("content", "").strip() for f in files):
            raise ValueError("Repository has no supported source files to assess")
        branch = "static_review"
    elif kind == "intervention":
        branch = "diagnostic" if context.get("twin", {}).get("evidence_count", 0) < 3 else "evidence_based"
    elif kind == "path":
        if not context.get("concept_ids") or not set(context["concept_ids"]) <= {c["id"] for c in context["course"]["concepts"]}:
            raise ValueError("Learning path contains unknown concepts")
        branch = "diagnostic_path" if context.get("twin", {}).get("evidence_count", 0) < 3 else "evidence_based_path"
    elif kind == "web":
        # Only the public question enters the search agent, never academic context.
        question = context.get("question", "").strip()
        if not question or len(question) > 500:
            raise ValueError("Invalid public learning query")
        context = {"question": question}
        branch = "public_research"
    context["workflow_policy"] = {"branch": branch, "teacher_review_required": kind in {"exam", "code", "intervention"}}
    if branch == "diagnostic":
        context["workflow_policy"]["instruction"] = "Insufficient evidence: propose a diagnostic before remediation; do not infer a knowledge gap."
    return context


def validate_result(kind, output, context, schema):
    """Reject malformed or out-of-curriculum results before any caller can save them."""
    if schema:
        if isinstance(output, schema):
            result = output.model_dump()
        elif isinstance(output, dict):
            result = schema.model_validate(output).model_dump()
        else:
            result = schema.model_validate_json(text_output(output)).model_dump()
        if kind == "exam":
            from ..learning import validate_exam
            validate_exam(context["blueprint"], result["questions"], context["course"])
        elif kind == "path":
            if any(step["concept_id"] not in {c["id"] for c in context["course"]["concepts"]} for step in result["steps"]):
                raise ValueError("Learning path references an unknown concept")
            resources = {r["id"] for r in context.get("learning_resources", [])}
            if any(ref["resource_id"] not in resources for step in result["steps"] for ref in step["references"]):
                raise ValueError("Learning path references an unknown resource")
        elif kind == "intervention":
            if result["concept_id"] not in {c["id"] for c in context["course"]["concepts"]}:
                raise ValueError("Learning plan references an unknown concept")
        return result
    message = text_output(output).strip()
    if not message:
        raise ValueError("Workflow returned an empty response")
    return {"message": message}


def text_output(output):
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return json.dumps(output)
    return "".join(getattr(p, "text", None) or "" for p in getattr(output, "parts", None) or [])


def build_workflow(kind, specialist, context, runtime, result_sink):
    from google.adk.workflow import Workflow, node, RetryConfig
    from ..cloud.model_armor import inspect, inspect_context

    def check_scope():
        # These values are server-bound, not chosen by the model or conversation history.
        if runtime:
            from ..security.identity import managed
            if managed() and runtime.get("coordinator_remote"):
                # Root payload/role is signed by the API. Live reads and
                # mutations recheck access at Data MCP/the coordinator.
                actor = runtime["actor"]
                if (kind == "teacher" and actor["role"] != "teacher") or (kind == "tutor" and actor["role"] != "student"):
                    raise ValueError("Agent role does not match the signed invocation")
                return
            from ..store import db, all_of
            from ..services import course_access
            actor = runtime["actor"]
            with db() as conn:
                course_access(conn, runtime["course_id"], actor)
                if (kind == "teacher" and actor["role"] != "teacher") or (kind == "tutor" and actor["role"] != "student"):
                    raise ValueError("Agent role does not match authenticated account")
                if kind == "tutor" and any(a["student_id"] == actor["id"] and a["status"] == "in_progress" for a in all_of(conn, "attempt")):
                    raise ValueError("Tutoring is paused during an active assessment")
    @node(name="check_request")
    async def check_request(node_input):
        await asyncio.to_thread(check_scope)
        checked = prepare(kind, context)
        await inspect_context(checked)
        return checked

    @node(name="validate_response")
    async def validate_response(node_input):
        from .runner import REGISTRY
        result = validate_result(kind, node_input, context, REGISTRY[kind].SCHEMA)
        await inspect(json.dumps(result), direction="output")
        return result

    @node(name="coordinate", rerun_on_resume=True)
    async def coordinate(ctx, node_input):
        checked = await ctx.run_node(check_request, node_input={})
        from .classroom_advisor.dispatch import quick_blueprints
        quick = quick_blueprints(checked, runtime) if kind == "teacher" else None
        from .learning_coach.dispatch import progress_summary
        progress = progress_summary(checked) if kind == "tutor" else None
        if progress:
            response = await ctx.run_node(summarize_progress, node_input=checked)
            branch = "evidence_summary"
        elif quick:
            response = await ctx.run_node(enqueue_practice_test, node_input=quick)
            branch = "assessment_handoff"
        else:
            from google.genai import types
            response = await ctx.run_node(specialist, node_input=types.Content(role="user", parts=[types.Part(text=json.dumps(checked))]))
            branch = checked["workflow_policy"]["branch"]
        # Scheduling occurs only after deterministic gates pass. No automatic repair
        # loops: tools may enqueue jobs and must not be replayed by an LLM retry.
        validated = await ctx.run_node(validate_response, node_input=response)
        result_sink["result"] = validated
        result_sink["branch"] = branch
        return validated

    @node(name="enqueue_practice_test")
    async def enqueue_practice_test(node_input):
        from .classroom_advisor.dispatch import start_assessment
        return await start_assessment(node_input, runtime)

    @node(name="summarize_progress")
    def summarize_progress(node_input):
        from .learning_coach.dispatch import progress_summary
        return progress_summary(node_input)

    return Workflow(name=specialist.name+"_workflow", edges=[("START", coordinate)], retry_config=RetryConfig(max_attempts=1))
