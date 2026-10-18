"""One-time, non-destructive ten-learner upgrade of the built-in synthetic classroom."""
import json
from pathlib import Path
from backend.store import all_of, get, put, now, password_hash


def seed(conn):
    marker = "focused-demo-v1"
    if get(conn, "fixture_import", marker):
        return
    course = get(conn, "course", "python-foundations")
    if not course or course["org"] != "demo" or course["teacher_id"] != "teacher-demo":
        return
    fixtures = json.loads(Path(__file__).with_name("focused_demo.json").read_text(encoding="utf-8"))["students"]
    # Restrict this known synthetic course's roster; never delete accounts or past work.
    course["students"] = [s["student_id"] for s in fixtures]
    put(conn, "course", course)
    evidence = all_of(conn, "evidence")
    from backend.learning import learning_twin
    for row in fixtures:
        student_id = row["student_id"]
        account = get(conn, "user", student_id)
        if account and account.get("org") != "demo":
            raise RuntimeError("Focused demo student ID belongs to another organization")
        if not account:
            put(conn, "user", {"id": student_id, "name": row["name"], "email": "student@openclass.demo" if student_id == "student-1" else student_id.replace("-", "")+"@openclass.demo", "org": "demo", "role": "student", "password": password_hash("OpenClass123!")})
        elif account["name"].startswith("Demo Learner"):
            put(conn, "user", {**account, "name": row["name"]})
        for concept_id, score in row["concept_scores"].items():
            if any(e["course_id"] == course["id"] and e["student_id"] == student_id and e["concept_id"] == concept_id for e in evidence):
                continue
            for n in range(3):
                record = {"id": f"focused:{student_id}:{concept_id}:{n}", "course_id": course["id"], "student_id": student_id, "concept_id": concept_id, "source": "Synthetic diagnostic evidence", "source_id": marker, "score": score/100, "confidence": 1, "kind": "quiz", "at": now(), "synthetic": True}
                put(conn, "evidence", record)
                evidence.append(record)
        twin = learning_twin(conn, course, student_id, evidence=evidence)
        targets = sorted(twin["concepts"], key=lambda c: c["mastery"] if c["mastery"] is not None else -1)[:3]
        path_id = "focused-path:"+student_id
        path = {"id": path_id, "type": "path", "org": "demo", "course_id": course["id"], "student_id": student_id, "request": {"concept_ids": [c["id"] for c in targets], "question_count": 5}, "version": 1, "status": "completed", "created_at": now(), "updated_at": now(), "synthetic": True, "output": {"title": row["name"].split()[0]+"'s practice path", "rationale": "Handwritten demo path based on recorded concept evidence. Use feedback and regenerate to request a live Gemini update.", "steps": [{"concept_id": c["id"], "title": "Practice "+c["name"], "explanation": "Review the course reference and explain the idea in your own words.", "practice": "Write a small Python example demonstrating "+c["name"]+", then add a test for one edge case.", "completion_check": "Explain the design choice and predict what changes for a different input. Take a short reassessment for new mastery evidence.", "estimated_minutes": 15+i*5} for i,c in enumerate(targets)]}}
        if not get(conn, "self_study", path_id):
            put(conn, "self_study", path)
        put(conn, "learning_feedback", {**row["feedback"], "id": "focused-feedback:"+student_id, "path_id": path_id, "org": "demo", "course_id": course["id"], "student_id": student_id, "created_at": now(), "synthetic": True})
    put(conn, "fixture_import", {"id": marker, "synthetic": True, "created_at": now(), "students": 10})
