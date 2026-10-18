"""Evidence-based dashboard metrics; missing evidence is counted separately."""
from collections import Counter


def classroom_metrics(twins, attempts, concepts):
    known = [t["mastery"] for t in twins if t["mastery"] is not None]
    graded = [a for a in attempts if a["status"] == "graded" and "score" in a and a.get("total_marks")]
    bands = Counter("no_evidence" if t["mastery"] is None else "review" if t["mastery"] < 60 else "developing" if t["mastery"] < 80 else "strong" for t in twins)
    dates = sorted({a.get("submitted_at", "")[:10] for a in graded})
    return {
        "learners": len(twins), "evidenced_learners": len(known),
        "average_mastery": round(sum(known)/len(known)) if known else None,
        "coverage": round(sum(t["coverage"] for t in twins)/len(twins)) if twins else 0,
        "evidence_count": sum(t["evidence_count"] for t in twins),
        "bands": {k: bands[k] for k in ("no_evidence", "review", "developing", "strong")},
        "submitted": len([a for a in attempts if a["status"] != "in_progress"]),
        "review_pending": len([a for a in attempts if a["status"] == "review_required"]),
        "average_assessment_score": round(sum(a["score"]/a["total_marks"]*100 for a in graded)/len(graded)) if graded else None,
        "assessment_trend": [{"date": day, "average": round(sum(a["score"]/a["total_marks"]*100 for a in graded if a.get("submitted_at", "")[:10] == day)/sum(a.get("submitted_at", "")[:10] == day for a in graded))} for day in dates if day],
        "concepts": [{"id": c["id"], "name": c["name"], "evidenced": sum(next(x for x in t["concepts"] if x["id"] == c["id"])["evidence_count"] > 0 for t in twins), "needs_review": sum(next(x for x in t["concepts"] if x["id"] == c["id"])["status"] == "requires review" for t in twins)} for c in concepts],
        "sources": dict(Counter(e["kind"] for t in twins for c in t["concepts"] for e in c["evidence"])),
        "note": "Concept source counts use the visible evidence window; bands include provisional mastery. Missing evidence is not low ability.",
    }


def simulate_concept(concept, action, assumed_score, observations):
    if action == "lesson_only":
        return {"current": concept["mastery"], "simulated": concept["mastery"], "additional_observations": 0, "note": "Completing a lesson adds no assessed evidence, so mastery does not change."}
    evidence = concept["evidence"]
    # The UI carries a bounded evidence window; expose that limitation explicitly.
    weight = sum(e["confidence"] for e in evidence)
    current_sum = sum(e["score"]*e["confidence"] for e in evidence)
    projected = round((current_sum+assumed_score*observations)/(weight+observations)*100)
    return {"current": concept["mastery"], "simulated": projected, "additional_observations": observations, "note": "Hypothetical arithmetic over visible recent evidence plus assumed future scores. This is not a prediction or a saved mastery update."}
