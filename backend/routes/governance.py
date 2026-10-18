import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..cloud.capabilities import issue
from ..cloud.config import enabled
from ..services import course_access, teacher, user
from ..store import all_of, db, put

router = APIRouter()


class MCPContextRequest(BaseModel):
    student_id: str | None = None


@router.get("/api/governance/status")
def status(current=Depends(user)):
    return {"memory": {"enabled": enabled("GEAP_MEMORY_ENABLED"), "configured": bool(os.getenv("GEAP_MEMORY_BANK_ID"))}, "model_armor": {"enabled": enabled("MODEL_ARMOR_ENABLED"), "configured": bool(os.getenv("MODEL_ARMOR_TEMPLATE"))}, "agent_gateway": {"configured": bool(os.getenv("GEAP_AGENT_GATEWAY")), "note": "Configuration is not proof of deployed enforcement"}, "identity": "Provisioned by Agent Runtime deployment, not a student login identity", "required": enabled("OPENCLASS_REQUIRE_GOVERNANCE")}


@router.post("/api/courses/{course_id}/mcp-context")
def mcp_context(course_id: str, body: MCPContextRequest, current=Depends(user)):
    with db() as conn:
        course = course_access(conn, course_id, current)
        student = body.student_id or current["id"]
        if student not in course["students"] or (current["role"] == "student" and student != current["id"]):
            raise HTTPException(404)
    return {"context_token": issue(current, course_id, student), "expires_in": 120}


@router.post("/api/courses/{course_id}/memory-sync/retry")
def retry_memory(course_id: str, current=Depends(teacher)):
    count = 0
    with db() as conn:
        course_access(conn, course_id, current)
        for item in all_of(conn, "memory_outbox"):
            if item["course_id"] == course_id and item["status"] == "failed":
                item.update(status="pending", attempts=0)
                put(conn, "memory_outbox", item)
                count += 1
    return {"queued": count}
