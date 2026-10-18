**Problem Statement**



1. document intelligence
2. how AI can transform operational data into meaningful insights, recommendations, or actions.
3. Personalized Adaptive Learning System - PAL in education
4. Enterprise Knowledge Assistants



Finalized --> **OpenClass AI - An open-source AI classroom companion for teachers and students**





OpenClass AI is an open-source AI learning intelligence platform that continuously understands how learners learn, identifies why they struggle, and helps educators deliver personalized interventions that measurably improve learning outcomes.





1. **UI**

   1. **Screens**

      1. **Teacher Screen**
      2. **Student Screen**
      3. **Logic Screen - Student/Teacher Selection**
      4. **Public Screen**
2. **Backend - Python FastAPI**

   1. **APIs**
3. **Data Models - We can't have a fixed i think. we need dynamic.**

   1. **Students**
   2. **Teacher**
   3. **Assessments**
   4. **Recommendations**
   5. **Class**
4. **Agents**

   1. **Teacher Agent**
   2. **Student Agent**
   3. **Intervention Agents**
   4. **Assessment Agent**
   5. **Coding Agent - Which assesses students codes provided in their repo and access the code quality as well and provides a report.**
   6. **Chat Agent**
5. **Memory**

   1. **Student Memories**
   2. **Teacher Memories**
   3. **Overall Memory**
6. **Skills**
7. **Deployment Options**

   1. **Firebase for app hosting**
   2. **Agent Runtime for Agents Deployment**
   3. **Agent Registry, Gateway for Agent Governance**
8. 





Functional Requirements

1. The system shall allow teachers to create a class and add the details about

   1. course details (including what are the objectives)

      1. objectives
      2. topics
      3. concepts
   2. add student details
2. System shall support organizations such as schools, universities, bootcamps and corporate learning programs.
3. System shall support Educator and Learner roles. So we will have to two login types - 1)educator 2)learner
4. Learners will have an Individual Learning Twin (something like individual memory)
5. Access to learner data shall be restricted according to organization/course permissions.
6. System shall map assessments, assignments and learning activities to concepts.
7. System shall maintain a Concept Graph representing relationships between concepts.
8. System shall support domain-specific content packs without changing the core platform logic.
9. Educators can upload/create

   1. MCQs
   2. Coding Questions
   3. Written questions
   4. Assignments
   5. Project evaluations
   6. practical assessments
10. System shall analyze learner responses and associate evidence with concepts.
11. System shall select subsequent questions based on the learner's current Learning Twin.
12. Educators can create a coding assignment registrations/tasks- with guidelines on what and how
13. Git repository ingestion - for assessing coding assignments
14. Code skill analysis - The system should not simply give a code quality score. It should infer what the learner actually knows.
15. Multi source learning twin - The learning twin should combine evidence from multiple sources like Quizzes, Exams, Coding Assignments, Projects etc.
16. Coding Misconception detection - The learner understands the theoretical concept of OOP but has difficulty applying composition and encapsulation in practical code.
17. 





Non Functional Requirements

1. Support 40+ Students





**Assumptions**



* Lets say we have a class room of 20 students and one teacher.
* This is about a graduate level course -







Things to Iterate

1. Learning Twin
2. 




OpenClass AI 

