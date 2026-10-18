"""Read-only deployment checks. Never prints credentials or GitHub response bodies."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def cloud(project, region):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id=project)
    report = {}
    with AuthorizedSession(credentials) as session:
        checks = {
            "project": f"https://cloudresourcemanager.googleapis.com/v1/projects/{project}",
            "enabled_services": f"https://serviceusage.googleapis.com/v1/projects/{project}/services?filter=state:ENABLED&pageSize=200",
            "runtimes": f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/reasoningEngines",
            "cloud_run": f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/services",
            "gateways": f"https://networkservices.googleapis.com/v1/projects/{project}/locations/{region}/agentGateways",
            "registrations": f"https://agentregistry.googleapis.com/v1/projects/{project}/locations/{region}/services",
        }
        for label, url in checks.items():
            response = session.get(url, timeout=30)
            item = {"http_status": response.status_code}
            if response.ok:
                data = response.json()
                if label == "project":
                    item["project_number"] = data.get("projectNumber")
                    item["parent"] = data.get("parent")
                else:
                    field = {"enabled_services": "services", "runtimes": "reasoningEngines", "cloud_run": "services", "gateways": "agentGateways", "registrations": "services"}[label]
                    item["resources"] = [{"name": entry.get("name"), "display_name": entry.get("displayName")} for entry in data.get(field, [])]
            else:
                error = response.json().get("error", {})
                item["status"] = error.get("status")
                item["reasons"] = [detail.get("reason") for detail in error.get("details", []) if detail.get("reason")]
            report[label] = item
        response = session.post(f"https://cloudresourcemanager.googleapis.com/v1/projects/{project}:testIamPermissions", json={"permissions": ["serviceusage.services.enable", "aiplatform.reasoningEngines.create", "run.services.create", "artifactregistry.repositories.create", "cloudbuild.builds.create", "secretmanager.secrets.create", "iam.serviceAccounts.create", "resourcemanager.projects.setIamPolicy", "networkservices.agentGateways.create", "agentregistry.services.create"]}, timeout=30)
        report["permissions"] = {"http_status": response.status_code, "granted": response.json().get("permissions", [])}
    return report


async def github():
    from backend.cloud.mcp_client import call
    from mcp_servers.github.upstream import TOOLS
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return {"configured": False}
    try:
        result = await call(os.getenv("GITHUB_UPSTREAM_MCP_URL") or "https://api.githubcopilot.com/mcp/", "search_repositories", {"query": "repo:github/github-mcp-server is:public", "perPage": 1, "minimal_output": False}, {"Authorization": "Bearer "+token, "X-MCP-Readonly": "true", "X-MCP-Tools": TOOLS})
        return {"configured": True, "official_mcp_ok": isinstance(result, dict) and bool(result.get("items"))}
    except Exception as error:
        return {"configured": True, "official_mcp_ok": False, "error_type": type(error).__name__}


async def github_repository(url):
    from mcp_servers.github.upstream import inspect_repository
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return {"configured": False, "verified": False}
    os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
    os.environ.setdefault("GITHUB_UPSTREAM_MCP_URL", "https://api.githubcopilot.com/mcp/")
    try:
        result = await inspect_repository(url)
        return {"verified": True, "repository": url, "commit": result["commit"], "files_read": len(result["files"])}
    except Exception as error:
        # Only locally defined static validation messages are safe to report;
        # upstream exception text may contain headers or response bodies.
        known = {"A pinned commit is required", "Unexpected GitHub directory response", "Expected GitHub text file content", "Repository file exceeds limit", "No supported text files found in the bounded repository sample", "Only public repositories can be assessed"}
        result = {"verified": False, "error_type": type(error).__name__}
        if str(error) in known:
            result["validation_error"] = str(error)
        return result


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="hackathon-506016")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--github-repository", help="Also verify bounded static reading of this public repository")
    args = parser.parse_args()
    result = {"project": args.project, "region": args.region, "github": asyncio.run(github())}
    if args.github_repository:
        result["github_repository"] = asyncio.run(github_repository(args.github_repository))
    try:
        result["cloud"] = cloud(args.project, args.region)
    except Exception as error:
        result["cloud"] = {"error_type": type(error).__name__}
    target = ROOT/"deployment/generated/deployment-preflight.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
