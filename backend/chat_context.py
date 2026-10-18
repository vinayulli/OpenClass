"""Build bounded, authorized chat context off the async API event loop."""
import re
from fastapi import HTTPException
from .learning import classroom_twins
from .services import course_access
from .store import db, all_of, many_of


def resolve_learner(message, roster):
    matches = [s["id"] for s in roster if re.search(r"(?<!\w)"+re.escape(s["name"])+r"(?!\w)", message, re.I)]
    return matches[0] if len(matches) == 1 else None


def build_context(course_id, body, current):
    with db() as conn:
        course = course_access(conn, course_id, current)
        teacher = current["role"] == "teacher"
        requested = getattr(body, "student_ids", [])
        if requested and body.student_id:
            raise HTTPException(422, "Choose a single learner or batch recipients, not both")
        if requested and (not teacher or not set(requested) <= set(course["students"]) or len(set(requested)) != len(requested)):
            raise HTTPException(422, "Batch recipients must be distinct enrolled learners selected by their teacher")
        if body.student_id and (body.student_id not in course["students"] or not teacher and body.student_id != current["id"]):
            raise HTTPException(404, "Learner not found")
        conversation_id = getattr(body, "conversation_id", None)
        if conversation_id:
            from .conversations import authorize
            authorize(conn, conversation_id, course_id, current)
        records = many_of(conn, ("attempt", "chat", "evidence", "user", "exam", "coding_assignment", "code_review", "intervention", "assignment_submission", "learner_profile"))
        attempts = records["attempt"] if not teacher else []
        if any(a["student_id"] == current["id"] and a["status"] == "in_progress" for a in attempts):
            raise HTTPException(409, "Tutoring is paused during an active assessment. Submit it to resume.")
        history = [m for m in records["chat"] if m["course_id"] == course_id and m["user_id"] == current["id"] and m.get("conversation_id") == conversation_id][-6:]
        # No tool actions, source bodies or unbounded conversation records in the prompt.
        context = {"curriculum": {k: course[k] for k in ("name", "objectives", "concepts", "materials")}, "syllabus_progress": course.get("syllabus_progress"), "question": body.message, "conversation": [{"question": m["question"], "response": m["response"][:4000]} for m in history]}
        ids = course["students"]
        twins = classroom_twins(conn, course, ids, evidence=records["evidence"])
        if teacher:
            accounts = {u["id"]: u for u in records["user"]}
            roster = [{"id": s, "name": accounts[s]["name"]} for s in ids if s in accounts]
            context["learner_roster"] = roster
            context["class_twins"] = [{**t, "concepts": [{k: v for k, v in c.items() if k != "evidence"} for c in t["concepts"]]} for t in twins]
            selected = body.student_id or resolve_learner(body.message, roster)
            if selected:
                context["selected_learner"] = {"student": {"id": selected, "name": accounts[selected]["name"]}, "twin": next(t for t in twins if t["student_id"] == selected)}
            if requested:
                context["selected_learners"] = [{"student": {"id": s, "name": accounts[s]["name"]}, "twin": next(t for t in twins if t["student_id"] == s)} for s in requested]
        else:
            context["twin"] = next(t for t in twins if t["student_id"] == current["id"])
            from .conversations import academic_snapshot
            context["academic_record"] = academic_snapshot(records, course, current["id"])
            profile = next((r for r in records["learner_profile"] if r["course_id"] == course_id and r["student_id"] == current["id"]), None)
            if profile:
                context["learner_preferences"] = {k: profile.get(k) for k in ("headline", "observations", "preferred_practice")}
            from .class_context import summarize_class
            context["class_performance"] = summarize_class(twins, current["id"])
    return context


def save_chat(record):
    from .store import put
    with db() as conn:
        put(conn, "chat", record)
        if record.get("conversation_id"):
            from .store import get
            session = get(conn, "chat_session", record["conversation_id"])
            if session:
                session.update(updated_at=record["at"])
                if session["title"] == "New conversation":
                    session["title"] = record["question"][:70]
                put(conn, "chat_session", session)
