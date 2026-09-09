"""Google Cloud Remote MCP Agent Bridge.

Re-exports the ADK agent and FastAPI app from the `gcp_agent` package for
backward compatibility with direct runner scripts and container entrypoints.
"""

from gcp_agent.agent import (
    root_agent,
    app,
    runner,
    session_service,
    MCP_CATALOG,
    SERVICE_NAME,
    MCP_URL,
    MODEL_NAME,
    get_auth_headers,
    load_instructions,
)

__all__ = [
    "root_agent",
    "app",
    "runner",
    "session_service",
    "MCP_CATALOG",
    "SERVICE_NAME",
    "MCP_URL",
    "MODEL_NAME",
    "get_auth_headers",
    "load_instructions",
]
