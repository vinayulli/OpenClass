"""Dynamic workflow entry point; reasoning prompts live in agent.py."""
from ..workflow import build_workflow


def build(reasoner, context, runtime, result_sink):
    return build_workflow('tutor', reasoner, context, runtime, result_sink)

