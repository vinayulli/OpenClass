# Current default: Machine Learning

See [the recreated ten-student ML classroom](MACHINE_LEARNING.md). The default seed command and startup now use this dataset; the older fixture pack below requires `--legacy`.

# Synthetic classroom and agent fixtures

This folder contains an independent, reproducible dataset for demos, API development and agent architecture review. All people, accounts, observations, memory facts and model responses are synthetic. The `.test` email domain is reserved for examples. Agent responses are **handwritten expected-shape examples**, not captured Gemini responses or proof of model quality.

## Contents

| File | Contents / purpose |
| --- | --- |
| `manifest.json` | Version, counts and which files may be seeded |
| `accounts.json` | One educator and 40 learners in organization `mock-academy`; no password hashes or cloud credentials |
| `courses.json` | Python course with 30 learners and data literacy course with 20 learners; 10 learners overlap, exercising separate per-course profiles |
| `evidence.json` | 68 source-linked observations, including quiz and synthetic educator-reviewed coding evidence |
| `learning_twins.json` | Seven derived Python Learning Twin snapshots for known learning scenarios |
| `exams.json` | One diagnostic draft, two published historical tests and one published test targeted to learner 01 |
| `attempts.json` | Twelve synthetic graded attempts across two dates for assessment analytics |
| `coding_assignments.json` | One class coding assignment with instructions and concept mappings |
| `code_reviews.json` | One handwritten report with a provisional rating and source references |
| `interventions.json` | One educator-reviewable composition practice plan, initially a draft |
| `agent_cases/*.json` | One request context, handwritten output example and review criteria for each of the five specialist agents |
| `memory_examples.json` | Illustrative GEAP memory facts and synchronization statuses; no managed memory is created |
| `security_cases.json` | Cross-learner access, missing MCP scope, untrusted repository comments and insufficient-evidence scenarios |
| `validate.py` | Offline Pydantic, blueprint, relationship and real Twin-engine checks |
| `seed.py` | Explicit, transactional insert-only import; never loads during ordinary app startup |

The Python material supports both diagnostic questions. Exam answers are intentionally available in this developer fixture folder; do not serve these JSON files as public frontend assets. Student API responses still strip answer keys according to application policy.

## Review scenarios

| Learner | What to inspect |
| --- | --- |
| `mock-student-01` | Strong function/parameter evidence and weaker object-design/testing evidence |
| `mock-student-02` | No evidence; mastery must remain `null`, with no assumption of low ability |
| `mock-student-03` | Weak prerequisite evidence that can motivate foundational revision |
| `mock-student-04` | Consistent perfect synthetic observations across the Python concepts |
| `mock-student-05` | Two perfect function observations: provisional 100% but still insufficient evidence |
| `mock-student-06` | Moderate consistent observations, resulting in likely mastery |
| `mock-student-07` | Strong composition theory evidence and weak reviewed coding evidence: a possible theory-to-practice gap, not a calibrated diagnosis |

The current Twin engine aggregates concept scores. It does not itself diagnose theory-to-practice differences; the paired evidence gives an educator or intervention agent something concrete to inspect. The other learners have no fabricated mastery observations. Enrollment in two courses does not transfer evidence automatically between them.

## Generate and validate without cloud access

From the repository root:

```powershell
node scripts/generate-mock-data.mjs
node scripts/check-mock-data.mjs
uv run --python 3.12 python -m mock_data.validate
```

Generation uses a fixed timestamp and stable IDs. It only rewrites files inside this folder; it does not connect to PostgreSQL, call Gemini or create GEAP memories. The Node checker verifies JSON relationships and exam constraints. The Python validator additionally checks application schemas and compares snapshots with the actual Python Learning Twin engine.

Review `agent_cases/assessment.json` alongside `backend/agents/assessment.py`, and similarly for the other agents. Each case has `agent`, `context`, `example_output` and `review_criteria`. The `agent` values match the application runner registry. The coding case includes source text directly; its illustrative GitHub URL is not a real repository to fetch.

## Optionally import into the application database

Start the Auth Proxy and run the API once so its schema exists. With `OPENCLASS_DEMO=true`, first preview, then explicitly import:

```powershell
uv run --python 3.12 python -m mock_data.seed
uv run --python 3.12 python -m mock_data.seed --apply
```

Preview validates locally and performs no database operations. Apply connects to the database selected by your `.env`, inserts fixture records in one transaction and skips existing synthetic IDs. Three fixture tests are marked published so the demonstration is immediately usable; this is fixture state, not an executed publication workflow. Rerunning adds missing new records without duplicating or overwriting rows. No memory outbox entries or cloud memory requests are generated by this import.

Historical attempts illustrate submitted-score analytics and are deliberately not replayed into the baseline evidence defining the seven scenario snapshots. This preserves the missing/sparse-evidence examples; it is a synthetic presentation choice. Real new submissions update evidence and the Twin through the normal application path.

After import, sign in with:

| Role | Email | Initial password |
| --- | --- | --- |
| Educator | `teacher@mock.openclass.test` | `MockClass123!` |
| Learner | `student01@mock.openclass.test` through `student40@mock.openclass.test` | `MockClass123!` |

These accounts are separate from the original `teacher@openclass.demo` dataset created by startup. Sign into the new mock educator account to see these classes. The folder does not replace or reset existing data. Imported synthetic records live in the configured database but are separated by the mock organization; use this only with a development/demo database. No database import has been performed by the agent during this task.

## Limits

Forty fixture accounts are not a load-test result. Example memory statuses do not demonstrate a working GEAP deployment. Handwritten outputs do not prove prompt-injection resistance, grading correctness or fairness. Semantic model behavior needs live agent-quality evaluation with reviewed criteria; authorization and persistence need integration tests.


## Focused ten-student classroom

The default `teacher@openclass.demo` classroom now uses `focused_demo.json`: ten named students, five concept score profiles per student, and individual difficulty/helpfulness feedback. At startup with `OPENCLASS_DEMO=true`, `focused_demo.py` performs a one-time upgrade of the known `demo` / `python-foundations` classroom. It limits that classroom's roster to student-1 through student-10, fills missing evidence, and inserts one personalized handwritten path and one feedback record per student. Existing assessed evidence, accounts, submissions and past paths are not deleted or overwritten. Existing unused demo accounts remain stored but are not enrolled in this classroom. A fixture-import marker prevents repeated reseeding or resetting later enrollment changes.

All starter paths and feedback are synthetic fixtures, not Gemini-generated content. Teacher **Student learning paths ? Regenerate all 10 paths** queues ten live personalized updates from each student's current Twin and feedback. Students can save more feedback and choose **Update path from latest feedback**. Paths retain versions and previous completed versions while regeneration is in progress. The older separate `mock-academy` fixture pack is still available for explicit import; it is not the default ten-student classroom.
