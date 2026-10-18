# Deployment verification — 18 October 2026

## Public application

- URL: https://openclass-jdi6nfaqza-uc.a.run.app
- Anonymous frontend request returned HTTP 200 with the React root.
- Teacher and student login, workspace, notifications and logout returned HTTP 200 without Cloud Run credentials.
- Demo accounts and walkthrough are in the [root README](../../README.md).

## Infrastructure

- All seven specialist deployments are serving on Agent Runtime with distinct native identities. Actual endpoints and Registry entries are wired to the application.
- The web/API and both private MCP services run on Cloud Run. Only the web/API has the public invoker grant; application APIs still require role-scoped sessions.
- Bootstrap mode is disabled; durable application workers are enabled.
- Runtime query grants are bound directly to approved resources. Model Armor sanitization grants use a limited custom role for the exact OpenClass workload identities.
- Five Gateway policies contain 47 exact-identity route rules. All seven runtimes are attached.
- A real Web Research request completed after Gateway attachment. Gateway logs showed allowed traffic, mTLS and TLS interception. This is positive-path evidence, not proof of all deny cases.

## Live functional acceptance

| Flow | Observed result |
| --- | --- |
| Learning Coach | Real Gemini explanation; history persisted; Memory Bank status available |
| Classroom Advisor | Real Gemini class-performance response; history persisted |
| Teacher assessment delegation | Specialist generated five MCQs; authenticated callback received; draft and teacher notification persisted |
| Assessment publication and attempt | Student notification; answer/rubric hidden before submission; synthetic correct answers graded 10/10 and persisted |
| Student private practice | Coach delegated two-question test; open-test action returned; teacher access denied with HTTP 403 |
| Learning Path | Five detailed steps with approved references; plan persisted |
| Intervention Planner | Valid support draft persisted with teacher review required |
| Coding Agent | Private GitHub MCP inspected the public Spoon-Knife sample; provisional low-confidence report persisted |
| Web Research | Protected request returned four public source links; about 91 seconds end to end |

The six non-Web agent flows above were verified before their final Gateway attachment. Web Research was verified while attached. A full repeat of the complete agent/tool matrix after all attachments remains pending. The coding sample is an integration fixture, not a representative Machine Learning assignment. The assessment score verifies deterministic grading of controlled answers, not an educational outcome.

## Automated checks

- Full Python suite: **92 passed, zero skipped**, using disposable PostgreSQL on localhost:55432.
- Latest targeted security/runtime run: **18 passed**.
- Coverage includes application/A2A flows, remote transport, certificate-enabled Runtime access, coordinator authentication/deduplication, signed grants, MCP separation, repository scopes and learner isolation.
- Separate MCP schema tests verify the Data and GitHub catalogues and reject unauthorized/cross-service requests.
- Local-ADC Model Armor checks allowed a clean question and blocked a prompt-injection sample through the fail-closed application decision. That rejection alone does not distinguish a filter match from incomplete inspection.

## Remaining acceptance work

- Repeat every agent/tool path after the final Gateway attachments, including scoped Data MCP and Coding-to-GitHub routing.
- Perform a controlled negative Gateway enforcement test and verify denial logs.
- Confirm the final ten-learner assessment batch outcome; no all-ten completion claim is made here.
- Complete broader agent-quality, accessibility, load, recovery and production-readiness reviews.

Integration tests reset their target database. **Never point them at the application Cloud SQL database.** Example for the separately provisioned disposable test instance:

```powershell
uv run --no-sync python -m pytest -q --test-database-url postgresql://openclass_test:openclass_disposable_test@127.0.0.1:55432/openclass_verification_test
```

Public application smoke check:

```powershell
uv run --no-sync python deployment/managed/check-application.py --url https://openclass-jdi6nfaqza-uc.a.run.app
```