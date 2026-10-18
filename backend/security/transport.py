"""Metadata-issued Agent Identity token; no downloaded service account key."""
from backend.cloud.config import required


def workload_token():
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    # This application verifies the token itself. Cloud Run invocation, when used,
    # requires a separate audience-specific Authorization token at the ingress.
    credentials = id_token.fetch_id_token_credentials(required("OPENCLASS_IDENTITY_AUDIENCE"))
    credentials.refresh(Request())
    return credentials.token


def ingress_token(audience):
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    # HTTPX uses ordinary TLS. Explicit per-request unbound token as documented
    # for standard run.app endpoints; application also verifies the SPIFFE token.
    return id_token.fetch_id_token(Request(), audience, bind_id_token=False)
