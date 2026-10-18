"""Prepare non-secret Terraform values; bootstrap endpoints stay private and deny calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KINDS = ["teacher", "tutor", "exam", "code", "path", "intervention", "web"]


def main():
    images = json.loads((ROOT/"deployment/generated/images.json").read_text())
    runtime_image = images["runtime"]
    def image(name):
        return images.get(name) or runtime_image.replace("/runtime:", "/"+name+":")
    base = "projects/159888433965/locations/us-central1"
    trust = "agents.global.proj-159888433965.system.id.goog"
    principals = {name: f"spiffe://{trust}/resources/aiplatform/{base}/reasoningEngines/bootstrap-{name}" for name in ["api", *KINDS]}
    resources = {name: f"{base}/reasoningEngines/bootstrap-{name}" for name in KINDS}
    web_url = "https://openclass-159888433965.us-central1.run.app"
    mcp = {name: f"https://openclass-{name}-mcp-159888433965.us-central1.run.app" for name in ["data", "github"]}
    common = {
        "GOOGLE_CLOUD_PROJECT": "hackathon-506016", "GOOGLE_CLOUD_QUOTA_PROJECT": "hackathon-506016", "GOOGLE_CLOUD_LOCATION": "us-central1",
        "GEMINI_MODEL": "gemini-3.8-flash", "GOOGLE_GENAI_USE_VERTEXAI": "false",
        "OPENCLASS_GOVERNANCE_MODE": "managed", "OPENCLASS_AGENT_EXECUTION": "managed", "OPENCLASS_REQUIRE_GOVERNANCE": "true",
        "GEAP_MEMORY_ENABLED": "true", "GEAP_MEMORY_BANK_ID": "5670775475597737984",
        "MODEL_ARMOR_ENABLED": "true", "MODEL_ARMOR_TEMPLATE": "projects/hackathon-506016/locations/us-central1/templates/openclass",
        "GEAP_AGENT_GATEWAY": "projects/hackathon-506016/locations/us-central1/agentGateways/openclass-egress",
        "OPENCLASS_IDENTITY_ISSUER": f"https://sts.googleapis.com/v1/projects/159888433965/locations/global/workloadIdentityPools/{trust}",
        "OPENCLASS_IDENTITY_AUDIENCE": "https://openclass.internal/workloads", "OPENCLASS_WORKLOAD_PRINCIPALS": json.dumps(principals),
        "OPENCLASS_AGENT_RESOURCES": json.dumps(resources), "OPENCLASS_COORDINATOR_URL": web_url+"/api/internal/agent-actions",
        "DATA_MCP_ENABLED": "true", "GITHUB_MCP_ENABLED": "true", "DATA_MCP_URL": mcp["data"]+"/mcp", "GITHUB_MCP_URL": mcp["github"]+"/mcp",
        "DATA_MCP_AUDIENCE": mcp["data"], "GITHUB_MCP_AUDIENCE": mcp["github"],
        "GOOGLE_API_USE_CLIENT_CERTIFICATE": "true", "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
        "AI_TIMEOUT_SECONDS": "90",
    }
    def secret(name):
        return {"secret": name, "version": "latest"}
    public = {"MCP_SCOPE_PUBLIC_KEY": secret("openclass-scope-public-key")}
    db = {"DB_HOST": "/cloudsql/hackathon-506016:us-central1:openclass-postgres", "DB_PORT": "5432", "DB_NAME": "openclass"}
    from backend.runtime.deployment import runtime_url
    values = {
        "runtime_image": runtime_image, "gateway_resource": common["GEAP_AGENT_GATEWAY"],
        "runtime_environment": common, "runtime_secrets": {name: {**public, "GEMINI_API_KEY": secret("openclass-gemini-api-key")} for name in KINDS},
        "mcp_urls": {name: url+"/mcp" for name, url in mcp.items()}, "agent_urls": {name: runtime_url(resource) for name, resource in resources.items()},
        "coordinator_url": common["OPENCLASS_COORDINATOR_URL"],
        "mcp_images": {name: image(name+"-mcp") for name in mcp},
        "mcp_environment": {"data": {**common, **db, "DB_USER": "openclass_mcp", "MCP_ALLOWED_HOSTS": "openclass-data-mcp-159888433965.us-central1.run.app"}, "github": {**common, "GITHUB_UPSTREAM_MCP_URL": "https://api.githubcopilot.com/mcp/", "MCP_ALLOWED_HOSTS": "openclass-github-mcp-159888433965.us-central1.run.app"}},
        "mcp_secrets": {"data": {**public, "DB_PASSWORD": secret("openclass-data-db-password")}, "github": {**public, "GITHUB_PERSONAL_ACCESS_TOKEN": secret("openclass-github-token")}},
        "workload_principals": {name: subject.replace("spiffe://", "principal://", 1) for name, subject in principals.items()},
        "web_image": image("web"), "web_environment": {**common, **db, "DB_USER": "openclass", "COOKIE_SECURE": "true", "OPENCLASS_DEMO": "true", "OPENCLASS_DEPLOYMENT_BOOTSTRAP": "true", "OPENCLASS_ORIGINS": web_url, "A2A_ASSESSMENT_URL": "http://127.0.0.1:8080/a2a/assessment", "A2A_CALLBACK_URL": "http://127.0.0.1:8080/api/a2a/webhook"},
        "web_secrets": {**public, "MCP_SCOPE_PRIVATE_KEY": secret("openclass-scope-private-key"), "DB_PASSWORD": secret("openclass-db-password"), "GEMINI_API_KEY": secret("openclass-gemini-api-key"), "A2A_SHARED_SECRET": secret("openclass-a2a-secret")},
    }
    target = ROOT/"deployment/managed/release.auto.tfvars.json"
    if target.exists():
        raise SystemExit("Release configuration already exists; refusing to overwrite deployed identities")
    target.write_text(json.dumps(values, indent=2)+"\n")
    print("Prepared private bootstrap configuration; placeholder identities deny execution until replaced with actual deployed identities")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    main()
