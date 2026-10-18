"""Reproducible ML classroom fixtures; preserve legacy classroom work by archiving its UI entry."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from backend.store import get, put, many_of, password_hash
from backend.learning import learning_twin
from backend.learning_resources import for_course


def stamp(days=0):
    return (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()


def fixture_records():
    fixture = json.loads(Path(__file__).with_name("machine_learning.json").read_text(encoding="utf-8"))
    course = {**fixture["course"], "created_at": stamp(45)}
    course["materials"] = [{**m, "created_at": stamp(20)} for m in course["materials"]]
    records = [("course", course)]
    evidence = []
    for learner in fixture["learners"]:
        student = learner["student_id"]
        records.append(("learner_profile", {"id": "ml-profile:"+student, "student_id": student, "course_id": course["id"], **learner["profile"], "synthetic": True}))
        for concept, score in learner["scores"].items():
            if score is None:
                continue
            for index, age in enumerate([15, 8, 2]):
                delta = [-.10, -.03, .05][index] if student in {"student-6", "student-10"} else [-.03, .02, .01][index]
                item = {"id": f"ml-evidence:{student}:{concept}:{index}", "student_id": student, "course_id": course["id"], "concept_id": concept, "score": round(max(0,min(1,score/100+delta)),2), "confidence": 1, "kind": "formative_check", "source": "Synthetic formative check", "source_id": f"ml-formative-{index+1}", "at": stamp(age), "synthetic": True}
                evidence.append(item)
                records.append(("evidence", item))
    resources = for_course(course)
    concepts = {c["id"]: c for c in course["concepts"]}
    for learner in fixture["learners"]:
        student = learner["student_id"]
        twin = learning_twin(None, course, student, evidence=evidence)
        targets = sorted((c for c in twin["concepts"] if c["teaching_status"] == "taught"), key=lambda c: c["mastery"] if c["mastery"] is not None else -1)[:3]
        steps = []
        for index, c in enumerate(targets):
            reference = next((r for r in resources if r["kind"] == "official_documentation" and c["id"] in r["concept_ids"]), resources[0])
            steps.append({"concept_id": c["id"], "title": ("Diagnose " if c["mastery"] is None else "Strengthen ")+c["name"], "learning_objectives": ["Explain "+c["name"]+" and justify its use in an ML experiment."], "prerequisites": [concepts[p]["name"] for p in c["prerequisites"]], "explanation": next(m["content"] for m in course["materials"] if c["id"] in m["concept_ids"]), "worked_example": "Compare an experiment that uses an untouched hold-out set with one that repeatedly checks test performance. Identify which decisions can use validation results and which final result must remain independent. Use the course reference to connect this experiment to "+c["name"]+".", "practice": "Create a small reproducible notebook focused on "+c["name"]+". State the prediction target, show your data split, include one baseline and explain one design decision. Follow your preferred practice format: "+learner["profile"]["preferred_practice"]+".", "common_mistakes": ["Treating training performance as evidence of generalization", "Interpreting missing assessment evidence as a demonstrated gap"], "self_check_questions": ["What evidence would convince you that your experiment generalizes?", "What changes when the target or class balance changes?"], "completion_check": "Submit the notebook and a short explanation; answer a follow-up question without referring to the worked example. Completion alone does not add mastery evidence.", "estimated_minutes": 20+index*5, "references": [{"resource_id": reference["id"], "purpose": "Read the relevant worked example, reproduce it with one changed input and explain the observed result."}]})
        path_id = "ml-path:"+student
        output = {"title": learner["name"].split()[0]+"'s Machine Learning path", "rationale": learner["profile"]["headline"]+". Priorities use taught topics only; planned syllabus topics are not counted as gaps.", "starting_point": learner["profile"]["observations"], "learning_goals": [s["learning_objectives"][0] for s in steps], "study_schedule": "Three focused study sessions this week, 20-30 minutes each. Record feedback after practice and reassess the selected topics.", "feedback_adaptation": learner["feedback"]["comment"], "steps": steps, "reference_catalog": resources}
        records.append(("self_study", {"id": path_id, "course_id": course["id"], "org": "demo", "student_id": student, "type": "path", "status": "completed", "version": 1, "request": {"concept_ids": [c["id"] for c in targets], "question_count": 5}, "created_at": stamp(2), "updated_at": stamp(2), "output": output, "synthetic": True}))
        records.append(("learning_feedback", {"id": "ml-feedback:"+student, "path_id": path_id, "course_id": course["id"], "org": "demo", "student_id": student, **learner["feedback"], "created_at": stamp(1), "synthetic": True}))
        for age in [15, 8, 2]:
            snapshot = learning_twin(None, course, student, evidence=[e for e in evidence if e["at"] <= stamp(age)])
            records.append(("twin_history", {**snapshot, "id": f"ml-twin:{student}:{age}", "at": stamp(age), "source_id": "ml-formative-history", "synthetic": True}))
    records.extend(assessment_records(course, fixture["learners"]))
    records.extend(coding_records(course, fixture["learners"]))
    return fixture, records


def assessment_records(course, learners):
    samples = [
        ("train-test-split", "Which data should remain untouched until final evaluation?", ["Test set", "Training set", "Validation folds", "All data combined"]),
        ("preprocessing", "Where should a scaler be fitted to avoid leakage?", ["On training data within each fold", "On all available data", "Only on test data", "On labels alone"]),
        ("cross-validation", "Why use validation folds during model selection?", ["Estimate generalization without tuning on the final test set", "Guarantee perfect accuracy", "Replace all training data", "Remove the need for a baseline"]),
        ("linear-regression", "What does ordinary linear regression predict?", ["A continuous target", "Only a cluster index", "Only binary labels", "A feature name"]),
        ("regression-metrics", "Which metric penalizes large residuals more strongly?", ["RMSE", "MAE", "Accuracy", "Recall"]),
        ("regularization", "What is a main purpose of regularization?", ["Limit model complexity to reduce overfitting", "Guarantee causal interpretation", "Fit test labels directly", "Eliminate validation"]),
        ("logistic-regression", "What converts classifier scores into predicted class labels?", ["A decision threshold", "A missing-value count", "An index name", "A training duration"]),
        ("classification-metrics", "Which metric measures TP divided by TP plus FN?", ["Recall", "Precision", "MAE", "R-squared"]),
        ("probability", "What can affect interpretation of a positive prediction?", ["The class base rate", "The notebook filename alone", "The color of a plot", "The number of markdown headings"]),
    ]
    result = []
    for batch, title in enumerate(["Validation and leakage check", "Regression and model complexity", "Classification and uncertainty"]):
        group = samples[batch*3:batch*3+3]
        exam_id = "ml-exam-"+str(batch+1)
        questions = [{"id": "q"+str(i+1), "prompt": prompt, "type": "mcq", "concept_id": concept, "objective": course["objectives"][2], "difficulty": "beginner", "marks": 2, "options": options, "answer": options[0], "rubric": "2 marks for the correct option, otherwise 0.", "explanation": next(m["content"] for m in course["materials"] if concept in m["concept_ids"]), "material_id": "ml-reference-"+concept} for i,(concept,prompt,options) in enumerate(group)]
        blueprint = {"title": title, "kind": "practice", "concept_ids": [q["concept_id"] for q in questions], "question_count": 3, "total_marks": 6, "duration_minutes": 15, "difficulty": "beginner", "question_types": ["mcq"], "release_feedback": True, "student_id": None}
        result.append(("exam", {"id": exam_id, "course_id": course["id"], "title": title, "blueprint": blueprint, "questions": questions, "status": "published", "created_at": stamp(12-batch*3), "published_at": stamp(11-batch*3), "source": "Synthetic teacher-authored example", "synthetic": True}))
        for i, learner in enumerate(learners):
            if any(learner["scores"].get(q["concept_id"]) is None for q in questions):
                continue
            answers, results = {}, []
            for j, q in enumerate(questions):
                correct = learner["scores"][q["concept_id"]] >= [40,65,80][(i+j)%3]
                answers[q["id"]] = q["options"][0 if correct else 1]
                results.append({"question_id": q["id"], "concept_id": q["concept_id"], "score": 2 if correct else 0, "marks": 2, "method": "objective", "feedback": "Correct" if correct else "Review the class reference"})
            result.append(("attempt", {"id": f"ml-attempt:{learner['student_id']}:{batch}", "student_id": learner["student_id"], "course_id": course["id"], "exam_id": exam_id, "status": "graded", "answers": answers, "results": results, "score": sum(r["score"] for r in results), "total_marks": 6, "started_at": stamp(10-batch*3), "deadline": stamp(10-batch*3), "submitted_at": stamp(10-batch*3), "synthetic": True}))
    return result


def coding_records(course, learners):
    result = []
    tasks = [("pipeline", "Leakage-safe baseline pipeline", ["preprocessing", "train-test-split"], "Build a reproducible scikit-learn pipeline. Split before fitting transforms, record a baseline, and explain how the held-out test set is protected."), ("metrics", "Classifier evaluation notebook", ["logistic-regression", "classification-metrics"], "Compare precision, recall and F1 at two thresholds. Include a confusion matrix, explain error costs and avoid relying on accuracy alone.")]
    for key, title, concepts, instructions in tasks:
        result.append(("coding_assignment", {"id": "ml-coding-"+key, "course_id": course["id"], "org": "demo", "teacher_id": "teacher-demo", "title": title, "instructions": instructions, "concept_ids": concepts, "student_ids": [], "status": "published", "schema_version": 1, "created_at": stamp(7), "synthetic": True}))
    for i, learner in enumerate(learners[:7]):
        student = learner["student_id"]
        sid = "ml-submission:"+student
        report_id = "ml-report:"+student
        failed = i == 6
        result.append(("assignment_submission", {"id": sid, "assignment_id": "ml-coding-pipeline", "course_id": course["id"], "org": "demo", "student_id": student, "url": "https://github.com/scikit-learn/scikit-learn", "status": "failed" if failed else "teacher_review_required", "attempt_number": 1, "review_id": None if failed else report_id, "error": "Synthetic example: repository access was unavailable. Retry with your own public project." if failed else None, "created_at": stamp(4), "updated_at": stamp(3), "lease_until": None, "schema_version": 1, "synthetic": True}))
        if not failed:
            rating = round(sum(v for v in learner["scores"].values() if v is not None)/sum(v is not None for v in learner["scores"].values()))
            result.append(("code_review", {"id": report_id, "submission_id": sid, "assignment_id": "ml-coding-pipeline", "student_id": student, "course_id": course["id"], "url": "https://github.com/scikit-learn/scikit-learn", "status": "teacher_review_required", "created_at": stamp(3), "scope": "Handwritten synthetic report; the linked public repository was not inspected to create this fixture.", "report": {"summary": learner["profile"]["headline"]+". Example report for a leakage-safe ML pipeline assignment.", "demonstrated_skills": ["Frames a prediction target", "Documents a reproducible experiment"], "gaps": [learner["profile"]["observations"]], "references": ["Synthetic notebook: baseline.ipynb, cells 3-7"], "confidence": "low", "provisional_rating": rating, "rating_rationale": "Illustrative source-sample estimate for a demo. Not an executed model evaluation or a final grade."}, "synthetic": True}))
    return result


def seed(conn):
    marker = "machine-learning-demo-v1"
    if get(conn, "fixture_import", marker):
        return
    fixture, records = fixture_records()
    snapshot = many_of(conn, tuple({"user", "course", *[kind for kind, _ in records]}))
    existing_records = {(kind, row["id"]): row for kind, rows in snapshot.items() for row in rows}
    pending = []
    for learner in fixture["learners"]:
        account = existing_records.get(("user", learner["student_id"]))
        if account and account.get("org") != "demo":
            raise RuntimeError("ML fixture user ID belongs to another organization")
        if not account:
            index = learner["student_id"].split("-")[-1]
            pending.append(("user", {"id": learner["student_id"], "name": learner["name"], "email": "student@openclass.demo" if index == "1" else "student"+index+"@openclass.demo", "org": "demo", "role": "student", "password": password_hash("OpenClass123!")}))
    for kind, record in records:
        existing = existing_records.get((kind, record["id"]))
        if existing and not existing.get("synthetic"):
            raise RuntimeError("ML fixture ID collides with existing non-synthetic work")
        if not existing:
            pending.append((kind, record))
    legacy = existing_records.get(("course", "python-foundations"))
    if legacy and legacy["org"] == "demo" and legacy["teacher_id"] == "teacher-demo":
        pending.append(("course", {**legacy, "archived": True}))
    with conn.pipeline():
        for kind, record in pending:
            put(conn, kind, record)
        put(conn, "fixture_import", {"id": marker, "synthetic": True, "students": 10, "at": stamp()})
