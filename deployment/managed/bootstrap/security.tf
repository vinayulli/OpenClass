resource "google_model_armor_template" "screening" {
  provider = google-beta
  project = "hackathon-506016"
  location = "us-central1"
  template_id = "openclass"
  filter_config {
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level = "MEDIUM_AND_ABOVE"
    }
    malicious_uri_filter_settings { filter_enforcement = "ENABLED" }
    rai_settings {
      dynamic "rai_filters" {
        for_each = toset(["HATE_SPEECH", "HARASSMENT", "SEXUALLY_EXPLICIT", "DANGEROUS"])
        content {
          filter_type = rai_filters.value
          confidence_level = "MEDIUM_AND_ABOVE"
        }
      }
    }
  }
  template_metadata {
    ignore_partial_invocation_failures = false
    log_sanitize_operations = false
    enforcement_type = "INSPECT_AND_BLOCK"
  }
  depends_on = [google_project_service.required]
}

resource "google_network_services_authz_extension" "iap" {
  provider = google-beta
  project = "hackathon-506016"
  name = "openclass-iap"
  location = "us-central1"
  service = "iap.googleapis.com"
  fail_open = false
  timeout = "1s"
  metadata = { iapPolicyVersion = "V2" }
  depends_on = [google_project_service.required]
}
resource "google_network_security_authz_policy" "gateway" {
  provider = google-beta
  project = "hackathon-506016"
  name = "openclass-agent-access"
  location = "us-central1"
  action = "CUSTOM"
  policy_profile = "REQUEST_AUTHZ"
  target { resources = [google_network_services_agent_gateway.egress.id] }
  custom_provider {
    authz_extension { resources = [google_network_services_authz_extension.iap.id] }
  }
}

resource "google_secret_manager_secret" "configuration" {
  provider = google-beta
  for_each = toset(["openclass-gemini-api-key", "openclass-github-token", "openclass-scope-private-key", "openclass-scope-public-key", "openclass-db-password", "openclass-data-db-password", "openclass-a2a-secret"])
  project = "hackathon-506016"
  secret_id = each.key
  replication {
    auto {}
  }
}
import {
  to = google_secret_manager_secret.configuration["openclass-db-password"]
  id = "projects/hackathon-506016/secrets/openclass-db-password"
}
