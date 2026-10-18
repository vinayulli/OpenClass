"""Map deployed resource IDs to the platform's authenticated HTTP passthrough."""
import json
import os
import re
from backend.cloud.config import required
from backend.cloud.mcp_client import checked_url

KINDS = {"teacher", "tutor", "exam", "code", "path", "intervention", "web"}


def runtime_url(resource):
    match = re.fullmatch(r"projects/([a-zA-Z0-9-]+)/locations/([a-z]+-[a-z]+\d)/reasoningEngines/([a-zA-Z0-9_-]+)", resource)
    if not match:
        raise ValueError("Use a full deployed Agent Runtime resource name")
    region = match[2]
    return f"https://{region}-aiplatform.mtls.googleapis.com/reasoningEngines/v1/{resource}/api/invoke"


def endpoints():
    if os.getenv("OPENCLASS_AGENT_RESOURCES"):
        values = json.loads(required("OPENCLASS_AGENT_RESOURCES"))
        urls = {kind: runtime_url(resource) for kind, resource in values.items()}
    else:
        urls = json.loads(required("OPENCLASS_AGENT_URLS"))
    if set(urls) != KINDS:
        raise RuntimeError("Configure one endpoint for each of the seven deployed specialists")
    if len(set(urls.values())) != len(KINDS):
        raise RuntimeError("Specialist runtimes must have separate endpoints")
    return {kind: checked_url(url) for kind, url in urls.items()}
