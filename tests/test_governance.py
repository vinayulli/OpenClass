import pytest
from backend.cloud.memory import scope
from backend.cloud.model_armor import ContentBlocked, decision


def test_memory_scope_isolates_organization_course_and_learner():
    a = scope("org1", "course1", "student1")
    assert a == scope("org1", "course1", "student1")
    assert a != scope("org2", "course1", "student1")
    assert a != scope("org1", "course2", "student1")
    assert a != scope("org1", "course1", "student2")
    with pytest.raises(ValueError):
        scope("org1", "", "student1")


def test_model_armor_fail_closed():
    decision({"invocationResult": "SUCCESS", "filterMatchState": "NO_MATCH_FOUND", "filterResults": {"pi": {"executionState": "EXECUTION_SUCCESS", "matchState": "NO_MATCH_FOUND"}}})
    for result in ({}, {"invocationResult": "SUCCESS", "filterMatchState": "MATCH_FOUND"}, {"invocationResult": "FAILURE", "filterMatchState": "NO_MATCH_FOUND"}, {"invocationResult": "SUCCESS", "filterMatchState": "NO_MATCH_FOUND", "filterResults": {"pi": {"executionState": "EXECUTION_FAILED"}}}):
        with pytest.raises(ContentBlocked):
            decision(result)


def test_application_scope_tokens_cannot_be_tampered(monkeypatch):
    pytest.importorskip("jwt")
    from backend.cloud.capabilities import issue, verify
    monkeypatch.setenv("MCP_CONTEXT_SECRET", "test-secret-with-more-than-thirty-two-characters")
    token = issue({"id": "student1", "org": "org1"}, "course1", "student1")
    assert verify(token)["student"] == "student1"
    parts = token.split('.')
    parts[1] = parts[1][::-1]
    with pytest.raises(Exception):
        verify('.'.join(parts))


def test_armor_covers_history_concept_metadata_and_feedback_without_transport_tokens(monkeypatch):
    import asyncio
    import json
    from backend.cloud import model_armor
    captured = []
    async def inspect(text, direction="input"):
        captured.append(json.loads(text))
    monkeypatch.setattr(model_armor, "inspect", inspect)
    context = {"history": [{"question": "untrusted old request"}], "course": {"concepts": [{"name": "untrusted concept title"}]}, "student_feedback": [{"comment": "untrusted feedback"}], "workflow_policy": {"instruction": "trusted branch instruction"}, "_mcp_context": "private-transport-token"}
    asyncio.run(model_armor.inspect_context(context))
    assert captured == [{key: value for key, value in context.items() if key not in {"workflow_policy", "_mcp_context"}}]
