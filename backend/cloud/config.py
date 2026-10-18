import os


def enabled(name):
    return os.getenv(name, "false").lower() == "true"


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Configure {name} to use the Google managed service")
    return value


def validate_governance():
    from ..security.identity import managed, issuer, principal_map
    if managed():
        issuer()
        principal_map()
        required("OPENCLASS_IDENTITY_AUDIENCE")
        required("MCP_SCOPE_PUBLIC_KEY")
        if not enabled("OPENCLASS_REQUIRE_GOVERNANCE"):
            raise RuntimeError("Managed identity mode requires governance enforcement")
        if not enabled("DATA_MCP_ENABLED") or not enabled("GITHUB_MCP_ENABLED"):
            raise RuntimeError("Managed mode requires separated MCP services")
    if enabled("OPENCLASS_REQUIRE_GOVERNANCE"):
        if not enabled("GEAP_MEMORY_ENABLED") or not enabled("MODEL_ARMOR_ENABLED"):
            raise RuntimeError("Managed mode requires GEAP Memory Bank and Model Armor")
        for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GEAP_MEMORY_BANK_ID", "MODEL_ARMOR_TEMPLATE", "GEAP_AGENT_GATEWAY"):
            required(name)
