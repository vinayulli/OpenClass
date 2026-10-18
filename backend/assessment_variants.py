"""Shared assessment scope with distinct, reviewable question variants per learner."""
import re
import unicodedata


class DuplicateVariantError(ValueError):
    pass


SCENARIOS = ["a library checkout system", "a small shopping basket", "a course enrollment tool", "a delivery tracker", "a game inventory", "an appointment calendar", "a weather-reading service", "a music playlist", "a banking ledger", "a laboratory sample tracker"]


def variant_spec(index, total, batch_id):
    return {"index": index+1, "total": total, "batch_id": batch_id, "scenario": SCENARIOS[index % len(SCENARIOS)], "instruction": "Create distinct question stems, examples and code/data for this variant while preserving exactly the shared concepts, objectives, difficulty, question count and marks. Do not personalize topic selection or difficulty from learner mastery. Changing option order or names alone is not sufficient. Do not include learner identities in question text."}


def normalized_prompt(text):
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def reject_repeated_questions(questions, sibling_exams):
    previous = {normalized_prompt(q["prompt"]) for exam in sibling_exams for q in exam["questions"]}
    if any(normalized_prompt(q["prompt"]) in previous for q in questions):
        raise DuplicateVariantError("Variant repeats a question from another learner in this batch")
