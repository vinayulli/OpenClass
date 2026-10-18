"""Allowlisted, credential-redacted Gemini error diagnostics (standard library only)."""
import os
import re


def redact(value):
    text = str(value)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"https?://\S+", "[URL omitted]", text)
    text = re.sub(r"AIza[\w-]+|AQ\.[\w.-]+", "[REDACTED]", text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return text[:2000]


def describe_error(error):
    payload = getattr(error, "response_json", None)
    if not isinstance(payload, dict):
        payload = {}
    data = payload.get("error", payload)
    if not isinstance(data, dict):
        data = {}
    lines = [f"FAIL: {type(error).__name__}; HTTP/code={redact(getattr(error, 'code', 'unavailable'))}"]
    for field in ("status", "message"):
        value = data.get(field) or getattr(error, field, None)
        if value:
            lines.append(f"{field}: {redact(value)}")
    for detail in data.get("details", []) or []:
        if not isinstance(detail, dict):
            continue
        for field in ("reason", "domain"):
            if detail.get(field):
                lines.append(f"{field}: {redact(detail[field])}")
        metadata = detail.get("metadata", {})
        if isinstance(metadata, dict):
            for field in ("service", "consumer", "permission"):
                if metadata.get(field):
                    lines.append(f"{field}: {redact(metadata[field])}")
    return "\n".join(lines)
