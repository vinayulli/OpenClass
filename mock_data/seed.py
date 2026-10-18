"""Explicit, insert-only import of validated mock data. Normal startup does not load it."""
import argparse
import os
from .validate import load, validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--legacy", action="store_true", help="Import the older, separate mock-academy fixture pack")
    args = parser.parse_args()
    if not args.legacy:
        from .machine_learning import fixture_records, seed
        fixture, records = fixture_records()
        print(f"Machine Learning demo: {len(fixture['learners'])} learners, 20 topics, 70% taught; {len(records)} synthetic records.")
        if not args.apply:
            print("No database writes. Add --apply to import; --legacy selects the archived fixture pack.")
            return
        from backend.store import db
        if os.getenv("OPENCLASS_DEMO", "true").lower() != "true":
            raise RuntimeError("Mock import requires OPENCLASS_DEMO=true")
        with db() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812417)")
            seed(conn)
        print("Machine Learning demo imported idempotently. Existing non-synthetic work was not overwritten.")
        return
    records = validate()
    if not args.apply:
        print(f"Validated {len(records)} records. No database writes. Add --apply to insert the separate mock-academy dataset.")
        return
    from backend.store import db, get, password_hash, put
    if os.getenv("OPENCLASS_DEMO", "true").lower() != "true":
        raise RuntimeError("Mock import requires OPENCLASS_DEMO=true")
    kinds = [("accounts.json", "user"), ("courses.json", "course"), ("evidence.json", "evidence"), ("exams.json", "exam"), ("interventions.json", "intervention"), ("attempts.json", "attempt"), ("coding_assignments.json", "coding_assignment"), ("code_reviews.json", "code_review")]
    inserted = skipped = 0
    with db() as conn:
        if not conn.execute("SELECT to_regclass('public.records')").fetchone()[0]:
            raise RuntimeError("Start the API once to initialize the schema before importing mock data")
        conn.execute("SELECT pg_advisory_xact_lock(7812406)")
        for filename, kind in kinds:
            for item in load(filename):
                existing = conn.execute("SELECT kind FROM records WHERE id=%s", (item["id"],)).fetchone()
                if existing:
                    row = get(conn, existing[0], item["id"])
                    if existing[0] != kind or not row.get("synthetic"):
                        raise RuntimeError("Fixture ID collides with another kind or non-synthetic record; no import committed")
                    skipped += 1
                    continue
                if kind == "user":
                    item["password"] = password_hash("MockClass123!")
                put(conn, kind, item)
                inserted += 1
    print(f"Inserted {inserted}; skipped {skipped} existing synthetic records. Existing records were not overwritten. No Gemini or GEAP memory calls.")


if __name__ == "__main__":
    main()
