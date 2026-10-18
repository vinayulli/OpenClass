# Observed on Cloud Run revision openclass-00001-9l5. Native Agent Identity,
# rather than the platform service account, resolves injected secrets.
locals {
  web_agent_principal = "principal://agents.global.proj-159888433965.system.id.goog/resources/run/projects/159888433965/locations/us-central1/services/openclass"
}
resource "google_secret_manager_secret_iam_member" "web_agent" {
  provider = google-beta
  for_each = toset(["openclass-scope-private-key", "openclass-scope-public-key", "openclass-db-password", "openclass-gemini-api-key", "openclass-a2a-secret"])
  project = "hackathon-506016"
  secret_id = each.value
  role = "roles/secretmanager.secretAccessor"
  member = local.web_agent_principal
}
resource "google_project_iam_member" "web_agent_sql" {
  provider = google-beta
  project = "hackathon-506016"
  role = "roles/cloudsql.client"
  member = local.web_agent_principal
}
