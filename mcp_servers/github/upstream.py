"""Bounded static reading through the official GitHub MCP server."""
import base64
import json
import re
from backend.cloud.config import required
from backend.cloud.mcp_client import call, checked_url

TOOLS = "search_repositories,list_commits,get_file_contents"


def repository_name(url):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
    if not match or any(p in {".", ".."} for p in match.groups()):
        raise ValueError("Use a public https://github.com/owner/repository URL")
    return match.groups()


async def inspect_repository(url):
    owner, repo = repository_name(url)
    endpoint = checked_url(required("GITHUB_UPSTREAM_MCP_URL"))
    # PAT stays exclusively in this service. Limit it to public repository reads.
    headers = {"Authorization": "Bearer "+required("GITHUB_PERSONAL_ACCESS_TOKEN"),
               "X-MCP-Readonly": "true", "X-MCP-Tools": TOOLS}
    async def tool(name, arguments):
        return await call(endpoint, name, arguments, headers)
    search = await tool("search_repositories", {"query": f"repo:{owner}/{repo} is:public", "perPage": 1, "minimal_output": False})
    matches = search.get("items", []) if isinstance(search, dict) else []
    if not any(item.get("full_name", "").casefold() == f"{owner}/{repo}".casefold() and item.get("private") is not True for item in matches):
        raise PermissionError("Only public repositories can be assessed")
    commits = await tool("list_commits", {"owner": owner, "repo": repo, "perPage": 1})
    if isinstance(commits, dict):
        commits = commits.get("commits", [])
    sha = commits[0].get("sha", "") if commits else ""
    if not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
        raise ValueError("A pinned commit is required")
    pending, files, visited = [""], [], 0
    while pending and visited < 10 and len(files) < 12:
        path = pending.pop(0)
        visited += 1
        entries = await tool("get_file_contents", {"owner": owner, "repo": repo, "path": path, "sha": sha})
        if isinstance(entries, dict):
            entries = entries.get("entries", entries.get("content", []))
        if not isinstance(entries, list):
            raise ValueError("Unexpected GitHub directory response")
        for entry in entries[:100]:
            name = entry.get("path", "")
            if not name or name.startswith("/") or any(p in {"..", ".git", ".venv", "venv", "node_modules", "vendor"} for p in name.split("/")):
                continue
            if entry.get("type") == "dir":
                if len(pending) < 10:
                    pending.append(name)
                continue
            if entry.get("type") != "file" or entry.get("size", 15001) > 15000 or not name.endswith((".py", ".ipynb", ".js", ".ts", ".tsx", ".java", ".md")):
                continue
            item = await tool("get_file_contents", {"owner": owner, "repo": repo, "path": name, "sha": sha})
            if not isinstance(item, dict) or item.get("encoding") not in {"base64", "utf-8"}:
                raise ValueError("Expected GitHub text file content")
            raw = base64.b64decode(item["content"], validate=False) if item["encoding"] == "base64" else item["content"].encode()
            if len(raw) > 15000:
                raise ValueError("Repository file exceeds limit")
            content = raw.decode("utf-8", errors="replace")
            files.append({"path": name, "sha": item.get("sha"), "content": "\n".join(f"{n+1}: {line}" for n, line in enumerate(content.splitlines()))})
            if len(files) == 12:
                break
    if not files:
        raise ValueError("No supported text files found in the bounded repository sample")
    return {"url": url, "commit": sha, "files": files, "scope": "Official GitHub MCP: up to 12 text files, 15KB each, 10 directories; pinned commit; static inspection only. Partial repository sample."}
