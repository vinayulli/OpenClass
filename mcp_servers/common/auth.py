import asyncio
from starlette.responses import JSONResponse
from backend.cloud.capabilities import request_scope, verify
from backend.security.identity import managed, caller_from_headers
from backend.security.policy import tools_for


class ScopedMCP:
    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k,v in scope["headers"]}
        try:
            claims = verify(headers.get("x-openclass-context", ""), self.service)
            if not tools_for(claims["agent"], self.service):
                raise PermissionError()
            if managed():
                caller = await asyncio.to_thread(caller_from_headers, headers)
                if caller != claims["agent"]:
                    raise PermissionError()
        except Exception:
            return await JSONResponse({"error": "Verified workload and scoped tool authorization required"}, status_code=403)(scope, receive, send)
        token = request_scope.set(claims)
        try:
            await self.app(scope, receive, send)
        finally:
            request_scope.reset(token)


def require_tool(service, name):
    from backend.security.policy import allow_tool
    claims = request_scope.get()
    if not claims or name not in claims["permissions"]:
        raise PermissionError("Scoped tool permission required")
    allow_tool(claims["agent"], service, name)
    return claims
