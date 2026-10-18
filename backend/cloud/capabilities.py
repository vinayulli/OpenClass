"""Short-lived signed user scope; complementary to GEAP workload identity and gateway IAM."""
import contextvars
import os
import time
from .config import required

request_scope = contextvars.ContextVar("openclass_mcp_scope", default=None)


def secret():
    value = required("MCP_CONTEXT_SECRET")
    if len(value) < 32:
        raise RuntimeError("MCP_CONTEXT_SECRET must have at least 32 characters")
    return value


def issue(current, course_id, student_id, agent=None, service="data", resources=None):
    import jwt
    from ..store import uid
    from ..security.policy import tools_for
    agent = agent or ("teacher" if current.get("role") == "teacher" else "tutor")
    claims = {"agent": agent, "permissions": tools_for(agent, service), "resources": resources or {}, "iss": "openclass-api", "aud": "openclass-"+service+"-mcp", "sub": current["id"], "org": current["org"], "course": course_id, "student": student_id or "*", "iat": int(time.time()), "exp": int(time.time())+120, "jti": uid()}
    from ..security.identity import managed
    if managed():
        return jwt.encode(claims, required("MCP_SCOPE_PRIVATE_KEY"), algorithm="RS256")
    return jwt.encode(claims, secret(), algorithm="HS256")


def verify(token, service="data"):
    import jwt
    from ..security.identity import managed
    key, algorithms = (required("MCP_SCOPE_PUBLIC_KEY"), ["RS256"]) if managed() else (secret(), ["HS256"])
    claims = jwt.decode(token, key, algorithms=algorithms, audience="openclass-"+service+"-mcp", issuer="openclass-api", options={"require": ["exp", "iat", "sub", "org", "course", "student", "jti", "agent", "permissions", "resources"]})
    if claims["exp"]-claims["iat"] > 120:
        raise ValueError("Scope lifetime exceeds limit")
    return claims
