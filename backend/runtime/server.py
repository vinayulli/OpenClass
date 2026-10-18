"""One deployed specialist per container, using the Agent Runtime HTTP contract."""
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from backend.cloud.config import required, validate_governance
from backend.security.identity import authorize_peer, managed
from .tickets import execution_grant, invocation_context, verify


@asynccontextmanager
async def lifespan(app):
    validate_governance()
    if not managed() or os.getenv("OPENCLASS_AGENT_EXECUTION") != "managed" or os.getenv("MCP_SCOPE_PRIVATE_KEY"):
        raise RuntimeError("Specialist runtime requires managed identity and must not hold the API signing key")
    if required("OPENCLASS_AGENT_KIND") not in {"teacher", "tutor", "exam", "code", "path", "intervention", "web"}:
        raise RuntimeError("Unknown deployed specialist")
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def bound_payload(request, call_next):
    from starlette.responses import JSONResponse
    if len(await request.body()) > 500_000:
        return JSONResponse({"detail": "Runtime request exceeds size limit"}, status_code=413)
    return await call_next(request)


class Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: dict
    user_id: str
    grant: str


@app.post("/invoke")
async def invoke(body: Invocation, request: Request):
    kind = required("OPENCLASS_AGENT_KIND")
    try:
        caller = await asyncio.to_thread(authorize_peer, request.headers, kind)
        verify(body.grant, kind, body.context, body.user_id, caller)
    except Exception:
        raise HTTPException(403, "Verified caller and payload-bound execution grant required") from None
    token = execution_grant.set(body.grant)
    import copy
    context_token = invocation_context.set(copy.deepcopy(body.context))
    try:
        from backend.agents.runner import invoke_local
        context = body.context
        if context.get("_tool_runtime"):
            context["_tool_runtime"]["coordinator_remote"] = True
        if kind == "code" and context.get("repository", {}).get("url"):
            from backend.cloud.mcp_client import call_scoped
            from backend.security.policy import current_agent
            agent_token = current_agent.set("code")
            try:
                context["repository"] = await call_scoped("github", "inspect_public_repository", {"url": context["repository"]["url"]}, context.pop("_github_context"))
            finally:
                current_agent.reset(agent_token)
        return await invoke_local(kind, context, body.user_id)
    finally:
        invocation_context.reset(context_token)
        execution_grant.reset(token)


@app.post("/api/reasoning_engine")
async def query(request: Request):
    envelope = await request.json()
    if envelope.get("class_method") != "query":
        raise HTTPException(400, "Unsupported runtime method")
    try:
        body = Invocation.model_validate(envelope.get("input", {}))
    except ValueError:
        raise HTTPException(422, "Invalid runtime input") from None
    return {"output": await invoke(body, request)}
