"""Model Armor input/output inspection with a fail-closed decision boundary."""
import asyncio
import re
from .config import enabled, required


class ContentBlocked(ValueError):
    pass


def decision(result):
    # Accept only an explicit successful clean result, including each filter execution.
    if result.get("invocationResult") != "SUCCESS" or result.get("filterMatchState") != "NO_MATCH_FOUND":
        raise ContentBlocked("Content was blocked or could not be safely inspected")
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "executionState" and item != "EXECUTION_SUCCESS":
                    raise ContentBlocked("A security filter did not complete")
                if key == "matchState" and item == "MATCH_FOUND":
                    raise ContentBlocked("Content was blocked by a security filter")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(result.get("filterResults", {}))


async def inspect(text, direction="input"):
    if not enabled("MODEL_ARMOR_ENABLED"):
        if enabled("OPENCLASS_REQUIRE_GOVERNANCE"):
            raise RuntimeError("Model Armor is required but disabled")
        return
    template = required("MODEL_ARMOR_TEMPLATE")
    match = re.fullmatch(r"projects/[^/]+/locations/([a-z0-9-]+)/templates/[^/]+", template)
    if not match:
        raise RuntimeError("MODEL_ARMOR_TEMPLATE must be a full template resource name")
    def call():
        from google.cloud import modelarmor_v1
        from google.protobuf.json_format import MessageToDict
        client = modelarmor_v1.ModelArmorClient(client_options={"api_endpoint": f"modelarmor.{match[1]}.rep.googleapis.com"})
        try:
            data = modelarmor_v1.DataItem(text=text)
            if direction == "input":
                response = client.sanitize_user_prompt(request=modelarmor_v1.SanitizeUserPromptRequest(name=template, user_prompt_data=data), timeout=20)
            else:
                response = client.sanitize_model_response(request=modelarmor_v1.SanitizeModelResponseRequest(name=template, model_response_data=data), timeout=20)
            result = MessageToDict(response._pb).get("sanitizationResult", {})
            decision(result)
        finally:
            client.transport.close()
    await asyncio.wait_for(asyncio.to_thread(call), timeout=25)


async def inspect_context(context):
    """Screen the whole untrusted model context, including history and metadata.

    System instructions live on the agent and are never part of this payload.
    Server workflow policy and private transport fields are excluded. Never
    truncate a large context and accidentally send an uninspected suffix.
    """
    import json
    payload = json.dumps({key: value for key, value in context.items() if key != "workflow_policy" and not key.startswith("_")}, ensure_ascii=False)
    if enabled("MODEL_ARMOR_ENABLED") and len(payload.encode()) > 250_000:
        raise ContentBlocked("Reduce source context before security inspection")
    await inspect(payload)
