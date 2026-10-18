"""Prepare release wiring from deployed Terraform outputs, never from guessed identities.

Defaults to validation only. --apply updates the ignored release values, keeping
the application in private bootstrap mode until cloud acceptance checks pass.
"""
import argparse
import json
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.runtime.deployment import runtime_url

KINDS = {"teacher", "tutor", "exam", "code", "path", "intervention", "web"}


def prepare(values, outputs):
    def output(name):
        item = outputs.get(name, {}).get("value")
        if not item:
            raise ValueError(f"Deployment output {name} is not ready")
        return item

    cloud_run = values.get("agent_hosting", "runtime") == "cloud_run"
    resources = {} if cloud_run else output("runtime_names")
    origins = output("cloud_run_agent_urls") if cloud_run else {}
    identities = output("cloud_run_agent_identities") if cloud_run else output("runtime_identities")
    if set(origins if cloud_run else resources) != KINDS or set(identities) != KINDS:
        raise ValueError("All seven deployed specialists are required")
    for resource in resources.values():
        if not re.fullmatch(r"projects/[A-Za-z0-9-]+/locations/[a-z0-9-]+/reasoningEngines/[0-9]+", resource):
            raise ValueError("Runtime output must contain a real resource name")
    subjects = {**identities, "api": output("application_identity")}
    def subject(identity):
        if identity.startswith("//"):
            return "spiffe:"+identity
        if identity.startswith("agents.global."):
            return "spiffe://"+identity
        return identity.replace("principal://", "spiffe://", 1)
    subjects = {name: subject(identity) for name, identity in subjects.items()}
    if len(set(subjects.values())) != len(subjects):
        raise ValueError("Every workload must have its own identity")
    for identity in subjects.values():
        if not re.fullmatch(r"spiffe://agents\.global\.[A-Za-z0-9.-]+/resources/[A-Za-z0-9/_-]+", identity) or "bootstrap-" in identity:
            raise ValueError("Only real deployed Agent Identity subjects are accepted")
    web = output("application_url").rstrip("/")
    mcp = output("mcp_service_urls")
    if set(mcp) != {"data", "github"}:
        raise ValueError("Both MCP services must be deployed")
    for url in [web, *mcp.values(), *origins.values()]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".run.app") or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("Expected a deployed HTTPS Cloud Run origin")
    values = json.loads(json.dumps(values))
    update = {
        "OPENCLASS_WORKLOAD_PRINCIPALS": json.dumps(subjects),
        "OPENCLASS_AGENT_RESOURCES": "" if cloud_run else json.dumps(resources),
        "OPENCLASS_AGENT_URLS": json.dumps({name: origin.rstrip("/")+"/invoke" for name, origin in origins.items()}) if cloud_run else "",
        "OPENCLASS_COORDINATOR_URL": web+"/api/internal/agent-actions",
    }
    for name, origin in mcp.items():
        update[name.upper()+"_MCP_URL"] = origin.rstrip("/")+"/mcp"
        update[name.upper()+"_MCP_AUDIENCE"] = origin.rstrip("/")
    for environment in [values["runtime_environment"], values["web_environment"], *values["mcp_environment"].values()]:
        environment.update(update)
    for name, origin in mcp.items():
        existing = values["mcp_environment"][name].get("MCP_ALLOWED_HOSTS", "")
        values["mcp_environment"][name]["MCP_ALLOWED_HOSTS"] = ",".join(sorted(set(filter(None, [*existing.split(","), urlsplit(origin).hostname]))))
    values["web_environment"].update(OPENCLASS_ORIGINS=web, OPENCLASS_DEPLOYMENT_BOOTSTRAP="true")
    values.update(
        workload_principals={name: subject.replace("spiffe://", "principal://", 1) for name, subject in subjects.items()},
        agent_urls={name: origin.rstrip("/")+"/invoke" for name, origin in origins.items()} if cloud_run else {name: runtime_url(resource) for name, resource in resources.items()},
        mcp_urls={name: origin.rstrip("/")+"/mcp" for name, origin in mcp.items()},
        coordinator_url=update["OPENCLASS_COORDINATOR_URL"],
        enable_registration=True,
        enable_workload_bindings=True,
        deploy_runtime_containers=True,
        runtime_identity_only=[],
    )
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--policy", action="store_true", help="Also prepare Gateway rules after all Registry registrations exist")
    args = parser.parse_args()
    directory = ROOT/"deployment/managed"
    target = directory/"release.auto.tfvars.json"
    values = json.loads(target.read_text())
    state = json.loads((directory/"terraform.tfstate").read_text())
    cloud_run = values.get("agent_hosting", "runtime") == "cloud_run"
    if cloud_run or not state.get("outputs", {}).get("application_identity", {}).get("value"):
        # The service template omits this output; the created revision exposes it.
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id="hackathon-506016")
        def deployed_service(name):
            resource = "projects/hackathon-506016/locations/us-central1/services/"+name
            with AuthorizedSession(credentials) as session:
                response = session.get("https://run.googleapis.com/v2/"+resource, timeout=30)
                if not response.ok:
                    raise ValueError("Cannot read deployed service "+name)
                service = response.json()
                if service.get("terminalCondition", {}).get("state") != "CONDITION_SUCCEEDED":
                    raise ValueError("Service is not ready: "+name)
                revision = service.get("latestReadyRevision", "")
                if not revision.startswith(resource+"/revisions/"):
                    raise ValueError("No ready deployed revision: "+name)
                response = session.get("https://run.googleapis.com/v2/"+revision, timeout=30)
                if not response.ok:
                    raise ValueError("Cannot read deployed revision: "+name)
                identity = response.json().get("workloadIdentityConfig", {}).get("identity")
                expected = "//agents.global.proj-159888433965.system.id.goog/resources/run/projects/159888433965/locations/us-central1/services/"+name
                if identity != expected:
                    raise ValueError("Deployed service identity does not match its intended principal")
                return service.get("uri"), identity
        origin, identity = deployed_service("openclass")
        state.setdefault("outputs", {}).update(application_url={"value": origin}, application_identity={"value": identity})
        if cloud_run:
            from concurrent.futures import ThreadPoolExecutor
            kinds = sorted(KINDS)
            with ThreadPoolExecutor(max_workers=4) as executor:
                deployed = list(executor.map(lambda kind: deployed_service("openclass-agent-"+kind), kinds))
            state["outputs"].update(
                cloud_run_agent_urls={"value": {kind: result[0] for kind, result in zip(kinds, deployed)}},
                cloud_run_agent_identities={"value": {kind: result[1] for kind, result in zip(kinds, deployed)}},
            )
    updated = prepare(values, state.get("outputs", {}))
    if args.policy:
        outputs = state["outputs"]
        agents = outputs.get("registered_agents", {}).get("value", {})
        servers = outputs.get("registered_mcp_servers", {}).get("value", {})
        coordinator = outputs.get("registered_coordinator", {}).get("value")
        if set(agents) != KINDS or set(servers) != {"data", "github"} or not coordinator:
            raise ValueError("Complete Registry registration before preparing Gateway rules")
        common = updated["runtime_environment"]
        subjects = json.loads(common["OPENCLASS_WORKLOAD_PRINCIPALS"])
        project = re.search(r"agents\.global\.proj-([0-9]+)\.system\.id\.goog", subjects["api"])
        if not project:
            raise ValueError("This release expects a project-scoped Agent Identity pool")
        inventory = {
            "principals": subjects, "registered_agents": agents,
            "registered_mcp_servers": servers, "registered_endpoints": {"coordinator": coordinator},
            "coordinator_url": updated["coordinator_url"],
            "google_api_context": {
                "project_number": project[1], "region": common["GOOGLE_CLOUD_LOCATION"],
                "model": common["GEMINI_MODEL"], "armor_template": common["MODEL_ARMOR_TEMPLATE"],
            },
        }
        policy_module = runpy.run_path(str(directory/"render-policy.py"))
        updated["gateway_rules"] = policy_module["compile_policy"](policy_module["render"](inventory))
        if args.apply:
            inventory_path = ROOT/"deployment/generated/inventory.json"
            inventory_path.parent.mkdir(parents=True, exist_ok=True)
            inventory_path.write_text(json.dumps(inventory, indent=2)+"\n")
    if args.apply:
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(updated, indent=2)+"\n")
        temporary.replace(target)
        print("Prepared actual identity and endpoint wiring; review a new Terraform plan before applying. Bootstrap mode remains enabled.")
    else:
        print("All deployed identities and endpoints validated; no files or cloud resources changed.")


if __name__ == "__main__":
    main()
