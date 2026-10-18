"""SDK-validated A2A 0.3 transport profile; JSON-RPC over HTTP, no SSE."""
from a2a.types import AgentCard, Task, SendMessageRequest
from datetime import datetime, timezone
from .config import agent_url, callback_url, callback_token


def card():
    return AgentCard.model_validate({"name": "OpenClass Assessment Generator", "description": "Generate enrolled-learner assessment drafts. Long-running tasks finish through authenticated push callbacks.", "url": agent_url(), "version": "1.0.0", "protocolVersion": "0.3.0", "capabilities": {"streaming": False, "pushNotifications": True}, "defaultInputModes": ["application/json"], "defaultOutputModes": ["application/json"], "securitySchemes": {"serviceBearer": {"type": "http", "scheme": "bearer"}}, "security": [{"serviceBearer": []}], "skills": [{"id": "assessment-draft", "name": "Assessment draft", "description": "Generate a draft from an authorized OpenClass job and its validated blueprint. Never publishes.", "tags": ["education", "assessment"]}]})


def send_request(job_id):
    return SendMessageRequest.model_validate({"jsonrpc": "2.0", "id": job_id, "method": "message/send", "params": {"message": {"kind": "message", "role": "user", "messageId": job_id, "parts": [{"kind": "data", "data": {"job_id": job_id}}]}, "configuration": {"blocking": False, "pushNotificationConfig": {"id": "completion", "url": callback_url(), "token": job_id, "authentication": {"schemes": ["Bearer"], "credentials": callback_token(job_id)}}}}})


def task_document(job, state, exam_id=None):
    result = {"kind": "task", "id": job["id"], "contextId": job["course_id"], "status": {"state": state, "timestamp": datetime.now(timezone.utc).isoformat()}, "metadata": {"job_id": job["id"], "course_id": job["course_id"]}}
    if exam_id:
        result["artifacts"] = [{"artifactId": "assessment-draft", "name": "Draft assessment reference", "parts": [{"kind": "data", "data": {"exam_id": exam_id, "review_required": True}}]}]
    return Task.model_validate(result).model_dump(mode="json", by_alias=True, exclude_none=True)
