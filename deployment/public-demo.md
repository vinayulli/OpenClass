# Current demonstration data

The default demo is now **Machine Learning: from data to decisions**, with ten learners and 14 of 20 topics taught (70%). Use `teacher@openclass.demo` and `student@openclass.demo` with `OpenClass123!`. See [the ML data guide](../mock_data/MACHINE_LEARNING.md). The previous Python course is archived from the picker and its past work is preserved. The default `mock_data.seed` importer now selects ML; add `--legacy` only for the older mock-academy fixture pack described below.

Live verification is recorded in [verification-report.json](verification-report.json). It covers detailed learning plans, ten common-concept question variants, authenticated callbacks, grading, private Coach tests, feedback-driven plan updates and streamed responses against a disposable local PostgreSQL database. It does not verify managed Memory Bank or Model Armor enforcement.

# Publish a working OpenClass demo

The repository now includes a multi-stage Dockerfile that builds React and serves it from FastAPI on the same origin. A Cloud Run demo can use the existing Cloud SQL instance. This has **not been deployed or verified** by the agent session.

## First verify locally

```powershell
uv sync --extra cloud --python 3.12
docker compose --profile cloud up -d cloud-sql-proxy
uv run uvicorn backend.main:app --reload
```

In another terminal, import the enriched dataset into the configured demo database:

```powershell
uv run python -m mock_data.validate
uv run python -m mock_data.seed
uv run python -m mock_data.seed --apply
```

The insert-only import adds missing fixture records, including new historical tests/submissions and a coding assignment; it does not overwrite existing fixtures. Accounts are under `mock-academy`. Use `teacher@mock.openclass.test` or `student01@mock.openclass.test`, password `MockClass123!`. Existing startup demo accounts remain separate. Historical fixture marks are deliberately illustrative and are not replayed into baseline Twin evidence.

## What to demonstrate

1. Educator: open **Analytics** to inspect evidence coverage, mastery bands, assessed scores and support priorities.
2. Educator: use **Generate / assign tests** to generate a Gemini draft or write an MCQ test without AI. Select recipients, review the draft in Assessments, then publish.
3. Learner: complete an available published test. Saved answers, objective grading and new concept evidence demonstrate the working loop.
4. Educator: switch students in **Digital Twin**. Compare current evidence with a clearly labeled hypothetical reassessment. Completing a lesson alone does not increase mastery.
5. Educator: create a coding assignment. Learner: submit a public GitHub repository from **Coding assignments** and wait for its provisional AI sample rating and source references. Live execution requires Gemini credentials, external GitHub access and an available model; the agent does not execute code or award a final grade.
6. Open **Agents & sessions** to inspect the five specialists and current user's stable, course-scoped session IDs. Sessions are created lazily and persisted in PostgreSQL through ADK, rather than a separate model deployment per student.
7. Use the explicit **Log out** button in the top bar when switching roles.

## Enable GEAP Memory Bank

Memory Bank requires Google Cloud credentials and permissions independently of `GEMINI_API_KEY`.

```powershell
gcloud auth application-default login
gcloud auth application-default set-quota-project hackathon-506016
gcloud services enable aiplatform.googleapis.com --project=hackathon-506016
uv run --extra cloud python deployment/create-memory-bank.py
```

Set these backend environment variables, using the actual returned bank ID:

```dotenv
GOOGLE_CLOUD_PROJECT=hackathon-506016
GOOGLE_CLOUD_QUOTA_PROJECT=hackathon-506016
GOOGLE_CLOUD_LOCATION=us-central1
GEAP_MEMORY_BANK_ID=ACTUAL_RETURNED_ID
GEAP_MEMORY_ENABLED=true
```

Restart the API, submit new assessed evidence and inspect **Learning Twin / Digital Twin → Learner memories**. The sync worker records pending, synced or failed status. Existing imported mock evidence is not automatically copied to Google. Memory retrieval is course/learner scoped and may be eventually consistent. Failures require checking workload memory permissions and the configured region/bank. On Cloud Run, grant the actual workload the appropriate memory generation/retrieval permissions; local ADC login does not configure that service's IAM.

## Deploy a public synthetic demo

1. Authenticate gcloud to `hackathon-506016` and verify billing/build permissions. Add the Gemini API key as a Secret Manager version named **`openclass-gemini-api-key`** through the console; do not place it in frontend variables or shell command arguments. `openclass-db-password` already comes from PostgreSQL provisioning.
2. Verify the frontend build and deterministic tests locally. The deployment image installs the updated `google-adk[db]` and `asyncpg` dependencies for durable per-user agent sessions.
3. Review [`cloud-run-demo.env.yaml`](cloud-run-demo.env.yaml) and [`deploy-demo.ps1`](deploy-demo.ps1). The script creates a dedicated web service account, grants it Cloud SQL connection access and read access to the two named secrets, builds an Artifact Registry image, and deploys a public Cloud Run service.

```powershell
./deployment/deploy-demo.ps1
./deployment/deploy-demo.ps1 -Apply
```

The first command prints the plan. The second makes the documented cloud changes. Use a terminal whose execution policy permits your reviewed script; the project does not weaken the machine's execution policy.

The public service exposes the web login page; FastAPI still enforces authentication and course permissions for classroom APIs. `COOKIE_SECURE=true` protects cookies over Cloud Run HTTPS. Public demo accounts allow visitors to explore synthetic data and can incur AI usage; use a dedicated synthetic dataset, monitor usage and restrict or disable AI calls when sharing widely. Do not put real student records in this shared demo.

The initial demo runs **one always-on instance** (`min=1`, `max=1`, CPU not throttled) because generation tasks and limits remain process-local. It incurs running costs. This is a constrained hackathon deployment, not a scalable production worker architecture. Multiple API replicas require durable job ownership/queues and distributed limits first. ADK conversation sessions themselves persist in PostgreSQL; memory remains a separate GEAP service.

ADK conversation tables use a separate `openclass_adk` PostgreSQL schema so they cannot collide with the application's login `sessions` table. The application database user must be able to create that schema on first agent use, or an administrator must create it with the appropriate ownership beforehand.

The script prints the Cloud Run URL. Verify `/api/health`, public login, teacher/student boundaries, a complete exam flow and a code submission before sharing it. To roll back, move traffic to a known-good previous Cloud Run revision; do not revert or delete learning records.

## Managed governance deployment is separate

The demo web service runs ADK inside FastAPI. It does not become a governed Agent Runtime deployment merely by setting `GEAP_AGENT_GATEWAY`. Deploy the private MCP service, register its tools and configure IAP/Model Armor policies; then deploy a supported ADK managed runtime with Agent Identity and Gateway attachment and wire API-to-runtime invocation. That managed invocation adapter is still pending. See [the GEAP deployment plan](README.md).

References: [Cloud Run container deployment](https://docs.cloud.google.com/run/docs/deploying), [Cloud SQL from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-instance-cloud-run), [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets).
