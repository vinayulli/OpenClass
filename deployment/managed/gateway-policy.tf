variable "gateway_rules" {
  description = "Reviewed exact-principal UAP rules rendered from actual deployed registry resources. Empty until registration is complete."
  type = list(object({
    description = string
    effect      = string
    principals  = list(string)
    operation   = object({ permissions = list(string) })
    conditions  = map(object({ expression = string }))
  }))
  default = []
  validation {
    condition = alltrue([for rule in var.gateway_rules :
      rule.effect == "ALLOW" && length(rule.principals) > 0 &&
      alltrue([for principal in rule.principals : startswith(principal, "principal://agents.global.")]) &&
      length(rule.operation.permissions) == 1 && contains(rule.operation.permissions, "iap.googleapis.com/resources.egressViaIAP") &&
      toset(keys(rule.conditions)) == toset(["iap.googleapis.com"])
    ])
    error_message = "Gateway rules must use exact Agent Identity principals, the egress permission and an IAP condition."
  }
}

locals {
  gateway_policy_batches = { for index, rules in chunklist(var.gateway_rules, 10) : tostring(index) => rules }
}

resource "google_iam_project_access_policy" "agents" {
  for_each         = local.gateway_policy_batches
  provider         = google-beta
  project          = var.project_id
  location         = "global"
  access_policy_id = "openclass-agent-access-${each.key}"
  display_name     = "OpenClass approved agent routes"
  details {
    dynamic "rules" {
      for_each = each.value
      content {
        description = rules.value.description
        effect      = rules.value.effect
        principals  = rules.value.principals
        operation { permissions = rules.value.operation.permissions }
        dynamic "conditions" {
          for_each = rules.value.conditions
          content {
            service    = conditions.key
            expression = conditions.value.expression
          }
        }
      }
    }
  }
}

resource "google_iam_projects_policy_binding" "agents" {
  for_each          = local.gateway_policy_batches
  provider          = google-beta
  project           = var.project_id
  location          = "global"
  policy_binding_id = "openclass-agent-access-${each.key}"
  policy            = google_iam_project_access_policy.agents[each.key].name
  policy_kind       = "ACCESS"
  target { resource = "//cloudresourcemanager.googleapis.com/projects/${var.project_id}" }
}
