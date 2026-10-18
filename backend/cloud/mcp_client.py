"""Fixed-destination MCP transport. Credentials never enter the model context."""
import asyncio
import json
import os
from urllib.parse import urlsplit
import httpx
from .config import required


def checked_url(value):
    parsed = urlsplit(value)
    from ..security.identity import managed
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("MCP URL must not contain credentials, query or fragment")
    if parsed.scheme != "https" and not (not managed() and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
        raise ValueError("Use HTTPS, or loopback HTTP in local mode")
    if not parsed.hostname:
        raise ValueError("MCP host required")
    return value


def decode_result(result):
    if result.isError:
        raise RuntimeError("MCP tool failed")
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        value = structured
    else:
        resources = [item.resource for item in result.content if getattr(item, "type", None) == "resource"]
        if resources:
            if len(resources) != 1 or not hasattr(resources[0], "text"):
                raise ValueError("Expected one embedded text resource")
            text = resources[0].text
            if len(text.encode()) > 15000:
                raise ValueError("GitHub text resource exceeds limit")
            return {"encoding": "utf-8", "content": text, "uri": str(resources[0].uri)}
        parts = [item.text for item in result.content if getattr(item, "type", None) == "text"]
        value = json.loads("\n".join(parts))
    if len(json.dumps(value).encode()) > 300_000:
        raise ValueError("MCP response exceeds the inspection limit")
    return value


async def call(url, tool, arguments, headers):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with httpx.AsyncClient(headers=headers, timeout=60, follow_redirects=False) as client:
        async with streamable_http_client(checked_url(url), http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return decode_result(await session.call_tool(tool, arguments))


async def call_scoped(service, tool, arguments, scope_token):
    from ..security.identity import managed
    from ..security.policy import allow_tool, current_agent
    allow_tool(current_agent.get(), service, tool)
    headers = {"X-OpenClass-Context": scope_token}
    if managed():
        from ..security.transport import workload_token
        headers["X-OpenClass-Workload-Token"] = await asyncio.to_thread(workload_token)
        from ..security.transport import ingress_token
        headers["Authorization"] = "Bearer "+await asyncio.to_thread(ingress_token, required(service.upper()+"_MCP_AUDIENCE"))
    result = await call(required(service.upper()+"_MCP_URL"), tool, arguments, headers)
    from .model_armor import inspect
    await inspect(json.dumps(result))
    return result
