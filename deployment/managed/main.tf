terraform {
  required_providers {
    google-beta = { source = "hashicorp/google-beta", version = ">= 7.0, < 9.0" }
  }
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
}

variable "project_id" { default = "hackathon-506016" }
variable "region" { default = "us-central1" }
variable "project_number" { default = "159888433965" }
variable "agent_hosting" {
  default = "runtime"
  validation {
    condition     = contains(["runtime", "cloud_run"], var.agent_hosting)
    error_message = "Use runtime or cloud_run for specialist hosting."
  }
}
variable "runtime_image" { type = string }
variable "gateway_resource" { type = string }
variable "coordinator_url" { type = string }
variable "enable_workload_bindings" { default = false }
variable "enable_registration" { default = false }
variable "deploy_runtime_containers" { default = true }
variable "runtime_source_archives" {
  description = "Optional credential-free Dockerfile source archives for source-based Runtime deployment."
  type = map(string)
  default = {}
}
variable "runtime_identity_only" {
  type    = set(string)
  default = []
}
variable "bootstrap_runtime_principals" {
  description = "Actual identity-only Runtime principals, used before deploying their containers."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for kind, principal in var.bootstrap_runtime_principals : contains(["teacher", "tutor", "exam", "code", "path", "intervention", "web"], kind) && can(regex("^principal://agents[.]global[.][A-Za-z0-9.-]+/resources/aiplatform/projects/[0-9]+/locations/[a-z0-9-]+/reasoningEngines/[0-9]+$", principal))])
    error_message = "Use actual, exact Runtime identities for approved specialist aliases."
  }
}
variable "enable_gateway_attachment" {
  description = "Attach runtime egress only after real identities, platform routes and Gateway CA trust are ready."
  default     = false
}
variable "gateway_attachment_agents" {
  description = "Specialists to attach during staged Gateway rollout. Defaults to all seven."
  type        = set(string)
  default     = ["teacher", "tutor", "exam", "code", "path", "intervention", "web"]
  validation {
    condition     = alltrue([for kind in var.gateway_attachment_agents : contains(["teacher", "tutor", "exam", "code", "path", "intervention", "web"], kind)])
    error_message = "Gateway attachment must select existing OpenClass specialist aliases."
  }
}
variable "runtime_environment" {
  type = map(string)
  validation {
    condition     = !contains(keys(var.runtime_environment), "MCP_SCOPE_PRIVATE_KEY") && !contains(keys(var.runtime_environment), "GITHUB_PERSONAL_ACCESS_TOKEN") && !contains(keys(var.runtime_environment), "DB_PASSWORD") && !contains(keys(var.runtime_environment), "DATABASE_URL")
    error_message = "Credentials belong in per-workload Secret Manager references, never common environment variables."
  }
}
variable "runtime_secrets" {
  description = "Per-specialist public verification key and Gemini credential. No database credentials, signing private key or GitHub PAT."
  type        = map(map(object({ secret = string, version = string })))
  validation {
    condition     = alltrue([for agent, secrets in var.runtime_secrets : length(setintersection(toset(keys(secrets)), toset(["MCP_SCOPE_PRIVATE_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN", "DATABASE_URL", "DB_PASSWORD", "ADK_SESSION_DATABASE_URL"]))) == 0])
    error_message = "Signing keys belong only to API; GitHub PAT belongs only to GitHub MCP."
  }
}
variable "mcp_urls" {
  type = map(string)
  validation {
    condition     = toset(keys(var.mcp_urls)) == toset(["data", "github"])
    error_message = "Provide separate data and github MCP endpoints."
  }
}
variable "agent_urls" {
  type = map(string)
  validation {
    condition     = toset(keys(var.agent_urls)) == toset(["teacher", "tutor", "exam", "code", "path", "intervention", "web"])
    error_message = "Register every deployed specialist separately."
  }
}

locals {
  agents = toset(["teacher", "tutor", "exam", "code", "path", "intervention", "web"])
}

