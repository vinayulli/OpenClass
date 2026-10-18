# Deadline fallback, activated only by agent_hosting = "cloud_run". Each fixed
# specialist keeps a separate native identity and private authenticated ingress.
locals {
  run_agents           = var.agent_hosting == "cloud_run" ? local.agents : toset([])
  run_agent_principals = { for kind in local.run_agents : kind => "principal://agents.global.proj-${var.project_number}.system.id.goog/resources/run/projects/${var.project_number}/locations/${var.region}/services/openclass-agent-${kind}" }
  run_agent_secrets    = merge({}, [for kind in local.run_agents : { for name, ref in var.runtime_secrets[kind] : "${kind}-${name}" => { kind = kind, secret = ref.secret } }]...)
  run_agent_calls      = merge({}, [for caller, destinations in local.policy.calls : { for destination in destinations : "${caller}-${destination}" => { caller = caller, destination = destination } if contains(local.agents, destination) && caller != "coordinator" }]...)
}
resource "google_service_account" "specialist" {
  provider     = google-beta
  for_each     = local.run_agents
  project      = var.project_id
  account_id   = "openclass-agent-${each.key}"
  display_name = "OpenClass ${each.key} platform"
}
resource "google_secret_manager_secret_iam_member" "run_specialist_native" {
  provider  = google-beta
  for_each  = local.run_agent_secrets
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = local.run_agent_principals[each.value.kind]
}
resource "google_secret_manager_secret_iam_member" "run_specialist_platform" {
  provider  = google-beta
  for_each  = local.run_agent_secrets
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.specialist[each.value.kind].email}"
}
resource "google_cloud_run_v2_service" "specialist" {
  provider        = google-beta
  for_each        = local.run_agents
  project         = var.project_id
  location        = var.region
  name            = "openclass-agent-${each.key}"
  launch_stage    = "BETA"
  functional_type = "FUNCTIONAL_TYPE_AGENT"
  ingress         = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.specialist[each.key].email
    timeout         = "300s"
    workload_identity_config {
      identity_type                = "IDENTITY_TYPE_AGENT_IDENTITY"
      identity_certificate_enabled = true
    }
    max_instance_request_concurrency = 4
    scaling {
      min_instance_count = 1
      max_instance_count = 2
    }
    containers {
      image = var.runtime_image
      ports { container_port = 8080 }
      resources { limits = { cpu = "1", memory = "2Gi" } }
      dynamic "env" {
        for_each = merge(var.runtime_environment, { OPENCLASS_AGENT_KIND = each.key, OPENCLASS_GATEWAY_ENFORCED = "false" })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.runtime_secrets[each.key]
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
  depends_on = [google_secret_manager_secret_iam_member.run_specialist_native, google_secret_manager_secret_iam_member.run_specialist_platform]
}
resource "google_cloud_run_v2_service_iam_member" "specialist_invoker" {
  provider = google-beta
  for_each = var.agent_hosting == "cloud_run" && var.enable_workload_bindings ? local.run_agent_calls : {}
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.specialist[each.value.destination].name
  role     = "roles/run.invoker"
  member   = each.value.caller == "coordinator" ? var.workload_principals["api"] : var.workload_principals[each.value.caller]
}
output "cloud_run_agent_urls" {
  value = { for kind, service in google_cloud_run_v2_service.specialist : kind => service.uri }
}
