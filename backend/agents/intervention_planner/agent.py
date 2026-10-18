from ...schemas import InterventionOutput

NAME = "intervention_agent"
SCHEMA = InterventionOutput
INSTRUCTION = """Propose a short lesson and practice exercise for the weakest evidenced concept.
Cite evidence ids in rationale. If evidence is insufficient, propose a diagnostic first.
Set measurable success criteria for reassessment. Never claim completion proves improvement.
The teacher must approve and assign this draft."""