OpenClass AI — Project Overview
1. OpenClass AI is a standalone, AI-powered Learning Intelligence Platform designed to personalize learning and improve educational outcomes.
2. It builds a continuously evolving Learning Twin for every student, representing their knowledge, practical skills, misconceptions, and progress.
3. The platform supports one teacher managing multiple students through dedicated teacher and student web interfaces.
4. It uses Google Agent Development Kit (ADK) to implement collaborative AI agents.
5. Google Gemini models through Vertex AI power reasoning, tutoring, assessment analysis, and personalized content generation.
6. A central Orchestrator coordinates specialized agents for educator intelligence, student tutoring, coding analysis, and interventions.
7. The Learning Evidence Engine combines quiz results, assignments, projects, practice activities, and tutor interactions.
8. The platform integrates a Git MCP server to analyze coding assignments submitted through Git repository links.
9. Code Intelligence evaluates demonstrated programming concepts, code structure, testing practices, and software engineering skills.
10. The Concept Graph connects concepts and prerequisites to identify the root causes of learning difficulties.
11. The Learning Twin combines evidence from theoretical assessments and practical work to identify theory-to-practice gaps.
12. Every important learning diagnosis includes supporting evidence, confidence estimates, and an explanation.
13. The Intervention Engine generates personalized lessons, examples, exercises, and practice assessments for identified learning gaps.
14. Teachers review and approve AI-generated interventions before assigning them to students.
15. Students receive personalized learning recommendations, interactive tutoring, adaptive practice, and progress insights.
16. Reassessment measures changes in student performance and updates the Learning Twin with new evidence.
17. The platform uses Google Cloud Run for frontend and backend deployment, with Vertex AI Agent Engine Runtime as the target managed agent runtime.
18. An agent governance layer controls tool access, data permissions, external calls, and sensitive operations, while observability tracks agent execution, errors, latency, and usage costs.
19. Its domain-agnostic architecture is designed to support school education, university courses, programming bootcamps, professional training, and future LMS integrations such as Moodle.
20. OpenClass AI's mission: Understand every learner, personalize every intervention, and measure every improvement through evidence-based, explainable, and continuously evolving learning intelligence.



