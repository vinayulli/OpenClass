"""Render reviewable UAP rules from real registry IDs and SPIFFE identities. No cloud mutations."""
import argparse
import json
import re
from urllib.parse import urlsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def render(inventory):
    policy = json.loads((ROOT/"security/agent-policy.json").read_text())
    principals = inventory["principals"]
    agents, servers = inventory["registered_agents"], inventory["registered_mcp_servers"]
    endpoints = inventory.get("registered_endpoints", {})
    for agent, principal in principals.items():
        if not re.fullmatch(r"spiffe://agents\.global\.[A-Za-z0-9.-]+/resources/[A-Za-z0-9/_-]+", principal):
            raise ValueError("Provide actual deployed Agent Identity SPIFFE subjects")
    if len(set(principals.values())) != len(principals):
        raise ValueError("Each workload must have a distinct identity")
    def registered(value, collection):
        if not re.fullmatch(r"/?projects/[A-Za-z0-9-]+/locations/[a-z0-9-]+/"+collection+r"/[A-Za-z0-9_-]+", value):
            raise ValueError("Provide actual registry resource names")
        return value.lstrip("/")
    rules = []
    for caller, destinations in policy["calls"].items():
        # Coordinator is deterministic code hosted inside the API, not an LLM
        # identity. Its approved root dispatches use the API's deployed identity.
        if caller not in principals:
            continue
        for destination in destinations:
            if destination in endpoints:
                target = registered(endpoints[destination], "endpoints")
                rules.append(rule(caller+" to "+destination, principals[caller], f"destination.agent_registry.endpoint.name == '{target}'"))
            if destination in agents:
                target = registered(agents[destination], "agents")
                rules.append(rule(caller+" to "+destination, principals[caller], f"destination.agent_registry.agent.name == '{target}'"))
    for agent, services in policy["tools"].items():
        if services and agent not in principals:
            raise ValueError("Missing deployed identity for "+agent)
        for service, tools in services.items():
            target = registered(servers[service], "mcpServers")
            allowed = json.dumps(tools)
            # initialize, tools/list and protocol notifications carry no tool
            # attribute. Permit that server's metadata handshake; actual tool
            # invocations must match the explicit list and server-side policy.
            tool = "destination.agent_registry.mcp_server.tool"
            expression = f"destination.agent_registry.mcp_server.name == '{target}' && ({tool}.name == '' || {tool}.name in {allowed})"
            rules.append(rule(agent+" to "+service+" tools", principals[agent], expression))
    if inventory.get("google_api_context"):
        rules.extend(google_api_rules(principals, inventory["google_api_context"]))
    if inventory.get("coordinator_url"):
        endpoint = urlsplit(inventory["coordinator_url"])
        if endpoint.scheme != "https" or not (endpoint.hostname or "").endswith(".run.app") or endpoint.path != "/api/internal/agent-actions" or endpoint.query or endpoint.fragment or endpoint.username:
            raise ValueError("Use the exact deployed coordinator HTTPS action endpoint")
        # Custom HTTP endpoints can resolve as unregistered egress. Permit only
        # the intended method/path and two authorized specialist identities.
        expression = f"destination.unregistered.host == '{endpoint.hostname}' && destination.unregistered.method == 'POST' && destination.unregistered.path == '{endpoint.path}'"
        for caller in ["teacher", "tutor"]:
            rules.append(rule(caller+" to exact coordinator HTTP route", principals[caller], expression))
    return rules


