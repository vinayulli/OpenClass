# A2A delegation and long-running assessment tasks

Classroom Advisor delegates assessment generation through an A2A **0.3 JSON-RPC HTTP profile**, validated using the official `a2a-sdk` 0.3.x models. The current deployment cohosts the agent HTTP endpoint and application in FastAPI; this is a real HTTP handoff, not an in-process function call disguised as A2A. The Assessment Generator still runs its dynamic ADK workflow internally.

Supported protocol operations are `message/send` (non-blocking), `tasks/get`, `tasks/cancel`, and constrained push-notification configuration set/get/list. SSE and arbitrary webhook URLs are not supported. This is a versioned application profile, not a claim of implementing every A2A version or optional operation. See the [A2A 0.3 specification](https://a2a-protocol.org/v0.3.0/specification/).

```mermaid
sequenceDiagram
    actor Teacher
    participant Advisor as Classroom Advisor workflow
    participant SQL as Cloud SQL task queue
    participant Dispatcher as A2A dispatcher
    participant Agent as Assessment A2A endpoint
    participant Workers as Bounded generation workers
    participant Gemini
    participant Hook as Completion webhook
    participant UI as Browser notifications and batch progress
    Teacher->>Advisor: Generate tests for selected learners
    Advisor->>SQL: Authorize recipients, validate blueprints, persist jobs
    Advisor-->>Teacher: Queued job or batch ID
    Dispatcher->>SQL: Claim pending dispatch
    Dispatcher->>Agent: message/send, blocking=false, pushNotificationConfig
    Agent->>SQL: Persist idempotent submitted task
    Agent-->>Dispatcher: A2A Task, state=submitted
    par Independent learner tasks up to configured limit
        Workers->>SQL: Claim leased task under global concurrency gate
        Workers->>Gemini: Assessment dynamic workflow with learner-scoped session
        Gemini-->>Workers: Structured questions
        Workers->>SQL: Validate and save draft, terminal task and webhook outbox
    end
    Workers->>Hook: Authenticated POST of terminal A2A Task
    Hook->>SQL: Validate persisted result; finalize job once; notify teacher
    UI->>SQL: Authorized API polling
    SQL-->>UI: Per-learner progress, draft IDs and completion notifications
```

## Ten students and concurrency

### Standard concepts with individual question variants

Teachers can ask Classroom Advisor: **Generate a standard test on functions for everyone, with different questions for each student.** The `request_class_test_variants` tool resolves the current course's enrolled roster and delegates one batch. An explicit whole-class request is required; missing concepts should prompt clarification. A selected subgroup can use `request_student_tests` with explicit shared concept IDs.

The teacher UI also provides **Generate / assign tests → Same concepts / different questions**. Choose the shared concepts, question count and difficulty, then generate for all enrolled students. Each student gets a separate draft; the teacher reviews and publishes each one.

A batch with an explicit common-concept blueprint uses `standard_variants` mode. Every child preserves the concepts, count, marks, duration, difficulty and question types. Individual Twins do not select topics or change difficulty in this mode. Each child receives a distinct variant index and scenario brief, plus question stems from already saved sibling variants to avoid repeating them. Formal variants retain a common blueprint without a personalized `student_id`; the saved exam's assigned recipients identify its student.

Draft saving takes a transaction-scoped batch lock and rejects normalized question text already saved for another student in that batch. This catches exact and punctuation/case-only repeats even when workers generate concurrently. A rejected variant becomes a failed task with an explicit teacher-facing error; it is not silently accepted or automatically regenerated with another paid model call. Distinct wording does not prove semantic diversity or equivalent difficulty, so teacher review remains required. Weakness-based batches without explicit shared concepts keep their existing personalized behavior.

Selecting ten students creates ten independent tasks, not one shared model conversation. The default `A2A_MAX_CONCURRENCY=3` permits three active generators, with the other seven queued. Claiming uses PostgreSQL locks and leases, so the active-task limit is shared across API processes. The effective limit reserves two application database-pool slots for other requests; raise the database pool and model quota budget deliberately if increasing concurrency.

Dynamic workflows provide conditional routing and checks. They do not automatically provide a durable queue, parallel capacity, retry semantics or callback security; these are explicit application components.

Each personalized assessment uses the selected student's organization/course/assessment session key. Multiple learners no longer compete for a single teacher assessment-session lock. The calling teacher remains the job owner and the authority for review/publication.

## Teacher interface

In **Classroom Advisor**, choose batch recipients and use **Prepare tests for N selected learners**. The standard shortcut goes through a deterministic scheduling branch, with defaults of five MCQs, ten marks, twenty minutes and beginner difficulty per draft. Each student's weakest evidenced concepts are selected independently; absent evidence leads to broad diagnostic coverage. Custom teacher requirements use the Advisor's reasoning/tool branch and retain the supplied settings.

Alternatively, open **Generate / assign tests → Generate personalized batch**, select recipients and generate. The UI shows each learner's task state and completed/failed counts. Completed drafts appear under Assessments. A webhook failure has a retry action. Only a teacher can approve and publish.

A number alone, such as “ten students,” does not authorize guessing recipients. Select students, name them, or provide an explicit selection rule. Duplicate or out-of-course recipients are rejected. Personalized batches do not create individually adapted formal exams; use a common blueprint and the existing assignment flow for formal assessment.

## Durability and security

PostgreSQL stores `job`, `assessment_batch`, `a2a_task` and `a2a_delivery` records. Queue dispatch survives HTTP request completion and API restarts. A worker that stops while processing leaves a 180-second lease; another worker can reclaim the task after expiry. Crash recovery is bounded to three claims. Successful drafts use deterministic IDs so replay does not create another exam. Explicit model/schema failures report failure rather than repeatedly charging for automatic repair attempts.

Dispatch has five delivery attempts. Terminal callbacks use an outbox with up to eight attempts and exponential backoff. Callback delivery is at least once; the receiver authenticates a task-specific bearer credential, checks the payload against the persisted terminal result, and finalizes/announces the result once. Replayed callbacks do not create duplicate notifications or grades. The UI polls authorized application APIs; the webhook is server-to-server, not a browser callback.

Teacher batch API requests support `Idempotency-Key`. Reusing a key for the same request returns the existing batch; using it for a different payload returns a conflict. The batch form retains a failed request's key for retry.

The A2A service uses a workload bearer secret. Only the administrator-configured callback URL and task-specific credential are accepted, preventing model-controlled callback destinations. Callback payloads carry draft references, not answer keys. Agent Cards contain capability metadata but no credentials. Production URLs require HTTPS. Loopback HTTP is permitted only in demo mode. Drain outstanding callbacks before rotating the shared secret; this version does not provide a dual-key rotation grace period.

## Local configuration and endpoints

```env
A2A_ASSESSMENT_URL=http://127.0.0.1:8000/a2a/assessment
A2A_CALLBACK_URL=http://127.0.0.1:8000/api/a2a/webhook
A2A_MAX_CONCURRENCY=3
DB_POOL_MAX=6
```

Demo mode generates a service secret in ignored `deployment/a2a.local.json` if `A2A_SHARED_SECRET` is unset. Production requires an explicit secret of at least 32 characters, supplied through Secret Manager/environment configuration. For separately hosted endpoints, configure the shared Cloud SQL access and workload credentials consistently. The local secret file is not a cloud secret-management strategy. This service secret does not establish GEAP Agent Identity or Gateway enforcement.

| Endpoint | Purpose |
| --- | --- |
| `GET /a2a/assessment/.well-known/agent-card.json` | Public capability metadata |
| `POST /a2a/assessment` | Authenticated A2A JSON-RPC |
| `POST /api/a2a/webhook` | Authenticated terminal task callback |
| `POST /api/courses/{id}/assessment-batches` | Teacher-authorized batch submission; HTTP 202 |
| `GET /api/assessment-batches/{id}` | Owning teacher's per-task progress |
| `POST /api/jobs/{id}/retry-webhook` | Owning teacher retries exhausted callback delivery |

## Deployment considerations

The workers currently run with the FastAPI process. The SQL queue is durable, but it cannot wake a scaled-to-zero service by itself. Run an always-on worker/worker pool, or deploy the cohosted demo with at least one instance and CPU allocated outside request handling. Cloud Run's default request-only CPU scheduling is insufficient for reliable background generation. Worker roles can be separated operationally later; this change does not provision new cloud infrastructure.

Model quotas, database capacity and worker availability bound throughput. The durable job records are not a guarantee that a model request will finish within a fixed time. Monitor dispatch/model/callback failure types and queue age, and rotate workload secrets through a coordinated deployment.

## Learning Coach and quick requests

“Summarize my progress” uses a deterministic workflow node over the authenticated learner's Twin. It does not wait for Gemini or long-term memory, and explicitly identifies PostgreSQL evidence as its source. General coaching still uses Gemini, private progress tools, and scoped GEAP memory, with bounded memory retrieval and visible failure/availability status. Custom questions and custom test specifications are not replaced with shortcut defaults.

Interactive Advisor/Coach workflows use temporary graph checkpoints by default to avoid repeated Cloud SQL checkpoint round trips. The final chat response and stable session ID remain durable in PostgreSQL, and subsequent prompts include the recent stored conversation plus current authorized evidence and optional GEAP memories. Set `ADK_PERSIST_INTERACTIVE_CHECKPOINTS=true` if every interactive ADK checkpoint must also be stored. Assessment reasoning and other non-interactive specialists retain durable ADK sessions; A2A task leases/outboxes remain durable independently. In a live local run, skipping shortcut checkpoints reduced the exact Coach progress-summary request from about 75 seconds during generation load to about 11 seconds afterward; these are individual observations, not a latency guarantee.

Live validation also completed two concurrent Gemini assessment tasks and Jamie Chen's separate request through the A2A callback path. All three terminal task callbacks were authenticated and delivered on their first attempt. Ten-task bounded concurrency is additionally tested offline with fake model calls; that is not a claim of a live ten-request load test.

## Tests

```powershell
uv sync --extra cloud --group dev
uv run pytest -q
node --test frontend/src/navigation.test.mjs
```

The offline A2A tests validate SDK contracts, service/callback authentication, callback destination restrictions, replay-safe completion, ten independent learner tasks with three concurrent fake model calls, and shortcut boundaries. Those tests do not establish live model quality or production delivery reliability. Live tests are reported separately when run.
