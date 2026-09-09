"""Google Cloud Remote MCP Agent using Google Agent Development Kit (ADK).

This agent connects directly to official Google Cloud Remote MCP Server
endpoints (e.g. recommender.googleapis.com/mcp) using ADK's native McpToolset.
No custom JSON-RPC client code is needed.
"""

import os
from typing import Any, Dict
from fastapi import FastAPI, Request as FastAPIRequest
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.genai import types

# Catalog of Google Cloud remote MCP server endpoints
# Reference: https://docs.cloud.google.com/mcp/supported-products
MCP_CATALOG: Dict[str, str] = {
    "recommender": "https://recommender.googleapis.com/mcp",
    "compute": "https://compute.googleapis.com/mcp",
    "bigquery": "https://bigquery.googleapis.com/mcp",
    "cloudbilling": "https://cloudbilling.googleapis.com/mcp",
    "run": "https://run.googleapis.com/mcp",
    "storage": "https://storage.googleapis.com/storage/mcp",
}

# Active service configuration
SERVICE_NAME = os.getenv("ACTIVE_MCP_SERVICE", "recommender").lower()
MCP_URL = os.getenv("MCP_SERVER_URL", MCP_CATALOG.get(SERVICE_NAME, MCP_CATALOG["recommender"]))
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")


def get_auth_headers(ctx=None) -> Dict[str, str]:
    """Provide fresh Google Cloud OAuth2 Bearer token for remote MCP calls.

    ADK invokes this callable dynamically for each tool request, ensuring
    tokens never go stale during long-running sessions.
    """
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if not credentials.valid:
        credentials.refresh(GoogleAuthRequest())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }

    # When authenticating via local Application Default Credentials (user account),
    # Google Cloud APIs like Recommender require a billing/quota project header.
    quota_project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or getattr(credentials, "quota_project_id", None)
        or project
    )
    if quota_project:
        headers["X-Goog-User-Project"] = quota_project

    return headers


def load_instructions() -> str:
    """Load skill instructions from SKILL.md."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "skills", SERVICE_NAME, "SKILL.md"),
        os.path.join(os.path.dirname(__file__), "..", "skills", SERVICE_NAME, "SKILL.md"),
        os.path.join(os.getcwd(), "skills", SERVICE_NAME, "SKILL.md"),
    ]
    for skill_file in candidates:
        if os.path.exists(skill_file):
            with open(skill_file, "r", encoding="utf-8") as f:
                return f.read()
    return f"You are a helpful assistant with access to Google Cloud {SERVICE_NAME} tools."


# Define the ADK Agent
# ADK automatically handles tool discovery (tools/list), parameter mapping,
# function calling execution, and response synthesis.
root_agent = Agent(
    name=f"gcp_{SERVICE_NAME}_agent",
    model=MODEL_NAME,
    instruction=load_instructions(),
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=MCP_URL),
            header_provider=get_auth_headers,
        )
    ],
)

# FastAPI wrapper for Cloud Run and Gemini Enterprise A2A protocol
app = FastAPI(title=f"GCP {SERVICE_NAME.capitalize()} ADK Agent")

session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name="gcp_agent", session_service=session_service)


@app.get("/")
@app.get("/health")
@app.get("/healthz")
async def health_check():
    return {"status": "ok", "agent": root_agent.name}


@app.get("/.well-known/agent-card.json")
async def get_agent_card(request: FastAPIRequest):
    base_url = str(request.base_url).rstrip("/")
    return {
        "name": f"GCP {SERVICE_NAME.capitalize()} Agent",
        "description": f"Audits Google Cloud resources using Google's remote {SERVICE_NAME} MCP server.",
        "version": "1.0.0",
        "protocolVersion": "1.0",
        "endpoints": {"a2a": f"{base_url}/a2a"},
        "capabilities": {"skills": [SERVICE_NAME]},
    }


@app.post("/a2a")
async def handle_a2a_invoke(payload: Dict[str, Any]):
    method = payload.get("method")
    if method == "agent/invoke":
        params = payload.get("params", {})
        user_message = params.get("message", {}).get("text", "")
        session_id = params.get("session_id", "default_session")
        user_id = params.get("user_id", "enterprise_user")

        try:
            await session_service.create_session(
                app_name="gcp_agent", user_id=user_id, session_id=session_id
            )
        except Exception:
            pass

        agent_response_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=user_message)]
            ),
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    agent_response_text = event.content.parts[0].text

        return {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "result": {"message": {"role": "agent", "text": agent_response_text}},
        }

    return {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "error": {"code": -32601, "message": f"Method '{method}' not supported"},
    }
