"""Verify Google Agent Identity OIDC tokens against a pinned trust domain."""
import json
import os
import re
from functools import lru_cache
from backend.cloud.config import required
from .policy import allow_call


def managed():
    mode = os.getenv("OPENCLASS_GOVERNANCE_MODE", "local")
    if mode not in {"local", "managed"}:
        raise RuntimeError("OPENCLASS_GOVERNANCE_MODE must be local or managed")
    return mode == "managed"


def principal_map():
    value = json.loads(required("OPENCLASS_WORKLOAD_PRINCIPALS"))
    if not isinstance(value, dict) or not value or not all(isinstance(subject, str) and subject.startswith("spiffe://agents.global.") for subject in value.values()) or len(set(value.values())) != len(value):
        raise RuntimeError("Configure a distinct verified principal for every workload")
    return value


def issuer():
    value = required("OPENCLASS_IDENTITY_ISSUER")
    if not re.fullmatch(r"https://sts\.googleapis\.com/v1/(projects|organizations)/[0-9]+/locations/global/workloadIdentityPools/[A-Za-z0-9.-]+", value):
        raise RuntimeError("Pin the Google STS workload identity pool issuer")
    return value


@lru_cache(maxsize=4)
def key_client(trusted_issuer):
    from jwt import PyJWKClient
    return PyJWKClient(trusted_issuer+"/openid/jwks", lifespan=3600, timeout=10)


def verify_assertion(assertion):
    import jwt
    trusted = issuer()
    key = key_client(trusted).get_signing_key_from_jwt(assertion).key
    return jwt.decode(assertion, key, algorithms=["RS256"], issuer=trusted,
                      audience=required("OPENCLASS_IDENTITY_AUDIENCE"),
                      options={"require": ["exp", "iat", "sub", "iss", "aud"]})


def caller_from_headers(headers):
    claims = verify_assertion(headers.get("x-openclass-workload-token", ""))
    # The mapping is operator configuration based on verified deployed identities.
    # No caller identity is taken from an unverified application header.
    for agent, principal in principal_map().items():
        if claims["sub"] == principal:
            return agent
    raise PermissionError("Unregistered workload identity")


def authorize_peer(headers, destination):
    caller = caller_from_headers(headers)
    allow_call(caller, destination)
    return caller
