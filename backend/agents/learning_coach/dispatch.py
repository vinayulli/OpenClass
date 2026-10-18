"""Progress summaries use authoritative arithmetic, without model/tool round trips."""
PROGRESS_REQUESTS = {"summarize my progress", "summarise my progress", "what is my progress"}


def is_progress_request(message):
    return " ".join(message.casefold().strip().rstrip(".?!").split()) in PROGRESS_REQUESTS


def progress_summary(context):
    ranked = rank_summary(context)
    if ranked:
        return ranked
    twin = context.get("twin")
    if not twin or not is_progress_request(context.get("question", "")):
        return None
    mastery = twin.get("mastery")
    lines = ["Your progress in this class:", f"Recorded concept observations: {twin['evidence_count']}.", f"Evidenced mastery: {mastery}% (a provisional evidence average)." if mastery is not None else "Mastery is unknown because no assessed evidence is recorded yet."]
    for concept in twin["concepts"]:
        score = f"{concept['mastery']}%" if concept.get("mastery") is not None else "not assessed"
        lines.append(f"- {concept.get('name', concept['id'])}: {score}; {concept['evidence_count']} observations; {concept['status']}.")
    gaps = [c for c in twin["concepts"] if c["status"] == "requires review"]
    if gaps:
        lines.append("Next step: review "+", ".join(c.get("name", c["id"]) for c in gaps)+" and take a short reassessment.")
    elif any(c["status"] == "insufficient evidence" for c in twin["concepts"]):
        lines.append("Next step: take a diagnostic for concepts with insufficient evidence. Missing evidence is not low ability.")
    else:
        lines.append("Next step: apply the concepts in practice, then reassess to collect current evidence.")
    lines.append("This summary uses your course's PostgreSQL evidence. It does not need a long-term memory lookup or an LLM call.")
    return "\n".join(lines)


def is_rank_request(message):
    import re
    return bool(re.search(r"\b(?:my rank|rank in (?:the )?class|where do i rank)\b", message, re.I))


def rank_summary(context):
    if not is_rank_request(context.get("question", "")) or "class_performance" not in context:
        return None
    info = context["class_performance"]
    if info["your_rank"] is None:
        headline = "Your provisional class rank is not available yet: ranking requires evidence in every taught course concept and at least five comparable learners."
    else:
        headline = f"Your provisional progress rank is **{info['your_rank']} of {info['comparable_learners']}** learners with evidence across all taught course concepts. Equal mastery scores share a rank."
    mean = info["class_mean_mastery"]
    return headline+f"\n\nClass context: {info['enrolled_learners']} enrolled learners; {info['learners_with_evidence']} have recorded evidence."+(f" The mean evidenced mastery is {mean}%." if mean is not None else " The class average is withheld for a small evidence cohort.")+"\n\nThis compares provisional evidence averages, not final grades or ability. Students without comparable evidence are excluded rather than assigned zero. Your classmates' individual records remain private."