OpenClass AI — Functional and Non-Functional Requirements
Product vision: OpenClass AI is a standalone, AI-powered Learning Intelligence Platform that continuously understands each learner's knowledge, practical skills, learning pace, and gaps, then personalizes learning interventions and generates adaptive examinations to measure improvement.
The exam-generation capability should be a core product feature, not an add-on. OpenClass should generate assessments based on what a student has learned, how quickly they learn, which concepts they struggle with, and the evidence available about their mastery.
1. Functional requirements
Functional requirements define what OpenClass AI must do.
A. User management and class setup
ID	Requirement	Priority
FR-001	The system shall support teacher and student roles with role-based access control.	Must
FR-002	Teachers shall create classes, define subjects/courses, configure topics and learning objectives, and enroll students.	Must
FR-003	Students shall access only their own learning profiles, assessments, feedback, and progress.	Must
FR-004	Teachers shall view class-level performance, learner progress, concept mastery, and students needing intervention.	Must
FR-005	The system shall support configurable grading scales, assessment rules, and course completion criteria.	Should
FR-006	The system shall support multiple classes, subjects, and courses without requiring a separate product implementation for each domain.	Must
B. Learning content and curriculum intelligence
ID	Requirement	Priority
FR-007	Teachers shall add learning materials, notes, documents, questions, assignments, and reference resources.	Must
FR-008	The system shall extract or accept learning objectives, concepts, prerequisites, and expected competency levels from course content.	Must
FR-009	The system shall maintain a concept graph linking topics, prerequisites, related skills, and learning outcomes.	Must
FR-010	The system shall map learning activities, questions, and assignments to one or more learning objectives.	Must
FR-011	Teachers shall review and edit AI-generated learning objectives, question mappings, and concept relationships.	Should
FR-012	The system shall identify missing or insufficient evidence for a learning objective instead of assuming the student has mastered it.	Must
C. Student Learning Twin
The Learning Twin is the central learner model that informs tutoring, intervention, and adaptive exams.
ID	Requirement	Priority
FR-013	The system shall maintain a separate, continuously updated Learning Twin for each student and course.	Must
FR-014	The Twin shall track concept mastery, practical skills, learning history, assessment performance, and progress over time.	Must
FR-015	The Twin shall estimate confidence and evidence coverage for each mastery estimate.	Must
FR-016	The system shall identify misconceptions, recurring mistakes, prerequisite gaps, and theory-to-practice gaps.	Must
FR-017	The system shall estimate learning pace using historical performance, attempts, time taken where available, and improvement across activities.	Must
FR-018	The system shall distinguish between demonstrated mastery, likely mastery, insufficient evidence, and concepts requiring review.	Must
FR-019	Teachers and students shall be able to view appropriate explanations of why the Twin recommends a learning activity or assessment.	Must
FR-020	New assessment and assignment evidence shall update the Twin while preserving a history of previous states and the evidence behind changes.	Must
D. AI tutoring and personalized learning
ID	Requirement	Priority
FR-021	Students shall interact with an AI tutor that uses course content, learning objectives, and their Learning Twin as context.	Must
FR-022	The tutor shall adjust explanations, examples, and hints to the student's current understanding and preferred level of difficulty.	Must
FR-023	The system shall recommend next steps, revision topics, practice activities, and prerequisite lessons based on identified gaps.	Must
FR-024	The system shall generate personalized exercises with explanations and worked examples.	Must
FR-025	The tutor shall distinguish between helping a student learn and providing direct answers to restricted or graded assessments.	Must
FR-026	The system shall record relevant learning interactions as evidence where appropriate, without treating every conversational answer as proof of mastery.	Must
E. Adaptive exam and test generation — core capability
OpenClass should generate more than a fixed quiz. It should support practice tests, topic tests, diagnostic tests, revision tests, mock exams, and teacher-controlled graded assessments.
ID	Requirement	Priority
FR-027	Teachers shall generate exams by selecting a course, topic, learning objectives, duration, total marks, question count, and difficulty range.	Must
FR-028	Students shall be able to receive personalized practice tests generated from their own Learning Twin and learning history.	Must
FR-029	The system shall generate diagnostic tests to identify knowledge gaps, misconceptions, and prerequisite weaknesses.	Must
FR-030	The system shall generate revision tests focused on concepts that a student has not mastered or is at risk of forgetting.	Must
FR-031	The system shall generate mock examinations aligned with specified learning objectives, question formats, marks, duration, and difficulty distribution.	Must
FR-032	The system shall support configurable question types, including multiple-choice, multiple-select, true/false, short answer, descriptive answer, coding questions, and scenario-based questions where appropriate.	Must
FR-033	The system shall align each generated question to one or more learning objectives and record its difficulty, expected answer, marking rubric, marks, and rationale.	Must
FR-034	The system shall construct an exam blueprint specifying the intended coverage of topics, objectives, cognitive levels, difficulty, and marks before generating the final paper.	Must
FR-035	The system shall validate generated exams against the blueprint, total marks, duration, question count, topic coverage, and configured constraints.	Must
FR-036	The system shall check for duplicate, ambiguous, unsupported, or out-of-scope questions and flag questionable items for review.	Must
FR-037	Teachers shall preview, edit, replace, approve, and publish AI-generated exams before students receive them.	Must
FR-038	The system shall support teacher-controlled settings that prevent changes to difficulty, questions, or exam content once a formal exam is published.	Must
FR-039	The system shall support question banks and track question usage, historical performance, and potential repeated exposure.	Should
FR-040	The system shall generate different exam versions where required, while maintaining equivalent learning-objective coverage and comparable difficulty.	Should
FR-041	The system shall provide a student-facing exam interface with instructions, navigation, answer saving, submission, and a visible timer for timed exams.	Must
FR-042	The system shall support automatic scoring for objectively scored questions and rubric-based AI-assisted evaluation for suitable free-text or coding answers.	Must
FR-043	The system shall show model-generated feedback, expected answers, and explanations according to teacher-configured release rules.	Must
FR-044	The system shall update the Learning Twin using exam results, question-level evidence, rubric scores, and confidence in the evaluation.	Must
FR-045	The system shall recommend follow-up learning activities and, when appropriate, a subsequent reassessment based on exam results.	Must
FR-046	The system shall support teacher-set exam policies, including whether personalization is allowed, whether questions may adapt during an exam, and when answers or feedback are revealed.	Must
How personalized exam generation should work
1. Read the Learning Twin
Mastery estimates, misconceptions, learning pace, past attempts and evidence confidence


