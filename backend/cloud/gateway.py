"""ADK Agent Registry discovery; Gateway routing is enforced by runtime deployment config."""
from .config import required


def registered_toolset(context_token):
    from google.adk.integrations.agent_registry import AgentRegistry
    def headers(context):
        # The model never receives this signed context; it is attached only to tool transport.
        return {"X-OpenClass-Context": context_token}
    registry = AgentRegistry(project_id=required("GOOGLE_CLOUD_PROJECT"), location=required("GOOGLE_CLOUD_LOCATION"), header_provider=headers)
    return registry.get_mcp_toolset(mcp_server_name=required("GEAP_MCP_SERVER"))
