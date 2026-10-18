"""Anonymous classroom aggregates; never expose another student's records to Coach."""
def summarize_class(twins, student_id):
    known = [t for t in twins if t.get("mastery") is not None]
    comparable = [t for t in known if t.get("taught_coverage", t.get("coverage")) == 100]
    own = next((t for t in twins if t["student_id"] == student_id), None)
    rank = 1+sum(t["mastery"] > own["mastery"] for t in comparable) if own in comparable and len(comparable) >= 5 else None
    return {"enrolled_learners": len(twins), "learners_with_evidence": len(known), "class_mean_mastery": round(sum(t["mastery"] for t in known)/len(known)) if len(known) >= 5 else None, "comparable_learners": len(comparable), "your_rank": rank, "ties_at_your_score": sum(t["mastery"] == own["mastery"] for t in comparable) if rank is not None else None, "method": "Provisional evidence-average ranking among students with evidence in every taught course concept; tied scores share a competition rank. Cohorts below five suppress rank and averages. Missing evidence is excluded, never scored zero. This is not a final grade or an ability ranking."}
