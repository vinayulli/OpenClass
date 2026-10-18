"""API-issued, payload-bound execution grants; agents receive no signing key."""
import contextvars
import hashlib
import json
import time
import jwt
from backend.cloud.config import required

execution_grant = contextvars.ContextVar("execution_grant", default=None)
invocation_context = contextvars.ContextVar("invocation_context", default=None)


def fingerprint(context):
    return hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def issue(kind, context, user_id):
    return jwt.encode({"iss": "openclass-api", "aud": "openclass-runtime", "sub": user_id,
                       "agent": kind, "digest": fingerprint(context), "iat": int(time.time()),
                       "exp": int(time.time())+180, "delegates": ["web"] if kind == "tutor" else []},
                      required("MCP_SCOPE_PRIVATE_KEY"), algorithm="RS256")


def verify(token, kind, context, user_id, caller):
    claims = jwt.decode(token, required("MCP_SCOPE_PUBLIC_KEY"), algorithms=["RS256"],
                        issuer="openclass-api", audience="openclass-runtime",
                        options={"require": ["sub", "exp", "iat", "agent", "digest", "delegates"]})
    if claims["sub"] != user_id or claims["exp"]-claims["iat"] > 180:
        raise PermissionError("Execution grant scope mismatch")
    if caller == "api":
        if claims["agent"] != kind or claims["digest"] != fingerprint(context):
            raise PermissionError("Execution payload is outside the grant")
    elif caller == "tutor" and kind == "web" and claims["agent"] == "tutor" and "web" in claims["delegates"]:
        if set(context) - {"question", "_course_id", "_org_id"} or not isinstance(context.get("question"), str) or len(context["question"]) > 500:
            raise PermissionError("Web delegation accepts only a bounded public query")
    else:
        raise PermissionError("Delegation is not permitted")
    return claims
