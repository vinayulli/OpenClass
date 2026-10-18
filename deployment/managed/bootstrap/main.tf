terraform {
  required_providers {
    google-beta = { source = "hashicorp/google-beta", version = "8.7.0" }
  }
}
provider "google-beta" {
  project = "hackathon-506016"
  billing_project = "hackathon-506016"
  user_project_override = true
  model_armor_custom_endpoint = "https://modelarmor.us-central1.rep.googleapis.com/v1/"
}
locals {
  apis = toset(["cloudresourcemanager.googleapis.com", "iam.googleapis.com", "iamcredentials.googleapis.com", "run.googleapis.com", "artifactregistry.googleapis.com", "cloudbuild.googleapis.com", "networkservices.googleapis.com", "networksecurity.googleapis.com", "agentregistry.googleapis.com", "modelarmor.googleapis.com", "compute.googleapis.com", "iap.googleapis.com", "policytroubleshooter.googleapis.com"])
}
resource "google_project_service" "required" {
  provider = google-beta
  for_each = local.apis
  project = "hackathon-506016"
  service = each.value
  disable_on_destroy = false
}
resource "google_artifact_registry_repository" "images" {
  provider = google-beta
  project = "hackathon-506016"
  location = "us-central1"
  repository_id = "openclass"
  format = "DOCKER"
  description = "OpenClass application, MCP and specialist images"
  depends_on = [google_project_service.required]
}
resource "google_network_services_agent_gateway" "egress" {
  provider = google-beta
  project = "hackathon-506016"
  name = "openclass-egress"
  location = "us-central1"
  description = "OpenClass governed specialist egress"
  google_managed { governed_access_path = "AGENT_TO_ANYWHERE" }
  registries = ["//agentregistry.googleapis.com/projects/159888433965/locations/us-central1"]
  depends_on = [google_project_service.required]
}
