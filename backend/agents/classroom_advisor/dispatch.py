"""Deterministic handling of the UI's standard selected-learner test shortcuts.

Custom requests still use the Advisor's reasoning/tools, rather than silently
discarding requested counts, formats, topics or timing constraints.
"""
def normalize(message):
    return " ".join(message.casefold().strip().rstrip(".").split())


SHORTCUTS = {normalize(message) for message in (
    "Generate a practice test for this learner focused on evidenced gaps. Ask me if any required details are unclear.",
    "Generate a practice test for the selected learner",
    "Generate a personalized practice test for each selected learner",
)}


def quick_blueprint(context, runtime):
    if not runtime or runtime["actor"]["role"] != "teacher" or not runtime.get("allow_test_generation"):
        return None
    if normalize(context.get("question", "")) not in SHORTCUTS:
        return None
    selected = context.get("selected_learner")
    if not selected:
        return None
    return personalized_blueprint(selected["twin"], selected["student"]["id"])


def personalized_blueprint(twin, student_id):
    concepts = twin["concepts"]
    known = [c for c in concepts if c.get("evidence_count", 0) > 0 and c.get("mastery") is not None]
    gaps = sorted((c for c in known if c["mastery"] < 60), key=lambda c: c["mastery"])
    targets = (gaps or sorted(known, key=lambda c: c["mastery"]) or concepts)[:3]
    if not targets:
        return None
    return {"title": "Personalized practice draft", "kind": "practice", "student_id": student_id, "concept_ids": [c["id"] for c in targets], "question_count": 5, "total_marks": 10, "duration_minutes": 20, "difficulty": "beginner", "question_types": ["mcq"], "release_feedback": True}


def quick_blueprints(context, runtime):
    if runtime and runtime["actor"]["role"] == "teacher" and runtime.get("allow_test_generation") and normalize(context.get("question", "")) == normalize("Generate a personalized practice test for each selected learner") and context.get("selected_learners"):
        return [personalized_blueprint(s["twin"], s["student"]["id"]) for s in context["selected_learners"]]
    single = quick_blueprint(context, runtime)
    return [single] if single else None


async def start_assessment(blueprint, runtime):
    if runtime.get("coordinator_remote"):
        from ...runtime.coordinator import request_action
        result = await request_action("start_assessment", {"blueprint": blueprint})
        runtime["actions"].extend(result["actions"])
        return result["message"]
    from ...store import db
    from ...services import course_access
    from ..coordinator.service import queue_assessment_async
    import asyncio
    def authorized_course():
        with db() as conn:
            return course_access(conn, runtime["course_id"], runtime["actor"])
    if isinstance(blueprint, list) and len(blueprint) > 1:
        from ..coordinator.service import queue_batch_assessments
        batch = await queue_batch_assessments(runtime["course_id"], runtime["actor"], [b["student_id"] for b in blueprint], teacher_request=runtime["latest_message"])
        runtime["actions"].append({"type": "assessment_batch", "batch_id": batch["id"], "student_count": len(batch["jobs"]), "status": "queued"})
        return f"Queued {len(batch['jobs'])} personalized practice-test tasks for the Assessment Generator over A2A. Each learner has an independent task and session. Tasks run with bounded concurrency; authenticated webhooks report completion. Defaults per test: 5 MCQs, 10 marks, 20 minutes, beginner difficulty. Drafts require your review before publication."
    if isinstance(blueprint, list):
        blueprint = blueprint[0]
    course = await asyncio.to_thread(authorized_course)
    job = await queue_assessment_async(course, runtime["actor"], blueprint, teacher_request=runtime["latest_message"])
    runtime["actions"].append({"type": "assessment_job", "job_id": job["id"], "status": job["status"], "student_id": blueprint["student_id"]})
    return "The Assessment Generator is preparing a practice-test draft for the selected learner. Defaults: 5 multiple-choice questions, 10 marks, 20 minutes, beginner difficulty. It targets the weakest evidenced concepts, or broad diagnostic coverage when evidence is absent. The draft will appear in Assessments and notifications when ready. Review it before publishing."