2. Build an exam blueprint
Select learning objectives, question formats, difficulty, marks, duration and coverage


3. Generate and validate
Generate questions, answer keys and rubrics; validate syllabus alignment, difficulty and marking rules


4. Take the test and evaluate
Administer the exam, score answers, provide authorized feedback and record evidence


5. Update and adapt
Update the Learning Twin and recommend revision, new practice or a future reassessment


Example: Two students are studying Python functions. One demonstrates strong conceptual knowledge but struggles to write working functions. The other writes correct code but struggles to explain parameters and return values.
- Student A receives more code-writing and debugging questions.
- Student B receives more conceptual explanation and code-tracing questions.
- Both tests cover the same essential learning objectives, but the question mix and difficulty progression differ.
For formal examinations, the teacher can disable personalization and use a common, controlled exam blueprint for fairness.
F. Assessment scoring and feedback
ID	Requirement	Priority
FR-047	The system shall calculate scores and topic-level performance using configurable grading rules.	Must
FR-048	The system shall support teacher review and override of AI-assisted grades, with an audit trail.	Must
FR-049	The system shall provide evidence-based feedback identifying strengths, errors, and suggested improvements.	Must
FR-050	The system shall distinguish objective scores from AI-estimated scores and indicate when human review is required.	Must
FR-051	Teachers shall be able to compare results across students, questions, topics, and exam attempts.	Must
FR-052	The system shall identify potentially flawed questions using signals such as unexpectedly poor performance, inconsistent scoring, or student reports.	Should
G. Coding assignment and Git repository intelligence
ID	Requirement	Priority
FR-053	Students shall submit Git repository URLs for supported coding assignments.	Must
FR-054	The system shall inspect authorized repositories in read-only mode and identify relevant files, code structure, tests, and implementation evidence.	Must
FR-055	The system shall map coding evidence to practical skills and learning objectives.	Must
FR-056	The system shall identify likely implementation gaps, debugging issues, and theory-to-practice mismatches, with supporting evidence.	Must
FR-057	The system shall record source references and confidence for coding assessments and allow teacher review.	Must
FR-058	The system shall not execute untrusted submitted code by default and shall treat repository content as untrusted input.	Must
H. Teacher intelligence and interventions
ID	Requirement	Priority
FR-059	The system shall identify learners who may need additional support based on transparent performance and mastery indicators.	Must
FR-060	The system shall recommend targeted interventions based on the learner's gaps, pace, and recent evidence.	Must
FR-061	Teachers shall review and approve AI-generated interventions and assessments before assigning them where teacher approval is required.	Must
FR-062	Teachers shall view class-wide misconceptions, frequently missed questions, topic mastery, and intervention outcomes.	Must
FR-063	The system shall measure progress after interventions using follow-up exercises or reassessments.	Must
FR-064	The system shall support reports showing changes in mastery and assessment performance over time.	Must
I. Agent orchestration, integrations and administration
ID	Requirement	Priority
FR-065	The system shall orchestrate specialized agents for learning diagnosis, exam generation, tutoring, coding analysis, and intervention planning.	Must
FR-066	Agents shall exchange validated structured outputs with defined schemas and traceable execution identifiers.	Must
FR-067	The system shall provide controlled tool access through an allowlisted tool gateway with authentication, authorization, and audit logging.	Must
FR-068	Administrators shall configure model settings, tool permissions, limits, and relevant feature flags.	Must
FR-069	The system shall record agent and tool failures and support safe retries or fallback behavior where appropriate.	Must
FR-070	The architecture shall support future integrations with LMS platforms, repositories, and external learning systems without making them prerequisites for the initial MVP.	Should

