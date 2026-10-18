# MCP services

`data/` and `github/` are separate Python packages, ASGI applications and container images. The old `mcp_service` import is a compatibility alias for **data only**.

| Service | Exposed tools | Credentials |
| --- | --- | --- |
| Data | Course materials, learner twin, academic progress, anonymous class context, learner memory search | Dedicated PostgreSQL reader; Memory Bank retrieval identity; Model Armor; scope public key |
| GitHub | `inspect_public_repository` | GitHub token; Model Armor; scope public key. No PostgreSQL credential |

The GitHub service is an OpenClass authorization proxy over [GitHub's official MCP server](https://github.com/github/github-mcp-server). The upstream URL defaults to `https://api.githubcopilot.com/mcp/`; an operator may configure a self-hosted official server. Only repository search, commit listing and file reading are requested. The agent receives neither the GitHub token nor the upstream tool catalogue. Scope binds inspection to the exact submitted URL. The reader verifies public visibility, pins a commit and samples at most 12 supported text files of 15 KB each across 10 directories. It never executes repository code or follows repository-supplied download URLs.

For a self-hosted official upstream use its HTTP transport and configure `GITHUB_READ_ONLY=true` and `GITHUB_TOOLS=search_repositories,list_commits,get_file_contents`. Pin the upstream image digest after testing. Keep the upstream private to this proxy. Read-only headers narrow requests; the OpenClass allowlist and URL capability are the application authorization boundary.

## Run locally

Set `MCP_CONTEXT_SECRET` to a random value of at least 32 characters in `.env`. Add `GITHUB_PERSONAL_ACCESS_TOKEN` there. Do not paste credentials into chat. Start each in its own terminal, from the repository root:

```powershell
uv run --extra cloud uvicorn mcp_servers.data.server:app --host 127.0.0.1 --port 8001
uv run --extra cloud uvicorn mcp_servers.github.server:app --host 127.0.0.1 --port 8002
```

Set `DATA_MCP_ENABLED=true`, `GITHUB_MCP_ENABLED=true`, and the matching URLs from `.env.example`; restart the backend. Advisor and Coach progress/memory tools use Data MCP. Coding submissions use GitHub MCP. Initial API authorization/context reads and durable application workers still use PostgreSQL directly. This is a domain tool API, not an unrestricted SQL interface.

An optional local container layout is `docker compose --env-file .env -f mcp_servers/compose.yaml up --build`. This passes selected credentials to each service rather than mounting the full `.env`. Its Data container needs a reachable database on `host.docker.internal`; a loopback-only Auth Proxy may require running Data MCP natively instead. Local container mode deliberately disables managed memory and Armor; use native processes with ADC to test those services.

Local HMAC scopes authenticate the application, but do not establish distinct cloud workload identities. Production uses API-issued RSA scopes plus verified Google Agent Identity tokens; see [managed deployment](../deployment/managed/README.md).
