"""Call a fixed configured runtime; models cannot choose an endpoint or identity."""
import asyncio
import logging
from urllib.parse import urlsplit
from backend.security.policy import current_agent, allow_call
from .tickets import execution_grant, issue
from .deployment import endpoints

logger = logging.getLogger("openclass.runtime")


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if key not in {"password", "password_hash", "hashed_password", "token", "api_key"}}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def post(url, body):
    from google.auth.transport.requests import AuthorizedSession
    from backend.security.transport import ingress_token, workload_token
    # A separate signed token gives the application the verified SPIFFE subject.
    destination = urlsplit(url)
    audience = f"{destination.scheme}://{destination.netloc}"
    headers = {"X-OpenClass-Workload-Token": workload_token()}
    if destination.hostname and destination.hostname.endswith(("-aiplatform.googleapis.com", "-aiplatform.mtls.googleapis.com")):
        import google.auth
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    else:
        # Standard run.app ingress needs the same explicit per-request unbound
        # token as MCP ingress; certificate-bound tokens require mtls.run.app.
        from google.auth.credentials import AnonymousCredentials
        headers["Authorization"] = "Bearer "+ingress_token(audience)
        # Gateway authenticates the workload at the TLS layer as well. Keep
        # explicit Cloud Run ingress tokens while presenting the native client
        # certificate to the egress proxy. Anonymous credentials prevent this
        # transport from replacing the audience-specific Authorization header.
        with AuthorizedSession(AnonymousCredentials()) as session:
            session.configure_mtls_channel()
            response = session.post(url, json=body, headers=headers, timeout=120, allow_redirects=False)
            if response.status_code == 403:
                # Only classify known authorization failures. Never log model
                # context, signed tokens, arbitrary response text or headers.
                reason = "upstream_forbidden"
                try:
                    failure = response.json()
                    detail = str(failure.get("detail") or failure.get("message") or "")
                    if detail in {
                        "Verified specialist and authorized execution grant required",
                        "Coordinator action is not allowed",
                        "Assessment shortcut does not match the signed request",
                        "Egress request is not authorized.",
                    }:
                        reason = detail
                except (ValueError, AttributeError):
                    pass
                # Upstream denial bodies contain protocol diagnostics rather
                # than the submitted context. Redact credential-shaped values.
                import re
                diagnostic = response.text[:1600]
                diagnostic = re.sub(r"(?i)(bearer\s+|key=|access_token=)[^\s&<]+", r"\1[redacted]", diagnostic)
                diagnostic = re.sub(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+", "[redacted-jwt]", diagnostic)
                logger.warning("coordinator_ingress_denied host=%s path=%s reason=%s diagnostic=%s", destination.hostname, destination.path, reason, diagnostic)
            response.raise_for_status()
            return response.json()
    with AuthorizedSession(credentials) as session:
        session.configure_mtls_channel()
        response = session.post(url, json=body, headers=headers, timeout=120, allow_redirects=False)
        if response.status_code == 403:
            # Google API ingress errors contain authorization diagnostics, not
            # the request body. Log only its message and known RPC reason fields.
            try:
                payload = response.json()
                failure = (payload[0] if isinstance(payload, list) and payload else payload).get("error", {})
                message = str(failure.get("message", ""))[:1000]
                import re
                message = re.sub(r"(?i)(bearer\s+|key=|access_token=)[^\s&]+", r"\1[redacted]", message)
                logger.warning("runtime_ingress_denied message=%s reasons=%s", message, [item.get("reason") for item in failure.get("details", []) if isinstance(item, dict) and item.get("reason")])
            except (ValueError, AttributeError):
                logger.warning("runtime_ingress_denied non_rpc_response=true")
        response.raise_for_status()
        return response.json()


async def invoke_remote(kind, context, user_id):
    allow_call(current_agent.get(), kind)
    context = clean(context)
    grant = execution_grant.get()
    if current_agent.get() == "api":
        grant = issue(kind, context, user_id)
    if not grant:
        raise PermissionError("API-issued execution grant required")
    url = endpoints().get(kind)
    if not url:
        raise RuntimeError("Configure the specialist runtime endpoint")
    result = await asyncio.to_thread(post, url, {"context": context, "user_id": user_id, "grant": grant})
    # Validate again at the application boundary before durable workers save it.
    from backend.agents.runner import REGISTRY
    schema = REGISTRY[kind].SCHEMA
    if schema:
        return schema.model_validate(result).model_dump()
    if not isinstance(result, dict) or not isinstance(result.get("message"), str) or not result["message"].strip():
        raise ValueError("Deployed agent returned an invalid conversation response")
    if not isinstance(result.get("actions", []), list) or not isinstance(result.get("sources", []), list):
        raise ValueError("Deployed agent returned invalid conversation metadata")
    return result
