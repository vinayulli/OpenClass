"""Exercise dynamic scheduling without Gemini, GCP, PostgreSQL or API keys."""
import asyncio
import pytest
from backend.agents.workflow import prepare, build_workflow


def test_diagnostic_branch_does_not_invent_missing_evidence():
    result = prepare("intervention", {"twin": {"evidence_count": 0}})
    assert result["workflow_policy"]["branch"] == "diagnostic"
    assert "do not infer" in result["workflow_policy"]["instruction"]
    assert prepare("intervention", {"twin": {"evidence_count": 4}})["workflow_policy"]["branch"] == "evidence_based"


def test_research_discards_private_academic_context():
    result = prepare("web", {"question": "Explain recursion", "learner_memories": ["private"], "twin": {"mastery": 50}})
    assert set(result) == {"question", "workflow_policy"}


@pytest.mark.parametrize("files", [[], [{"path": "empty.py", "content": "  "}]])
def test_empty_source_is_rejected(files):
    with pytest.raises(ValueError, match="source files"):
        prepare("code", {"repository": {"files": files}})


@pytest.mark.parametrize("empty,malformed", [(False, False), (True, False), (False, True)])
def test_workflow_gates_reasoning_and_output(monkeypatch, empty, malformed):
    from google.adk.workflow import FunctionNode
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from backend.cloud import model_armor
    calls = []

    async def noop(*args, **kwargs):
        pass

    monkeypatch.setattr(model_armor, "inspect", noop)
    monkeypatch.setattr(model_armor, "inspect_context", noop)

    def reason(node_input):
        calls.append(node_input)
        return {} if malformed else {"summary": "Visible source sample", "demonstrated_skills": [], "gaps": [], "references": [], "confidence": "low", "provisional_rating": None}

    sink = {}
    workflow = build_workflow("code", FunctionNode(name="fake_reasoner", func=reason), {"repository": {"files": [] if empty else [{"path": "a.py", "content": "1: pass"}]}}, None, sink)

    async def run():
        runner = InMemoryRunner(agent=workflow, app_name="test_dynamic")
        session = await runner.session_service.create_session(app_name="test_dynamic", user_id="test_user")
        try:
            async for _ in runner.run_async(user_id="test_user", session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text="review")])):
                pass
        finally:
            await runner.close()

    if empty or malformed:
        with pytest.raises(Exception):
            asyncio.run(run())
        assert "result" not in sink
        assert len(calls) == (0 if empty else 1)
    else:
        asyncio.run(run())
        assert sink["result"]["provisional_rating"] is None
        assert sink["branch"] == "static_review"
        assert len(calls) == 1
