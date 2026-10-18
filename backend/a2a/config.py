import hashlib
import hmac
import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


@lru_cache(maxsize=1)
def shared_secret():
    secret = os.getenv("A2A_SHARED_SECRET", "")
    if secret:
        if len(secret) < 32:
            raise RuntimeError("A2A_SHARED_SECRET must have at least 32 characters")
        return secret
    if os.getenv("OPENCLASS_DEMO", "true").lower() != "true":
        raise RuntimeError("Configure A2A_SHARED_SECRET for agent service authentication")
    path = Path(__file__).resolve().parents[2] / "deployment" / "a2a.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump({"secret": secrets.token_urlsafe(48)}, stream)
        except FileExistsError:
            pass
    return json.loads(path.read_text(encoding="utf-8"))["secret"]


def trusted_url(value):
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError("Agent URLs cannot contain credentials or fragments")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (local and parsed.scheme == "http" and os.getenv("OPENCLASS_DEMO", "true").lower() == "true"):
        raise RuntimeError("Agent URLs require HTTPS; HTTP loopback is allowed only in demo mode")
    return value.rstrip("/")


def agent_url():
    return trusted_url(os.getenv("A2A_ASSESSMENT_URL", f"http://127.0.0.1:{os.getenv('PORT', '8000')}/a2a/assessment"))


def callback_url():
    return trusted_url(os.getenv("A2A_CALLBACK_URL", f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/a2a/webhook"))


def callback_token(job_id):
    return hmac.new(shared_secret().encode(), ("callback:"+job_id).encode(), hashlib.sha256).hexdigest()


def concurrency():
    return max(1, min(10, int(os.getenv("DB_POOL_MAX", "6"))-2, int(os.getenv("A2A_MAX_CONCURRENCY", "3"))))
