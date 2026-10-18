import asyncio
import hmac
import json
from fastapi import APIRouter, Header, HTTPException, Request
from a2a.types import Task, TaskQueryParams, PushNotificationConfig, SendMessageRequest
from .config import shared_secret, callback_token, callback_url
from .protocol import card
from .state import accept_task, finish_task, receive_callback
from ..store import db, get

router = APIRouter()


def validate_push(push, job_id):
    value = PushNotificationConfig.model_validate(push)
    auth = value.authentication
    if value.url != callback_url() or value.token != job_id or not auth or auth.schemes != ["Bearer"] or not hmac.compare_digest(auth.credentials or "", callback_token(job_id)):
        raise ValueError("Only the configured authenticated completion webhook is accepted")
    return value.model_dump(mode="json", by_alias=True, exclude_none=True)


def load_task(task_id):
    with db() as conn:
        return get(conn, "a2a_task", "a2a:"+task_id)


@router.get("/a2a/assessment/.well-known/agent-card.json")
def agent_card():
    return card().model_dump(mode="json", by_alias=True, exclude_none=True)


@router.post("/a2a/assessment")
async def rpc(request: Request, authorization: str = Header(default="")):
    from ..security.identity import managed, authorize_peer
    if managed():
        try:
            await asyncio.to_thread(authorize_peer, request.headers, "exam")
        except Exception:
            raise HTTPException(403, "Authorized workload identity required")
    elif not hmac.compare_digest(authorization, "Bearer "+shared_secret()):
        raise HTTPException(401, "Agent service authentication required")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "A2A request too large")
    try:
        body = json.loads(raw)
    except ValueError:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}}
    request_id = body.get("id") if isinstance(body, dict) else None
    try:
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            raise ValueError("Invalid JSON-RPC envelope")
        method, params = body.get("method"), body.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            raise ValueError("Invalid method or parameters")
        if method == "message/send":
            parsed = SendMessageRequest.model_validate(body)
            parts = [p.root.data for p in parsed.params.message.parts if p.root.kind == "data"]
            if len(parts) != 1 or set(parts[0]) != {"job_id"}:
                raise ValueError("Expected an authorized job reference")
            job_id = parts[0]["job_id"]
            if not isinstance(job_id, str) or len(job_id) > 100:
                raise ValueError("Invalid job reference")
            config = parsed.params.configuration
            if not config or config.blocking is not False or not config.push_notification_config:
                raise ValueError("Use non-blocking tasks with a completion webhook")
            push = validate_push(config.push_notification_config.model_dump(by_alias=True), job_id)
            result = await asyncio.to_thread(accept_task, job_id, push)
        elif method in {"tasks/get", "tasks/cancel"}:
            query = TaskQueryParams.model_validate(params)
            item = await asyncio.to_thread(load_task, query.id)
            if not item:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": "Task not found"}}
            result = item["task"] if method == "tasks/get" else await asyncio.to_thread(finish_task, query.id, "canceled")
        elif method.startswith("tasks/pushNotificationConfig/"):
            task_id = params.get("taskId") or params.get("id")
            item = await asyncio.to_thread(load_task, task_id or "")
            if not item:
                raise ValueError("Task not found")
            if method.endswith("/set"):
                validate_push(params["pushNotificationConfig"], task_id)
            elif not method.endswith(("/get", "/list")):
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32004, "message": "Webhook removal is unsupported for this durable task profile"}}
            result = {"taskId": task_id, "pushNotificationConfig": item["push"]}
            if method.endswith("/list"):
                result = [result]
        else:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not supported"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (ValueError, KeyError, TypeError):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid task parameters or webhook configuration"}}


@router.post("/api/a2a/webhook")
async def completion(request: Request, authorization: str = Header(default="")):
    from ..security.identity import managed, caller_from_headers
    if managed():
        try:
            caller = await asyncio.to_thread(caller_from_headers, request.headers)
            if caller != "api":
                raise PermissionError()
        except Exception:
            raise HTTPException(403, "Assessment workload identity required")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "Callback too large")
    try:
        task = Task.model_validate_json(raw).model_dump(mode="json", by_alias=True, exclude_none=True)
    except ValueError:
        raise HTTPException(422, "Invalid A2A task callback")
    if not hmac.compare_digest(authorization, "Bearer "+callback_token(task["id"])):
        raise HTTPException(401, "Invalid task callback authentication")
    try:
        return await asyncio.to_thread(receive_callback, task)
    except ValueError:
        raise HTTPException(409, "Callback does not match a known terminal task")