resource "google_vertex_ai_reasoning_engine" "specialist" {
  provider     = google-beta
  for_each     = var.agent_hosting == "runtime" ? local.agents : toset([])
  project      = var.project_id
  region       = var.region
  display_name = "openclass-${each.key}"
  spec {
    identity_type = "AGENT_IDENTITY"
    agent_framework = "google-adk"
    class_methods = var.deploy_runtime_containers && !contains(var.runtime_identity_only, each.key) ? jsonencode([{ name = "query", api_mode = "async", parameters = { type = "object", required = ["context", "user_id", "grant"], properties = { context = { type = "object" }, user_id = { type = "string" }, grant = { type = "string" } } } }]) : null
    dynamic "container_spec" {
      for_each = var.deploy_runtime_containers && !contains(var.runtime_identity_only, each.key) && !contains(keys(var.runtime_source_archives), each.key) ? [1] : []
      content { image_uri = var.runtime_image }
    }
    dynamic "source_code_spec" {
      for_each = var.deploy_runtime_containers && !contains(var.runtime_identity_only, each.key) && contains(keys(var.runtime_source_archives), each.key) ? [1] : []
      content {
        inline_source { source_archive = var.runtime_source_archives[each.key] }
        image_spec {}
      }
    }
    dynamic "deployment_spec" {
      for_each = var.deploy_runtime_containers && !contains(var.runtime_identity_only, each.key) ? [1] : []
      content {
        min_instances         = 1
        max_instances         = 2
        container_concurrency = 4
        resource_limits       = { cpu = "1", memory = "2Gi" }
        dynamic "env" {
          # Project/quota are reserved; location is allowed and required by our app.
          for_each = merge({ for name, value in var.runtime_environment : name => value if value != "" && !contains(["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_QUOTA_PROJECT"], name) }, {
            OPENCLASS_AGENT_KIND              = each.key
            OPENCLASS_GOVERNANCE_MODE         = "managed"
            OPENCLASS_AGENT_EXECUTION         = "managed"
            OPENCLASS_REQUIRE_GOVERNANCE      = "true"
            DATA_MCP_ENABLED                  = "true"
            GITHUB_MCP_ENABLED                = "true"
            GEAP_MEMORY_ENABLED               = "true"
            MODEL_ARMOR_ENABLED               = "true"
            GOOGLE_API_USE_CLIENT_CERTIFICATE = "true"
          })
          content {
            name  = env.key
            value = env.value
          }
        }
        dynamic "secret_env" {
          for_each = var.runtime_secrets[each.key]
          content {
            name = secret_env.key
            secret_ref {
              secret  = secret_env.value.secret
              version = secret_env.value.version
            }
          }
        }
        dynamic "agent_gateway_config" {
          for_each = var.enable_gateway_attachment && contains(var.gateway_attachment_agents, each.key) ? [1] : []
          content {
            agent_to_anywhere_config { agent_gateway = var.gateway_resource }
          }
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime_platform, google_artifact_registry_repository_iam_member.runtime_platform, google_project_iam_member.runtime_defaults, google_secret_manager_secret_iam_member.runtime_agent]
}

resource "google_agent_registry_service" "mcp" {
  provider     = google-beta
  for_each     = var.enable_registration ? var.mcp_urls : {}
  project      = var.project_id
  location     = var.region
  service_id   = "openclass-${each.key}-mcp"
  display_name = "OpenClass ${each.key} MCP"
  interfaces {
    url              = each.value
    protocol_binding = "JSONRPC"
  }
  mcp_server_spec {
    type    = "TOOL_SPEC"
    content = file("${path.module}/tools-${each.key}.json")
  }
}

resource "google_agent_registry_service" "agent" {
  provider     = google-beta
  for_each     = var.enable_registration ? var.agent_urls : {}
  project      = var.project_id
  location     = var.region
  service_id   = "openclass-${each.key}"
  display_name = "OpenClass ${each.key}"
  interfaces {
    url              = each.value
    protocol_binding = "HTTP_JSON"
  }
  agent_spec { type = "NO_SPEC" }
}

output "runtime_names" {
  value = { for kind, runtime in google_vertex_ai_reasoning_engine.specialist : kind => try(split("/resources/aiplatform/", runtime.spec[0].effective_identity)[1], runtime.id) }
}
output "runtime_identities" {
  value = { for kind, runtime in google_vertex_ai_reasoning_engine.specialist : kind => runtime.spec[0].effective_identity }
}
output "registered_agents" {
  value = { for kind, agent in google_agent_registry_service.agent : kind => agent.registry_resource }
}
output "registered_mcp_servers" {
  value = { for kind, server in google_agent_registry_service.mcp : kind => server.registry_resource }
}
resource "google_agent_registry_service" "coordinator" {
  count        = var.enable_registration ? 1 : 0
  provider     = google-beta
  project      = var.project_id
  location     = var.region
  service_id   = "openclass-coordinator"
  display_name = "OpenClass durable coordinator"
  interfaces {
    url              = var.coordinator_url
    protocol_binding = "HTTP_JSON"
  }
  endpoint_spec { type = "NO_SPEC" }
}
output "registered_coordinator" {
  value = var.enable_registration ? google_agent_registry_service.coordinator[0].registry_resource : null
}
