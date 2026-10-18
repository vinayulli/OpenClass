"""Versioned learning-path refreshes with student feedback, independent of private tests."""
from datetime import datetime, timedelta, timezone
from .store import all_of, put, now, uid


def paths_for(records, course_id, student_id):
    return [s for s in records if s["type"] == "path" and s["course_id"] == course_id and s["student_id"] == student_id]


def latest_ready(paths):
    return max((s for s in paths if s["status"] == "completed"), key=lambda s: s["created_at"], default=None)


def refresh_due(path):
    return not path or datetime.fromisoformat(path["updated_at"])+timedelta(days=1) <= datetime.now(timezone.utc)


def enqueue(conn, course, student_id, concept_ids, requested_by, records=None):
    records = all_of(conn, "self_study") if records is None else records
    paths = paths_for(records, course["id"], student_id)
    pending = next((s for s in paths if s["status"] in {"queued", "processing"}), None)
    if pending:
        return pending
    prior = latest_ready(paths)
    item = {"id": uid(), "type": "path", "course_id": course["id"], "org": course["org"], "student_id": student_id, "request": {"concept_ids": concept_ids, "question_count": 5}, "requested_by": requested_by, "version": max((s.get("version", 1) for s in paths), default=0)+1, "previous_path_id": prior["id"] if prior else None, "status": "queued", "created_at": now(), "updated_at": now(), "error": None}
    put(conn, "self_study", item)
    return item


def feedback_context(conn, item):
    feedback = [f for f in all_of(conn, "learning_feedback") if f["course_id"] == item["course_id"] and f["student_id"] == item["student_id"] and f["org"] == item["org"]]
    return [{k: f.get(k) for k in ("path_id", "helpfulness", "difficulty", "comment", "created_at")} for f in feedback[-20:]]
