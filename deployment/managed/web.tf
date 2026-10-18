variable "web_image" { type = string }
variable "web_environment" { type = map(string) }
variable "web_secrets" { type = map(object({ secret = string, version = string })) }
resource "google_cloud_run_v2_service" "web" {
  provider        = google-beta
  project         = var.project_id
  location        = var.region
  name            = "openclass"
  launch_stage    = "BETA"
  functional_type = "FUNCTIONAL_TYPE_AGENT"
  template {
    service_account = google_service_account.web.email
    timeout         = "300s"
    workload_identity_config {
      identity_type                = "IDENTITY_TYPE_AGENT_IDENTITY"
      identity_certificate_enabled = true
    }
    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = ["hackathon-506016:us-central1:openclass-postgres"] }
    }
    containers {
      image = var.web_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "2Gi" }
        cpu_idle = false
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      dynamic "env" {
        for_each = var.web_environment
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.web_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret
              version = env.value.version
            }
          }
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.web, google_project_iam_member.web_sql]
}
resource "google_service_account" "web" {
  provider     = google-beta
  project      = var.project_id
  account_id   = "openclass-web-platform"
  display_name = "OpenClass API platform operations"
}
resource "google_secret_manager_secret_iam_member" "web" {
  provider  = google-beta
  for_each  = var.web_secrets
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.web.email}"
}
resource "google_project_iam_member" "web_sql" {
  provider = google-beta
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.web.email}"
}
output "application_url" { value = google_cloud_run_v2_service.web.uri }
output "application_identity" { value = google_cloud_run_v2_service.web.template[0].workload_identity_config[0].identity }
resource "google_cloud_run_v2_service_iam_member" "coordinator_invoker" {
  provider = google-beta
  for_each = var.enable_workload_bindings ? toset(["teacher", "tutor"]) : toset([])
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = var.workload_principals[each.value]
}
variable "public_application" { default = false }
resource "google_cloud_run_v2_service_iam_member" "public_application" {
  count    = var.public_application ? 1 : 0
  provider = google-beta
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
  lifecycle {
    precondition {
      condition     = var.enable_workload_bindings && lookup(var.web_environment, "OPENCLASS_DEPLOYMENT_BOOTSTRAP", "true") == "false"
      error_message = "Complete workload identity wiring and disable private bootstrap mode before opening the application."
    }
  }
}
