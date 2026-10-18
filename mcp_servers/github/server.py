import os
from dotenv import load_dotenv
load_dotenv()
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from backend.cloud.config import validate_governance
from backend.cloud.model_armor import inspect
from mcp_servers.common.auth import ScopedMCP, require_tool
from .upstream import inspect_repository

validate_governance()
mcp = FastMCP("OpenClass GitHub", stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=os.getenv("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*").split(",")))


@mcp.tool()
async def inspect_public_repository(url: str) -> dict:
    """Read a bounded source sample from an authorized public GitHub repository. Never executes code."""
    claims = require_tool("github", "inspect_public_repository")
    if claims["resources"].get("repository_url") != url:
        raise PermissionError("Repository URL is outside the submission scope")
    result = await inspect_repository(url)
    for file in result["files"]:
        await inspect(file["content"])
    return result


app = ScopedMCP(mcp.streamable_http_app(), "github")