def google_api_rules(principals, context):
    """Permit only model, security inspection and issuer-key endpoints needed by runtimes."""
    project, region, model = context["project_number"], context["region"], context["model"]
    if not re.fullmatch(r"[0-9]+", project) or not re.fullmatch(r"[a-z0-9-]+", region) or not re.fullmatch(r"gemini-[A-Za-z0-9.-]+", model):
        raise ValueError("Invalid Google API endpoint context")
    template = context["armor_template"]
    if not re.fullmatch(r"projects/[A-Za-z0-9-]+/locations/"+re.escape(region)+r"/templates/[A-Za-z0-9_-]+", template):
        raise ValueError("Invalid Model Armor template")
    routes = {
        "configured Gemini model": ("generativelanguage.googleapis.com", "POST", [f"/v1beta/models/{model}:{method}" for method in ["generateContent", "streamGenerateContent", "countTokens"]]),
        "Model Armor sanitization": (f"modelarmor.{region}.rep.googleapis.com", "POST", [
            "/google.cloud.modelarmor.v1.ModelArmor/SanitizeUserPrompt",
            "/google.cloud.modelarmor.v1.ModelArmor/SanitizeModelResponse",
            "/v1/"+template+":sanitizeUserPrompt", "/v1/"+template+":sanitizeModelResponse",
        ]),
        "issuer verification keys": ("sts.googleapis.com", "GET", [f"/v1/projects/{project}/locations/global/workloadIdentityPools/agents.global.proj-{project}.system.id.goog/openid/jwks"]),
        "runtime secret injection": ("secretmanager.googleapis.com", "GET", [
            f"/v1/projects/{project}/secrets/{secret}/versions/latest:access"
            for secret in ["openclass-gemini-api-key", "openclass-scope-public-key"]
        ]),
    }
    rules = []
    for agent in ["teacher", "tutor", "exam", "code", "path", "intervention", "web"]:
        if agent not in principals:
            raise ValueError("Missing deployed identity for "+agent)
        for label, (host, method, paths) in routes.items():
            expression = f"destination.unregistered.host == '{host}' && destination.unregistered.method == '{method}' && destination.unregistered.path in {json.dumps(paths)}"
            rules.append(rule(agent+" to "+label, principals[agent], expression))
    # Runtime instrumentation can emit telemetry during initialization. Keep
    # these transport grants separate from data/model IAM permissions.
    platform = {
        "runtime logs": (["logging.googleapis.com", "logging.mtls.googleapis.com"], ["/v2/entries:write", "/google.logging.v2.LoggingServiceV2/WriteLogEntries"]),
        "runtime traces": (["telemetry.googleapis.com", "telemetry.mtls.googleapis.com", "cloudtrace.googleapis.com", "cloudtrace.mtls.googleapis.com"], ["/v1/traces", "/opentelemetry.proto.collector.trace.v1.TraceService/Export", "/google.devtools.cloudtrace.v2.TraceService/BatchWriteSpans", f"/v2/projects/{project}/traces:batchWrite"]),
        "runtime metrics": (["monitoring.googleapis.com", "monitoring.mtls.googleapis.com"], ["/google.monitoring.v3.MetricService/CreateTimeSeries", f"/v3/projects/{project}/timeSeries"]),
    }
    runtime_subjects = [principals[name].replace("spiffe://", "principal://", 1) for name in ["teacher", "tutor", "exam", "code", "path", "intervention", "web"]]
    for label, (hosts, paths) in platform.items():
        expression = f"destination.unregistered.host in {json.dumps(hosts)} && destination.unregistered.method == 'POST' && destination.unregistered.path in {json.dumps(paths)}"
        entry = rule(label, principals["teacher"], expression)
        entry["principals"] = runtime_subjects
        rules.append(entry)
    return rules


def rule(description, subject, expression):
    return {"description": description, "effect": "ALLOW", "principals": [subject.replace("spiffe://", "principal://", 1)], "operation": {"permissions": ["iap.googleapis.com/resources.egressViaIAP"]}, "conditions": {"iap.googleapis.com": {"expression": expression}}}


def compile_policy(rules):
    """Validate atomic rules; Terraform batches ten conditions per policy."""
    for entry in rules:
        expression = entry["conditions"]["iap.googleapis.com"]["expression"]
        if len(expression) > 1024:
            raise ValueError("Gateway condition exceeds GCP's 1024-character limit")
    return rules


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", default="deployment/generated/openclass-uap-rules.json")
    args = parser.parse_args()
    result = compile_policy(render(json.loads(Path(args.inventory).read_text())))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(f"Rendered {len(result)} exact-principal allow rules to {output}; not applied to GCP.")
