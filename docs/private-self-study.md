# Private practice and learning paths

Students open **Private practice & paths**, choose one to five course topics, then request either a private MCQ practice test (up to ten questions) or an ordered learning path. Requests persist immediately and run in the background. Learning paths and path feedback are now shared with the course teacher for guidance and regeneration; private practice tests and their scores remain student-only. Progress is polled every five seconds; completion creates a student-only in-app notification.

The **Learning Path agent** lives in [`backend/agents/learning_path/`](../backend/agents/learning_path/) with separate instructions, structured output schema and dynamic workflow. It uses course prerequisites, materials and the student's Learning Twin to suggest ordered steps, practice tasks, time estimates and understanding checks. Unknown concept IDs fail validation. With limited evidence it takes a diagnostic-path branch. This is separate from the Intervention Planner, which drafts teacher-assigned support plans.

Private tests reuse the Assessment Generator's dynamic workflow and deterministic question/blueprint checks. They do not enter the teacher A2A assessment queue, `exam`, `attempt` or `evidence` records. They cannot be published or assigned by teachers through existing assessment APIs.

## Storage and privacy

PostgreSQL `records` entries with kind `self_study` store ID, type (`practice` or `path`), organization, course, owning student, topic request, lifecycle state, timestamps, processing lease, generated output and optional private result. Owner-only student endpoints list self-study records and submit private tests. Teacher accounts receive 403 on these private test APIs; a separate path-only teacher API exposes learning paths and path feedback without private tests or scores. another student cannot submit them. Teacher classroom analytics, learner details, audit events and Memory Bank synchronization do not consume these records. This is application access control, not encryption from database administrators.

Practice questions omit answer keys, explanations and rubrics until the student submits all selected options. The backend calculates and saves a private score and reveals explanations after submission. Resubmitting returns the existing result. It does not change official grades, mastery evidence or teacher dashboards.

Generation and answer submission pause during an active official assessment. Requests use course-enrollment checks and per-student rate limits. A row lease guards background processing; expired processing becomes a visible failure rather than silently retrying a model call. A failed generation can be requested again from the form. The backend must remain running for queued requests to complete.

API:

- `GET /api/courses/{course_id}/self-study`
- `POST /api/courses/{course_id}/self-study/practice`
- `POST /api/courses/{course_id}/self-study/path`
- `POST /api/self-study/{study_id}/submit`

These calls currently invoke the specialists inside the API process; they do not use A2A. They do not automatically retrieve long-term memories; the Learning Twin and course materials are their evidence inputs.


## Feedback-driven daily refresh

Teacher entry points are now labelled **AI learning plans** in the sidebar and **Generate AI learning plans** on the Learners page. Each learner's detail profile includes **Generate AI plan for this student** and **View AI learning plans**. The older Learning plans page links to the same generator. The generator clearly distinguishes handwritten **Synthetic starter plan** fixtures from completed **AI-generated plan** updates. Generation queues Gemini work; it does not merely reuse the starter fixture.

Paths have a version, prior completed path ID, request owner and timestamps. Students save helpfulness, difficulty and free-text feedback, then request an update. Teachers use **Student learning paths** to refresh one, selected or all enrolled students. The Learning Path agent receives up to 20 recent feedback entries plus current course evidence; comments are treated as untrusted data and inspected when Model Armor is enabled. Current completed paths remain available when a refresh is queued, processing or failed. Duplicate refreshes while a path is pending return that pending request.

A path becomes due for a refresh after 24 hours. This release provides manual refresh controls and a daily-due indicator; it does not run an automatic daily scheduler. Teacher endpoints: `GET /api/courses/{id}/learning-paths` and `POST /api/courses/{id}/learning-paths/regenerate` with optional `student_ids` (empty means all enrolled learners). Student endpoints: `POST /api/self-study/{path_id}/feedback` and `POST /api/self-study/{path_id}/refresh`.

## Coach delegation and classroom comparison

Learning Coach has an authorized `request_practice_test` tool. On an explicit student request, it persists a private practice job for the Assessment Generator and returns an **Open private test** action. The link opens that saved test while generation runs and shows questions when ready. This path uses the existing private worker, not the teacher A2A queue, and never publishes an official exam.

Coach receives anonymous classroom aggregates plus the student's own provisional competition rank among learners with evidence in every course concept. Equal scores share rank (1, 2, 2, 4). Ranking requires at least five comparable learners; averages require at least five learners with evidence. Unknown mastery is excluded rather than scored zero. No peer IDs, names or individual scores enter student-facing class context. These figures describe assessed evidence coverage and averages, not intelligence or final grades. Direct rank questions use deterministic arithmetic without a model or Memory Bank lookup.


## Detailed plans and references

New AI plans contain an evidenced starting point, learning goals, a suggested schedule, feedback adaptation and detailed steps. Each step includes objectives, prerequisites, an explanation, worked example, mistakes to avoid, practice task, self-check questions and a completion checkpoint. Lessons and supporting details expand on demand. Resource IDs are checked against a server-maintained catalogue; canonical URLs and source labels are attached by the server. Machine Learning plans link to course references and official scikit-learn guides. The model supplies reading guidance rather than invented reference URLs. URL availability can change; references do not imply the model browsed or executed their examples.

Provider output schemas use a simpler grammar while the application still validates the full detailed schema and curriculum/resource IDs before saving. This avoids provider rejection of unsupported schema constraints without accepting incomplete plans.