2. Non-functional requirements
Non-functional requirements define how well, securely, and reliably the platform must operate. The values below are proposed engineering targets to validate during implementation, not claims about existing performance.
A. Performance and scalability
ID	Requirement	Proposed target
NFR-001	Common dashboard and profile pages shall load promptly under normal conditions.	P95 response time ≤ 2 seconds, excluding initial heavy processing
NFR-002	Standard interactive API operations shall respond within the target latency.	P95 ≤ 3 seconds, excluding LLM-dependent operations
NFR-003	AI operations shall have explicit timeouts and bounded retries.	Configurable by operation; no unbounded retry loops
NFR-004	Exam generation shall handle configured question counts and difficulty constraints without blocking unrelated user operations.	Asynchronous jobs for longer generations
NFR-005	The system shall support an initial demo with one teacher and 30 students.	All 31 demo accounts usable concurrently
NFR-006	Services shall scale independently as user activity and AI workloads grow.	Stateless services where practical; configurable concurrency and quotas
B. Reliability and availability
ID	Requirement	Proposed target
NFR-007	The system shall prevent loss of submitted exam answers during normal operation.	Autosave after answer changes, with visible save status
NFR-008	Exam submission shall be idempotent, preventing duplicate submissions from retries.	One final submission per attempt
NFR-009	Temporary model or tool failures shall not corrupt the Learning Twin or exam state.	Validated writes and recoverable job status
NFR-010	The system shall provide meaningful error messages and retry options when operations fail.	No silent failures
NFR-011	Core application workflows shall not depend exclusively on a single optional managed agent runtime or gateway.	Support a tested fallback deployment path
C. Security and privacy
ID	Requirement	Proposed target
NFR-012	All application access shall require authentication, with authorization enforced server-side.	No reliance on frontend-only access checks
NFR-013	Student data shall be isolated by user, class, and role.	Automated authorization tests for critical APIs
NFR-014	Data shall be encrypted in transit and at rest using platform-supported encryption.	HTTPS/TLS and managed storage encryption
NFR-015	API keys and service credentials shall be stored in an appropriate secret manager or secure environment configuration.	No secrets in source control
NFR-016	Only necessary student data shall be collected and retained.	Documented retention and deletion rules
NFR-017	Production use shall comply with applicable privacy, child-protection, education, and data-protection obligations.	Compliance review before real student deployment
NFR-018	External tools and repository access shall follow least privilege and deny-by-default policies.	Read-only Git access for the MVP
NFR-019	The system shall protect against prompt injection in uploaded documents, repository content, and retrieved material.	Treat external content as data, not trusted instructions
NFR-020	Logs shall avoid unnecessarily exposing student records, credentials, exam answers, or source code.	Redaction and restricted log access
D. AI quality, assessment validity and fairness
ID	Requirement	Proposed target
NFR-021	Generated questions shall be grounded in approved course content and mapped learning objectives.	Every published question has traceable objective mapping
NFR-022	Generated exams shall satisfy their configured blueprint.	100% compliance with deterministic constraints such as marks and question count
NFR-023	The system shall measure question quality, answer-key correctness, and rubric consistency.	Evaluation against a human-reviewed test set
NFR-024	The system shall distinguish lack of evidence from low mastery.	No unsupported mastery conclusions
NFR-025	Mastery and confidence estimates shall be calibrated and evaluated against observed student performance.	Track calibration and prediction error
NFR-026	Adaptive exams shall preserve required learning-objective coverage and respect teacher-defined difficulty boundaries.	Automated blueprint validation
NFR-027	AI-generated grading shall be explainable and subject to human review for high-impact or uncertain cases.	No unreviewed high-stakes grading by default
NFR-028	The system shall test for unfair differences in question quality, scoring, and recommendations across relevant learner groups where appropriate data and consent are available.	Documented fairness evaluation
NFR-029	The system shall not claim that learning has improved solely because a student completed more activities.	Measure demonstrated performance change
NFR-030	Model changes shall be evaluated for regressions in question quality, scoring, latency, and cost.	Versioned evaluation suite
E. Usability and accessibility
ID	Requirement	Proposed target
NFR-031	Teacher and student interfaces shall be responsive across supported desktop, tablet, and mobile screen sizes.	Responsive layout testing
NFR-032	Core workflows shall provide clear status, error, confirmation, and progress feedback.	No ambiguous exam-generation or submission states
NFR-033	Assessment instructions and question layouts shall be clear and consistent.	Usability testing with representative users
NFR-034	The application shall support keyboard navigation and accessible labels for major interactive controls.	Target WCAG 2.2 AA for relevant workflows
NFR-035	AI explanations shall use language appropriate to the learner's course level and configured reading level.	Human-reviewed sample evaluations
F. Maintainability and architecture
ID	Requirement	Proposed target
NFR-036	The system shall use modular components with clear API contracts and separation of concerns.	Independently testable services and agents
NFR-037	Agent outputs shall use validated schemas rather than relying solely on unstructured prose.	Schema validation at component boundaries
NFR-038	Core business logic shall be testable without requiring live model calls.	Mocked model and tool adapters
NFR-039	Database schema changes and deployments shall be versioned and repeatable.	Automated migration workflow
NFR-040	The application shall support local development and a reproducible cloud deployment.	Documented setup and deployment steps
NFR-041	Model providers, repository providers, and optional LMS integrations shall be abstracted behind adapters where practical.	Avoid tight coupling to one external integration
G. Observability, auditability and cost
ID	Requirement	Proposed target
NFR-042	Agent, model, API, and tool operations shall have correlated execution identifiers.	Traceable end-to-end runs
NFR-043	The system shall capture latency, error rates, retry counts, token usage, and estimated AI costs.	Dashboards and structured logs
NFR-044	Important actions shall be auditable.	Track exam creation, approval, publication, grading overrides, and Twin updates
NFR-045	AI usage shall be subject to configurable budgets and rate limits.	Per-user or per-class limits where appropriate
NFR-046	Logs and traces shall redact sensitive content while retaining useful debugging metadata.	No default logging of full student prompts or repository contents
NFR-047	Administrators shall be able to identify failed or stalled asynchronous jobs.	Job status and failure reason available
H. Testing and deployment quality
ID	Requirement	Proposed target
NFR-048	Critical business logic shall have automated unit tests.	Target ≥ 80% coverage for core deterministic logic
NFR-049	Critical end-to-end workflows shall have automated integration tests.	Login, generate exam, approve, attempt, grade, update Twin
NFR-050	AI quality shall be evaluated separately from ordinary software correctness.	Versioned benchmark dataset and repeatable evaluation
NFR-051	Synthetic demo accounts and datasets shall be reproducible and isolated from production data.	No real student records in the demo
NFR-052	Deployment shall include health checks, environment configuration, and rollback procedures.	Documented recovery path

3. Recommended exam-generation rules
The following rules are important enough to treat as explicit product policies.
Rule	Expected behavior
Evidence before personalization	Do not personalize strongly when a learner has insufficient evidence; use a diagnostic assessment instead.
Learning objectives first	Generate questions from the syllabus and learning objectives, not from the student's profile alone.
Difficulty is not mastery	A student who is slow is not necessarily weak. Use accuracy, attempts, hints, evidence quality, and progress together.
Teacher control	Teachers can preview, edit, approve, and lock formal exams.
Fairness	Personalized practice can vary by learner; formal exams can use common blueprints and controlled versions.
Valid scoring	Every question should have an answer key or rubric and a defined scoring method.
Evidence traceability	Each mastery update should reference the assessment or learning evidence that supports it.
No false precision	Mark uncertain answers and grading cases for review instead of presenting estimates as facts.
Reassessment	Follow-up exams should test whether the underlying gap has improved, not simply repeat the same questions.