# Agent communication boundary

`agent-policy.json` is the common default-deny source for local call checks, MCP tool allowlists and generated Agent Gateway UAP rules.

The deterministic coordinator is application code. It queues authorized work and owns leases, retries and webhook delivery; it is not another model. Root jobs use the deployed API workload identity. Every deployed model specialist receives a separate Agent Identity. The Coach may delegate a public educational query to Web Research. Web Research has no learner-data or GitHub tool permission.

Managed requests need two independent credentials: a verified Google workload token, and an API-signed short-lived learner/resource scope or payload-bound execution grant. Never provision the scope signing private key to an agent runtime or MCP server. Never accept an agent name header as authentication. Native platform IAM and Gateway policy must protect deployed endpoints in addition to these application checks.

The Python ContextVar guard only controls application routing in local development. It is not isolation against malicious Python code in the same process. Cloud isolation requires separate deployed identities, no broad project-wide invocation grants, restricted endpoint ingress and successful negative tests. Model Armor inspects content; it does not replace authorization.
