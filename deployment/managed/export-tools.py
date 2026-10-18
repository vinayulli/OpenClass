"""Export actual server tool schemas for review/Registry. Does not call tools or GCP."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main():
    from mcp_servers.data.server import mcp as data
    from mcp_servers.github.server import mcp as github
    for service, server in (("data", data), ("github", github)):
        tools = await server.list_tools()
        content = json.dumps({"tools": [tool.model_dump(mode="json", exclude_none=True) for tool in tools]}, indent=2)+"\n"
        (ROOT/f"deployment/managed/tools-{service}.json").write_text(content)
        if service == "data":
            (ROOT/"deployment/toolspec.json").write_text(content)
        print(f"Exported {service}: {len(tools)} tools; no cloud registration performed")


if __name__ == "__main__":
    asyncio.run(main())
