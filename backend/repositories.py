"""Read-only allowlisted GitHub adapter. No clone, shell, or code execution."""
import re
import httpx
import os


async def inspect_for_actor(url, actor, course_id):
    from .security.identity import managed
    if managed() and os.getenv("OPENCLASS_AGENT_EXECUTION") == "managed":
        from mcp_servers.github.upstream import repository_name
        repository_name(url)
        return {"url": url, "files": [], "scope": "Bounded source inspection delegated to the Coding Agent's GitHub MCP tool."}
    if os.getenv("GITHUB_MCP_ENABLED", "false").lower() == "true":
        from .cloud.capabilities import issue
        from .cloud.mcp_client import call_scoped
        from .security.policy import current_agent
        identity = current_agent.set("code")
        try:
            return await call_scoped("github", "inspect_public_repository", {"url": url}, issue(actor, course_id, actor["id"], agent="code", service="github", resources={"repository_url": url}))
        finally:
            current_agent.reset(identity)
    if managed():
        raise RuntimeError("Managed repository access requires the Coding Agent runtime")
    return await read_repository(url)


async def read_repository(url):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
    if not match:
        raise ValueError("Use a public https://github.com/owner/repository URL")
    owner, repo = match.groups()
    if owner in (".", "..") or repo in (".", ".."):
        raise ValueError("Invalid repository")
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers={"Accept": "application/vnd.github+json", "User-Agent": "OpenClassAI"}) as client:
        info = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        info.raise_for_status()
        branch = info.json()["default_branch"]
        tree = await client.get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}", params={"recursive": "1"})
        tree.raise_for_status()
        files = []
        for entry in tree.json().get("tree", []):
            path = entry["path"]
            if entry["type"] != "blob" or entry.get("size", 0) > 15000 or not path.endswith((".py", ".js", ".ts", ".tsx", ".java", ".md")) or any(p in path.lower().split("/") for p in ("node_modules", "vendor", ".git", "venv", ".venv")):
                continue
            # Fetch by immutable blob SHA from fixed API host; never follow repository-provided URLs.
            blob = await client.get(f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{entry['sha']}")
            blob.raise_for_status()
            import base64
            content = base64.b64decode(blob.json()["content"]).decode("utf-8", errors="replace")
            files.append({"path": path, "sha": entry["sha"], "content": "\n".join(f"{i+1}: {line}" for i, line in enumerate(content.splitlines()))})
            if len(files) >= 12:
                break
    return {"url": url, "files": files, "scope": "Up to 12 text files, 15KB each; static inspection only. This is a partial repository sample."}
