import hashlib
import json
import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from fastapi import Depends, HTTPException, Request
from . import agents
from .learning import learning_twin
from .cloud.model_armor import ContentBlocked
from .store import all_of, audit, db, get, now, put, uid

logger = logging.getLogger("openclass")
limits = defaultdict(deque)
tasks = set()

def rate_limit(key, count=15, seconds=60):
    q = limits[key]
    current = time.time()
    while q and q[0] < current-seconds:
        q.popleft()
    if len(q) >= count:
        raise HTTPException(429, "Too many requests. Please wait a minute.")
    q.append(current)


def authenticate(conn, request):
    token = request.cookies.get("openclass_session", "")
    row = conn.execute("SELECT r.data FROM sessions s JOIN records r ON r.id=s.user_id AND r.kind='user' WHERE s.token=%s AND s.expires>%s", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    result = json.loads(row[0]) if row else None
    if not result:
        raise HTTPException(401, "Please sign in")
    return result


def user(request: Request):
    with db() as conn:
        return authenticate(conn, request)


def authenticated_db(request: Request):
    """Short read endpoints share the auth transaction; LLM routes do not hold it."""
    with db() as conn:
        yield authenticate(conn, request), conn



def teacher(current=Depends(user)):
    if current["role"] != "teacher":
        raise HTTPException(403, "Educator access required")
    return current



def public_user(u):
    return {k: v for k, v in u.items() if k != "password"}



def course_access(conn, course_id, current):
    course = get(conn, "course", course_id)
    if not course or course["org"] != current["org"] or (course["teacher_id"] != current["id"] and current["id"] not in course["students"]):
        raise HTTPException(404, "Class not found")
    return course



def exam_access(conn, exam_id, current):
    exam = get(conn, "exam", exam_id)
    if not exam:
        raise HTTPException(404, "Assessment not found")
    course = course_access(conn, exam["course_id"], current)
    if current["role"] == "student" and (exam["status"] != "published" or exam["blueprint"].get("student_id") not in (None, current["id"]) or exam.get("assigned_student_ids") and current["id"] not in exam["assigned_student_ids"]):
        raise HTTPException(404, "Assessment not found")
    return exam, course



def safe_exam(exam, current):
    if current["role"] == "teacher":
        return exam
    return {**exam, "questions": [{k: v for k, v in q.items() if k not in ("answer", "rubric", "explanation")} for q in exam["questions"]]}



def safe_attempt(conn, attempt, current, exam_records=None):
    result = dict(attempt)
    exam = exam_records.get(attempt["exam_id"]) if exam_records is not None else get(conn, "exam", attempt["exam_id"])
    if current["role"] == "student" and not exam["blueprint"]["release_feedback"]:
        for key in ("results", "score"):
            result.pop(key, None)
        result["feedback_withheld"] = True
    if current["role"] == "student" and attempt["status"] == "graded" and exam["blueprint"]["release_feedback"]:
        result["feedback"] = [{"question_id": q["id"], "answer": q["answer"], "explanation": q["explanation"]} for q in exam["questions"]]
    return result



def own_attempt(conn, attempt_id, current):
    attempt = get(conn, "attempt", attempt_id)
    if not attempt or attempt["student_id"] != current["id"]:
        raise HTTPException(404, "Attempt not found")
    exam_access(conn, attempt["exam_id"], current)
    return attempt



def write_evidence(conn, attempt):
    # Stable identifiers make submission and reviewed-grade updates idempotent.
    for r in attempt["results"]:
        if r["score"] is not None:
            put(conn, "evidence", {"id": attempt["id"]+":"+r["question_id"], "course_id": attempt["course_id"], "student_id": attempt["student_id"], "concept_id": r["concept_id"], "source": "Assessment result", "source_id": attempt["id"], "score": r["score"]/r["marks"], "confidence": 1, "kind": "assessment", "at": now()})
    course = get(conn, "course", attempt["course_id"])
    twin = learning_twin(conn, course, attempt["student_id"])
    put(conn, "twin_history", {"id": uid(), "at": now(), "source_id": attempt["id"], **twin})
    gaps = [c["name"] for c in twin["concepts"] if c["status"] == "requires review"]
    if gaps:
        from .notifications import notify
        notify(conn, course, [attempt["student_id"]], "coach.review_recommended", "Learning Coach: topics to review", "Updated assessment evidence suggests reviewing "+", ".join(gaps[:3])+". Ask your Coach for help.", "coach", attempt["id"])
    from .cloud.memory_outbox import enqueue
    # No names, raw answers, model answer keys or sensitive traits enter managed memory.
    import json
    summary = json.dumps({"source": attempt["id"], "kind": "assessed learning evidence", "results": [{"concept": r["concept_id"], "score": r["score"], "marks": r["marks"], "method": r["method"]} for r in attempt["results"] if r["score"] is not None]})
    enqueue(conn, course["org"], course["id"], attempt["student_id"], attempt["id"], summary)



async def ai_call(kind, context, current):
    try:
        context = {**context, "_org_id": current["org"]}
        return await asyncio.wait_for(agents.invoke(kind, context, current["id"]), timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "90"))+10)
    except TimeoutError as error:
        logger.warning("agent_timeout kind=%s", kind)
        raise HTTPException(504, "The advisor timed out while contacting Gemini or a managed service. Your question was not saved; retry once or check backend logs.") from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    except ContentBlocked as error:
        raise HTTPException(422, "Content was blocked by Model Armor. Rephrase the request or ask your educator to review the source material.") from error
    except Exception as error:
        logger.warning("agent_failed kind=%s type=%s code=%s http_status=%s", kind, type(error).__name__, getattr(error, "code", "unavailable"), getattr(getattr(error, "response", None), "status_code", "unavailable"))
        raise HTTPException(502, "AI service could not complete this request. Please retry.") from error


