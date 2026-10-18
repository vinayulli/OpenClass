variable "mcp_images" {
  type = map(string)
  validation {
    condition     = toset(keys(var.mcp_images)) == toset(["data", "github"])
    error_message = "Deploy separate data and github MCP images."
  }
}
variable "mcp_environment" { type = map(map(string)) }
variable "mcp_secrets" {
  type = map(map(object({ secret = string, version = string })))
  validation {
    condition     = !contains(keys(var.mcp_secrets["github"]), "DB_PASSWORD") && !contains(keys(var.mcp_secrets["github"]), "DATABASE_URL") && !contains(keys(var.mcp_secrets["data"]), "GITHUB_PERSONAL_ACCESS_TOKEN") && alltrue([for name, secrets in var.mcp_secrets : !contains(keys(secrets), "MCP_SCOPE_PRIVATE_KEY")])
    error_message = "Separate GitHub/database credentials; MCP services must never receive the API signing key."
  }
}
variable "workload_principals" {
  description = "Exact deployed principal:// identities, keyed by agent alias; no principalSet wildcards."
  type        = map(string)
  validation {
    condition     = alltrue([for value in values(var.workload_principals) : startswith(value, "principal://")])
    error_message = "Use exact IAM workload principals."
  }
}

locals {
  policy = jsondecode(file("${path.module}/../../security/agent-policy.json"))
  mcp_invokers = merge([
    for agent, services in local.policy.tools : {
      for service, tools in services : "${agent}-${service}" => { agent = agent, service = service }
    }
  ]...)
  mcp_secret_bindings = merge([for service, secrets in var.mcp_secrets : { for name, secret in secrets : "${service}-${name}" => { service = service, secret = secret.secret } }]...)
}

resource "google_service_account" "mcp" {
  provider     = google-beta
  for_each     = var.mcp_images
  project      = var.project_id
  account_id   = "openclass-${each.key}-mcp"
  display_name = "OpenClass ${each.key} MCP only"
}

resource "google_cloud_run_v2_service" "mcp" {
  provider = google-beta
  for_each = var.mcp_images
  project  = var.project_id
  name     = "openclass-${each.key}-mcp"
  location = var.region
  # Authenticated IAM ingress remains required. There is no allUsers binding.
  ingress = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.mcp[each.key].email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = each.value
      ports { container_port = 8080 }
      dynamic "volume_mounts" {
        for_each = each.key == "data" ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
      dynamic "env" {
        for_each = merge(var.mcp_environment[each.key], {
          OPENCLASS_GOVERNANCE_MODE    = "managed"
          OPENCLASS_REQUIRE_GOVERNANCE = "true"
          DATA_MCP_ENABLED             = "true"
          GITHUB_MCP_ENABLED           = "true"
          GEAP_MEMORY_ENABLED          = "true"
          MODEL_ARMOR_ENABLED          = "true"
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.mcp_secrets[each.key]
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
    dynamic "volumes" {
      for_each = each.key == "data" ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = ["hackathon-506016:us-central1:openclass-postgres"]
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.mcp, google_project_iam_member.data_sql]
}
resource "google_secret_manager_secret_iam_member" "mcp" {
  provider  = google-beta
  for_each  = local.mcp_secret_bindings
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp[each.value.service].email}"
}
resource "google_project_iam_member" "data_sql" {
  provider = google-beta
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.mcp["data"].email}"
}

resource "google_cloud_run_v2_service_iam_member" "mcp_invoker" {
  provider = google-beta
  for_each = var.enable_workload_bindings ? local.mcp_invokers : {}
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mcp[each.value.service].name
  role     = "roles/run.invoker"
  member   = var.workload_principals[each.value.agent]
}

output "mcp_service_urls" {
  value = { for kind, service in google_cloud_run_v2_service.mcp : kind => service.uri }
}
