"""Actionable API errors without printing request secrets."""
import re


def describe_error(response, url, payload=None):
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict):
        error = {}
    parts = [f"GCP operation failed: HTTP {response.status_code} at {url.split('?')[0]}"]
    if error.get("status"):
        parts.append(str(error["status"]))
    for detail in error.get("details", []):
        if not isinstance(detail, dict):
            continue
        if detail.get("reason"):
            parts.append("reason="+str(detail["reason"]))
        metadata = detail.get("metadata", {})
        if isinstance(metadata, dict):
            for key in ("service", "permission", "consumer"):
                if metadata.get(key):
                    parts.append(f"{key}={metadata[key]}")
    message = str(error.get("message", ""))
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
    for value in sorted(strings(payload), key=len, reverse=True):
        if value:
            message = message.replace(value, "[request value redacted]")
    message = re.sub(r"(?i)Bearer\s+[^\s,;]+", "Bearer [redacted]", message)
    if message:
        parts.append(message[:1000])
    if response.status_code == 403:
        parts.append("Verify the ADC identity has project access. gcloud login and application-default login use separate credentials. Check the reason/service above for disabled APIs or quota-project permissions.")
    return "\n".join(parts)
