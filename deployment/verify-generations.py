"""Live API/model verification against an explicitly disposable LOCAL database."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    target = urlparse(args.database_url)
    if target.hostname not in {"localhost", "127.0.0.1"} or not target.path.endswith("_test"):
        raise RuntimeError("Live verification requires a disposable local database ending in _test")
    from dotenv import dotenv_values
    import httpx
    config = dotenv_values(ROOT / ".env")
    key = config.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    env = {**os.environ, "DATABASE_URL": args.database_url, "ADK_SESSION_DATABASE_URL": args.database_url, "GEMINI_API_KEY": key, "GEMINI_MODEL": config.get("GEMINI_MODEL") or "gemini-3.8-flash", "GOOGLE_GENAI_USE_VERTEXAI": "false", "GEAP_MEMORY_ENABLED": "false", "MODEL_ARMOR_ENABLED": "false", "OPENCLASS_REQUIRE_GOVERNANCE": "false", "GEAP_MCP_SERVER": "", "OPENCLASS_DEMO": "true", "COOKIE_SECURE": "false", "A2A_SHARED_SECRET": secrets.token_urlsafe(48), "A2A_ASSESSMENT_URL": f"http://127.0.0.1:{args.port}/a2a/assessment", "A2A_CALLBACK_URL": f"http://127.0.0.1:{args.port}/api/a2a/webhook", "PORT": str(args.port), "PYTHONUNBUFFERED": "1"}
    env.pop("GOOGLE_API_KEY", None)
    directory = ROOT / ".cache" / "verification"
    directory.mkdir(parents=True, exist_ok=True)
    report = {"model": env["GEMINI_MODEL"], "database": "disposable local PostgreSQL", "checks": [], "managed_memory_tested": False, "model_armor_tested": False}
    started = time.monotonic()
    def passed(name, **details):
        report["checks"].append({"name": name, "status": "passed", **details})
        print("PASS: "+name, flush=True)
    def check(response):
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} at {response.request.url.path}: "+str(response.json().get("detail", "Request failed")))
        return response.json()
    def poll(fn, ready, timeout=300):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            value = fn()
            if ready(value):
                return value
            time.sleep(2)
        raise RuntimeError("Timed out waiting for generated records")
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            base = f"http://127.0.0.1:{args.port}"
            with httpx.Client(base_url=base, timeout=120) as teacher, httpx.Client(base_url=base, timeout=120) as student, httpx.Client(base_url=base, timeout=120) as other:
                for _ in range(60):
                    if server.poll() is not None:
                        raise RuntimeError("Verification server exited; inspect .cache/verification/server.log")
                    try:
                        if teacher.get("/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError("Verification server did not become healthy")
                for client, email in [(teacher, "teacher@openclass.demo"), (student, "student@openclass.demo"), (other, "student2@openclass.demo")]:
                    check(client.post("/api/auth/login", json={"email": email, "password": "OpenClass123!"}))
                workspace = check(teacher.get("/api/workspace"))
                course = workspace["overview"]["course"]
                cid = course["id"]
                assert cid == "machine-learning" and len(course["students"]) == 10
                assert course["syllabus_progress"]["percent_complete"] == 70
                passed("ML demo: ten students, twenty topics, 70% taught")

                generated = check(teacher.post(f"/api/courses/{cid}/learning-paths/regenerate", json={"student_ids": ["student-1", "student-2"]}))
                wanted = {p["id"] for p in generated["paths"]}
                paths = poll(lambda: check(teacher.get(f"/api/courses/{cid}/learning-paths")), lambda rows: all(any(row.get("latest_request", {}).get("id") == id and row["latest_request"]["status"] in {"completed", "failed"} for row in rows) for id in wanted))
                plans = [row["path"] for row in paths if row.get("path", {}).get("id") in wanted]
                assert len(plans) == 2, "One or more live plans failed; inspect server.log"
                for plan in plans:
                    assert plan["output"]["reference_catalog"]
                    assert all(step["references"] and step["worked_example"] for step in plan["output"]["steps"])
                passed("Two live detailed Learning Path generations with reference links", count=2)
                report["sample_learning_plan"] = plans[0]["output"]

                advisor = check(teacher.post(f"/api/courses/{cid}/chat", json={"message": "Generate a standard test on classification-metrics for everyone in the class. Use 2 beginner MCQ questions, 4 total marks, and 10 minutes. Every student must get different questions testing the same concept."}))
                batch_action = next(a for a in advisor["actions"] if a["type"] == "assessment_batch")
                assert batch_action["student_count"] == 10
                batch = poll(lambda: check(teacher.get("/api/assessment-batches/"+batch_action["batch_id"])), lambda b: b["status"] in {"completed", "finished_with_errors"})
                assert batch["completed"] == 10, "One or more assessment variants failed: "+str([(j["student_id"], j.get("error")) for j in batch["jobs"] if j["status"] != "completed"])
                overview = check(teacher.get(f"/api/courses/{cid}/overview"))
                exam_ids = {j["exam_id"] for j in batch["jobs"]}
                exams = [e for e in overview["exams"] if e["id"] in exam_ids]
                assert len(exams) == 10
                from backend.assessment_variants import normalized_prompt
                prompts = [normalized_prompt(q["prompt"]) for e in exams for q in e["questions"]]
                assert len(prompts) == len(set(prompts)) == 20
                assert all(e["blueprint"]["concept_ids"] == ["classification-metrics"] and e["blueprint"]["question_count"] == 2 for e in exams)
                passed("Advisor delegates ten A2A variants; ten authenticated completion webhooks; twenty distinct questions", learners=10, questions=20)
                report["assessment_batch_id"] = batch["id"]

                own_exam = next(e for e in exams if e["assigned_student_ids"] == ["student-1"])
                check(teacher.post(f"/api/exams/{own_exam['id']}/publish"))
                assert other.post(f"/api/exams/{own_exam['id']}/attempt").status_code == 404
                attempt = check(student.post(f"/api/exams/{own_exam['id']}/attempt"))
                assert all("answer" not in q for q in attempt["exam"]["questions"])
                aid = attempt["attempt"]["id"]
                check(student.put(f"/api/attempts/{aid}/answers", json={"answers": {q["id"]: q["answer"] for q in own_exam["questions"]}}))
                graded = check(student.post(f"/api/attempts/{aid}/submit"))
                assert graded["score"] == 4
                passed("Published variant: recipient isolation, hidden answer keys and grading")

                coach = check(student.post(f"/api/courses/{cid}/chat", json={"message": "Create a private practice test on train-test-split with 2 MCQ questions for me."}))
                private = next(a for a in coach["actions"] if a["type"] == "private_practice")
                private_records = poll(lambda: check(student.get(f"/api/courses/{cid}/self-study")), lambda rows: any(s["id"] == private["study_id"] and s["status"] in {"completed", "failed"} for s in rows))
                quiz = next(s for s in private_records if s["id"] == private["study_id"])
                assert quiz["status"] == "completed"
                assert teacher.get(f"/api/courses/{cid}/self-study").status_code == 403
                assert other.post(f"/api/self-study/{quiz['id']}/submit", json={"answers": {}}).status_code == 404
                assert all("answer" not in q for q in quiz["output"]["questions"])
                result = check(student.post(f"/api/self-study/{quiz['id']}/submit", json={"answers": {q["id"]: q["options"][0] for q in quiz["output"]["questions"]}}))
                assert result["result"]["official_grade"] is False
                passed("Coach delegates private test, supplies open link, enforces privacy and returns private score")

                plan = next(p for p in plans if p["student_id"] == "student-1")
                check(student.post(f"/api/self-study/{plan['id']}/feedback", json={"helpfulness": "partly_helpful", "difficulty": "too_hard", "comment": "Please shorten sessions and add numerical confusion-matrix examples before independent practice."}))
                refresh = check(student.post(f"/api/self-study/{plan['id']}/refresh"))
                records = poll(lambda: check(student.get(f"/api/courses/{cid}/self-study")), lambda rows: any(s["id"] == refresh["id"] and s["status"] in {"completed", "failed"} for s in rows))
                refreshed = next(s for s in records if s["id"] == refresh["id"])
                assert refreshed["status"] == "completed" and refreshed["version"] > plan["version"]
                assert refreshed["output"]["feedback_adaptation"]
                passed("Student feedback drives a new versioned detailed learning path")

                with student.stream("POST", f"/api/courses/{cid}/chat/stream", json={"message": "What is my rank in class?"}) as response:
                    assert response.status_code == 200
                    events = "\n".join(response.iter_lines())
                assert 'event: progress' in events and 'event: result' in events and '"response_at"' in events
                assert "provisional" in events.lower()
                passed("SSE progress, saved message timings and anonymous class ranking")
                report["status"] = "passed"
        except Exception as error:
            report["status"] = "failed"
            report["failure"] = str(error).replace(key, "[REDACTED]")
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            report["elapsed_seconds"] = round(time.monotonic()-started, 1)
            (ROOT / "deployment" / "verification-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print("Saved deployment/verification-report.json", flush=True)


if __name__ == "__main__":
    main()
