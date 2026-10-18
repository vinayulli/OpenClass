from ...schemas import ExamOutput

NAME = "assessment_generator"
SCHEMA = ExamOutput
INSTRUCTION = """Generate an assessment that exactly matches the supplied blueprint.
Cover every selected concept. Ground questions in supplied materials and exact course objectives.
Use distinct ids, exact total marks, and requested types and difficulty. Include answer keys,
rubrics, explanations and material_id for each question. With insufficient learner evidence,
use broad diagnostic questions rather than strong personalization. Formal exams use a common blueprint."""

INSTRUCTION += " If variant is supplied, produce the variant's distinct scenarios and question stems while keeping the exact common blueprint unchanged. Do not adapt topics or difficulty to the learner. Never repeat any avoid_question_prompts. Merely shuffling options or renaming variables does not make a new question. This is a separate assigned test for one student in a common-concept batch. Teacher review still checks semantic distinctness and equivalent difficulty."
