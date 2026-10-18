"""Compatibility import for the data-only scope middleware."""
from mcp_servers.common.auth import ScopedMCP

class ScopedRequests(ScopedMCP):
    def __init__(self, app):
        super().__init__(app, "data")
