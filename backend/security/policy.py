import contextvars
import json
from functools import lru_cache
from pathlib import Path
import sys

current_agent = contextvars.ContextVar("openclass_current_agent", default="api")


@lru_cache(maxsize=1)
def policy():
    source = Path(__file__).resolve().parents[2]/"security"/"agent-policy.json"
    packaged = Path(sys.prefix)/"share"/"openclass"/"security"/"agent-policy.json"
    result = json.loads((source if source.exists() else packaged).read_text(encoding="utf-8"))
    if result.get("default") != "deny" or result.get("version") != 1:
        raise RuntimeError("Unsupported agent authorization policy")
    return result


def allow_call(caller, destination):
    if destination not in policy()["calls"].get(caller, []):
        raise PermissionError("Agent communication is not authorized")


def tools_for(agent, service):
    return policy()["tools"].get(agent, {}).get(service, [])


def allow_tool(agent, service, tool):
    if tool not in tools_for(agent, service):
        raise PermissionError("Agent tool access is not authorized")
