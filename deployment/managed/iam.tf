resource "google_secret_manager_secret_iam_member" "runtime_platform" {
  provider  = google-beta
  for_each  = toset(["openclass-gemini-api-key", "openclass-scope-public-key"])
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-159888433965@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}
resource "google_artifact_registry_repository_iam_member" "runtime_platform" {
  provider   = google-beta
  for_each   = toset(["service-159888433965@gcp-sa-aiplatform-re.iam.gserviceaccount.com", "service-159888433965@gcp-sa-aiplatform.iam.gserviceaccount.com"])
  project    = var.project_id
  location   = var.region
  repository = "openclass"
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${each.value}"
}
resource "google_project_iam_custom_role" "armor" {
  provider    = google-beta
  project     = var.project_id
  role_id     = "openclassArmorSanitizer"
  title       = "OpenClass content sanitization only"
  permissions = ["modelarmor.templates.useToSanitizeUserPrompt", "modelarmor.templates.useToSanitizeModelResponse"]
}
locals {
  armor_subjects = merge({ data = "serviceAccount:${google_service_account.mcp["data"].email}", github = "serviceAccount:${google_service_account.mcp["github"].email}" }, var.enable_workload_bindings ? var.workload_principals : {})
}
resource "google_project_iam_member" "armor" {
  provider = google-beta
  for_each = local.armor_subjects
  project  = var.project_id
  role     = google_project_iam_custom_role.armor.name
  member   = each.value
  # Model Armor sanitization uses project-level IAM. Its unsupported resource.name
  # condition denied inspection. This custom role contains only the two inspect
  # permissions; application configuration pins the template independently.
}
resource "google_project_iam_member" "quota" {
  provider = google-beta
  for_each = local.armor_subjects
  project  = var.project_id
  role     = "roles/serviceusage.serviceUsageConsumer"
  member   = each.value
}
resource "google_project_iam_member" "memory_reader" {
  provider = google-beta
  project  = var.project_id
  role     = "roles/aiplatform.memoryViewer"
  member   = "serviceAccount:${google_service_account.mcp["data"].email}"
  condition {
    title      = "OpenClass learning memory scope"
    expression = "api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['app_name'].startsWith('openclass_') && api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['user_id'].startsWith('learner_')"
  }
}
resource "google_project_iam_member" "memory_api" {
  provider = google-beta
  for_each = var.enable_workload_bindings ? toset(["roles/aiplatform.memoryViewer", "roles/aiplatform.memoryEditor"]) : toset([])
  project  = var.project_id
  role     = each.value
  member   = var.workload_principals["api"]
  condition {
    title      = "OpenClass learning memory scope"
    expression = "api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['app_name'].startsWith('openclass_') && api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['user_id'].startsWith('learner_')"
  }
}
resource "google_project_iam_custom_role" "runtime_invoker" {
  provider    = google-beta
  project     = var.project_id
  role_id     = "openclassRuntimeInvoker"
  title       = "OpenClass runtime query only"
  permissions = ["aiplatform.reasoningEngines.query"]
}
locals {
  runtime_invocation_edges = var.enable_workload_bindings && var.agent_hosting == "runtime" ? merge(
    { for kind in local.agents : "api-${kind}" => { caller = "api", destination = kind } if kind != "web" },
    { "tutor-web" = { caller = "tutor", destination = "web" } }
  ) : {}
}
resource "google_vertex_ai_reasoning_engine_iam_member" "runtime_invoker" {
  provider         = google-beta
  for_each         = local.runtime_invocation_edges
  project          = var.project_id
  region           = var.region
  reasoning_engine = google_vertex_ai_reasoning_engine.specialist[each.value.destination].name
  role             = google_project_iam_custom_role.runtime_invoker.name
  member           = var.workload_principals[each.value.caller]
}
locals {
  native_runtime_principals     = var.agent_hosting == "runtime" ? (var.enable_workload_bindings ? { for name in local.agents : name => var.workload_principals[name] } : var.bootstrap_runtime_principals) : {}
  runtime_agent_secret_bindings = merge({}, [for name, principal in local.native_runtime_principals : { for key, ref in var.runtime_secrets[name] : "${name}-${key}" => { principal = principal, secret = ref.secret } }]...)
}
resource "google_project_iam_member" "runtime_defaults" {
  provider = google-beta
  for_each = local.native_runtime_principals
  project  = var.project_id
  role     = "roles/aiplatform.agentDefaultAccess"
  member   = each.value
}
resource "google_secret_manager_secret_iam_member" "runtime_agent" {
  provider  = google-beta
  for_each  = local.runtime_agent_secret_bindings
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.principal
}
