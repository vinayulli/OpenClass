from fastapi import APIRouter, Depends, HTTPException
from ..learning import classroom_twins
from ..schemas import CourseInput, Enrollment, Material
from ..store import all_of, many_of, audit, db, get, now, password_hash, put, uid
from ..services import user, teacher, public_user, course_access, safe_exam, safe_attempt, authenticated_db

router = APIRouter()

@router.get("/api/courses")
def courses(context=Depends(authenticated_db)):
    current, conn = context
    return [{k: c[k] for k in ("id", "name", "code")} for c in all_of(conn, "course") if not c.get("archived", False) and c["org"] == current["org"] and (c["teacher_id"] == current["id"] or current["id"] in c["students"])]


@router.get("/api/workspace")
def workspace(course_id: str | None = None, context=Depends(authenticated_db)):
    current, conn = context
    available = courses(context)
    selected = course_id if any(c["id"] == course_id for c in available) else available[0]["id"] if available else None
    return {"user": public_user(current), "courses": available, "course_id": selected, "overview": classroom_overview(conn, selected, current) if selected else None}


@router.post("/api/courses")
def create_course(body: CourseInput, current=Depends(teacher)):
    with db() as conn:
        course = put(conn, "course", {**body.model_dump(), "id": uid(), "org": current["org"], "teacher_id": current["id"], "students": [], "materials": [], "created_at": now()})
        audit(conn, current["id"], "course.created", course["id"])
        return course


@router.get("/api/courses/{course_id}/overview")
def overview(course_id: str, context=Depends(authenticated_db)):
    current, conn = context
    return classroom_overview(conn, course_id, current)


def classroom_overview(conn, course_id, current):
    course = course_access(conn, course_id, current)
    records = many_of(conn, ("user", "evidence", "exam", "intervention", "attempt"))
    accounts = {u["id"]: u for u in records["user"]}
    students = [public_user(accounts[s]) for s in course["students"] if s in accounts and (current["role"] == "teacher" or s == current["id"])]
    twins = classroom_twins(conn, course, [s["id"] for s in students], evidence=records["evidence"])
    exams = [safe_exam(e, current) for e in records["exam"] if e["course_id"] == course_id and (current["role"] == "teacher" or e["status"] == "published" and e["blueprint"].get("student_id") in (None, current["id"]) and (not e.get("assigned_student_ids") or current["id"] in e["assigned_student_ids"]))]
    interventions = [i for i in records["intervention"] if i["course_id"] == course_id and (current["role"] == "teacher" or i["student_id"] == current["id"] and i["status"] == "assigned")]
    attempts = [a for a in records["attempt"] if a["course_id"] == course_id and (current["role"] == "teacher" or a["student_id"] == current["id"])]
    if current["role"] == "student":
        lookup = {e["id"]: e for e in records["exam"] if e["course_id"] == course_id}
        attempts = [safe_attempt(conn, a, current, exam_records=lookup) for a in attempts]
    return {"course": course, "students": students, "twins": twins, "exams": exams, "interventions": interventions, "attempts": attempts}


@router.post("/api/courses/{course_id}/students")
def enroll(course_id: str, body: Enrollment, current=Depends(teacher)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812402)")
        course = course_access(conn, course_id, current)
        email = body.email.strip().lower()
        account = next((u for u in all_of(conn, "user") if u["email"] == email), None)
        if account and (account["org"] != current["org"] or account["role"] != "student"):
            raise HTTPException(409, "This account cannot be enrolled")
        if not account:
            account = put(conn, "user", {"id": uid(), "name": body.name, "email": email, "role": "student", "org": current["org"], "password": password_hash(body.password)})
        if account["id"] not in course["students"]:
            course["students"].append(account["id"])
            put(conn, "course", course)
        audit(conn, current["id"], "student.enrolled", course_id)
        return public_user(account)


@router.post("/api/courses/{course_id}/materials")
def material(course_id: str, body: Material, current=Depends(teacher)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812402)")
        course = course_access(conn, course_id, current)
        course["materials"].append({**body.model_dump(), "id": uid(), "created_at": now()})
        return put(conn, "course", course)


