from fastapi import APIRouter, Depends, HTTPException
from ..services import course_access, teacher, user
from ..store import all_of, db, get, now, put

router = APIRouter()


def visible_notification(conn, notification, actor):
    if not notification or notification["recipient_id"] != actor["id"] or notification["org"] != actor["org"]:
        return False
    try:
        course_access(conn, notification["course_id"], actor)
    except HTTPException:
        return False
    return True


@router.get("/api/notifications")
def notifications(current=Depends(user)):
    with db() as conn:
        items = [n for n in all_of(conn, "notification") if visible_notification(conn, n, current)]
        items.sort(key=lambda n: (n["created_at"], n["id"]), reverse=True)
        return {"items": items[:40], "unread": sum(n["read_at"] is None for n in items)}


@router.post("/api/notifications/read-all")
def read_all(current=Depends(user)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812410)")
        for item in all_of(conn, "notification"):
            if visible_notification(conn, item, current) and item["read_at"] is None:
                item["read_at"] = now()
                put(conn, "notification", item)
    return {"ok": True}


@router.post("/api/notifications/{notification_id}/read")
def read_notification(notification_id: str, current=Depends(user)):
    with db() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7812410)")
        item = get(conn, "notification", notification_id)
        if not visible_notification(conn, item, current):
            raise HTTPException(404)
        item["read_at"] = item["read_at"] or now()
        put(conn, "notification", item)
    return {"ok": True}


@router.get("/api/courses/{course_id}/students/{student_id}/details")
def learner_profile(course_id: str, student_id: str, current=Depends(teacher)):
    from ..learner_details import details
    with db() as conn:
        return details(conn, course_id, student_id, current)
