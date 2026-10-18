import os
from dotenv import load_dotenv
load_dotenv()
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from backend.cloud.config import validate_governance
from mcp_servers.common.auth import ScopedMCP
from . import tools

validate_governance()
mcp = FastMCP("OpenClass data", stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=os.getenv("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*").split(",")))
for name in ("get_learning_twin", "get_course_materials", "get_student_progress", "get_class_summary", "search_learner_memory"):
    mcp.add_tool(getattr(tools, name))
app = ScopedMCP(mcp.streamable_http_app(), "data")
