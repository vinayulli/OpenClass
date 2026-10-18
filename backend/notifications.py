"""Durable, recipient-scoped in-app events; no email or browser-push transmission."""
import hashlib
import json
from .store import get, now, put


def notify(conn, course, recipients, event, title, message, target_type, target_id):
    allowed = {course["teacher_id"], *course["students"]}
    for recipient in set(recipients) & allowed:
        id = "notification:"+hashlib.sha256(json.dumps([event, target_id, recipient]).encode()).hexdigest()
        if get(conn, "notification", id):
            continue
        put(conn, "notification", {"id": id, "org": course["org"], "course_id": course["id"], "recipient_id": recipient, "event": event, "title": title, "message": message, "target_type": target_type, "target_id": target_id, "created_at": now(), "read_at": None})


def exam_recipients(course, exam):
    audience = set(exam.get("assigned_student_ids") or course["students"])
    if exam["blueprint"].get("student_id"):
        audience &= {exam["blueprint"]["student_id"]}
    return sorted(audience & set(course["students"]))
