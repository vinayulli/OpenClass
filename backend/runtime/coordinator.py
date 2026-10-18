"""Delegate mutations back to the API's authorized durable coordinator."""
import asyncio
from backend.cloud.config import required
from backend.cloud.mcp_client import checked_url
from .tickets import execution_grant, invocation_context


async def request_action(name, arguments):
    from .client import post
    grant, context = execution_grant.get(), invocation_context.get()
    if not grant or context is None:
        raise PermissionError("An authenticated root invocation is required for coordinator actions")
    payload = {"grant": grant, "context": context, "name": name, "arguments": arguments}
    return await asyncio.to_thread(post, checked_url(required("OPENCLASS_COORDINATOR_URL")), payload)
