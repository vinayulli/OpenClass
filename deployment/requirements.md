# OpenClass Google Cloud requirements

Target: **hackathon-506016**. Proposed region: **us-central1**. No resources have been applied by the agent session. Region availability, project billing, organization policies and quotas must be checked in the authenticated project.

| Component | Resource / requirement | Purpose |
| --- | --- | --- |
| Models | Gemini; Vertex AI API for identity-based cloud usage | ADK specialist reasoning; API-key mode remains local development |
| Learner memory | One separately managed GEAP Memory Bank | Long-term memory isolated by organization/course/learner scope |
| Identity | GEAP Agent Identity on the dedicated managed agent runtime | Cryptographically identifiable agent workload; independent of student login |
| Gateway | `openclass-egress` | Govern MCP egress with IAM/IAP and inline Model Armor |
| Registry | Regional Agent Registry | Discover approved MCP service and tool specifications |
| Model Armor | Regional `openclass` template | Prompt injection, jailbreak, safety and malicious URI screening |
| MCP service | Private Cloud Run `openclass-mcp` | Bounded read-only learning and repository tools |
| Container images | Artifact Registry Docker repository `openclass` | Versioned API/MCP/runtime images |
| Secrets | Secret Manager | Database connection and application scope-signing secret; Gemini API key only if using API-key mode |
| Database | One Cloud SQL PostgreSQL instance `openclass-postgres`, shared by API and MCP | Grade, evidence, session and outbox persistence |
| Observability | Cloud Logging and Monitoring | Security decisions, request traces, memory sync errors; redact content |

Required API candidates: `aiplatform.googleapis.com`, `agentidentity.googleapis.com`, `agentregistry.googleapis.com`, `networkservices.googleapis.com`, `networksecurity.googleapis.com`, `iap.googleapis.com`, `compute.googleapis.com`, `iam.googleapis.com`, `modelarmor.googleapis.com`, `run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`, `logging.googleapis.com`, `monitoring.googleapis.com`, `serviceusage.googleapis.com`. Add `sqladmin.googleapis.com` if Cloud SQL is selected. An unavailable API or region must fail provisioning rather than silently removing a requested protection.

Provisioner access: ability to enable services, create the named resources and dedicated service accounts, and configure reviewed IAM. Do not grant application workloads Owner or Editor. Memory workloads require memory generation/retrieval permissions; choose resource-scoped custom roles where supported. Agent Identity is assigned by the managed runtime and must be bound to exact destinations after its resource identity exists. Gateway and Runtime service agents need documented Model Armor integration permissions. MCP workload authentication, application scope authorization and transport security must all be verified independently.

Memory policy: learning evidence and learning preferences only; exclude general personal information, sensitive traits, raw exam answers and answer keys. Suggested initial revision retention: 90 days, subject to the organization's policy. Source-linked assessment summaries are queued transactionally. Memory generation is eventually consistent and must never override authoritative grades. Configure a distinct bank lifecycle so replacing an agent does not delete learner memory.

Execution order:

1. Verify project access, billing, region support and quotas.
2. Enable APIs; create Artifact Registry and dedicated workload identities.
3. Create the learning-only Memory Bank and Model Armor template.
4. Create Gateway with IAP and Model Armor authorization policies.
5. Provision reachable PostgreSQL and Secret Manager values.
6. Deploy the MCP image privately, register its explicit tool specification, and bind destination access.
7. Scaffold and deploy the dedicated ADK runtime with Agent Identity and Gateway attachment.
8. Verify negative authorization cases, cross-learner isolation, memory retries and Model Armor blocking before enabling required-governance mode.

Provisioning scripts are prepared but unexecuted. `bootstrap-gcp.ps1` creates the base APIs/repository, Model Armor template and gateway policy resources. It does not deploy application services, assign project-wide application roles or provision a paid database instance. `create-memory-bank.py` creates the separate managed bank. Remaining deployment steps require the actual cloud database endpoint, secret versions, runtime image and generated identity IDs.
