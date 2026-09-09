"""Google Cloud Remote MCP Agent using Google Agent Development Kit (ADK).

This agent connects directly to official Google Cloud Remote MCP Server
endpoints (e.g. recommender.googleapis.com/mcp) using ADK's native McpToolset.
No custom JSON-RPC client code is needed.
"""

import json
import logging
import os
import time
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.responses import JSONResponse, StreamingResponse
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.genai import types

logger = logging.getLogger(__name__)

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
@app.get("/a2a/gcp_agent/.well-known/agent-card.json")
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
@app.post("/a2a/gcp_agent")
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


def _parse_reasoning_engine_input(body: Dict[str, Any]):
    """Extract (class_method, kwargs, user_id, session_id, content, is_gemini_enterprise) from Reasoning Engine payload."""
    class_method = body.get("class_method", "")
    kwargs = body.get("input", {}) or {}

    user_id = kwargs.get("user_id") or kwargs.get("userId")
    session_id = kwargs.get("session_id") or kwargs.get("sessionId")
    raw_message = kwargs.get("message")
    is_gemini_enterprise = (class_method == "streaming_agent_run_with_events") or ("request_json" in kwargs)

    if "request_json" in kwargs:
        try:
            req_data = json.loads(kwargs["request_json"])
            user_id = req_data.get("user_id") or req_data.get("userId") or user_id
            session_id = req_data.get("session_id") or req_data.get("sessionId") or session_id
            if req_data.get("message") is not None:
                raw_message = req_data.get("message")
        except Exception as err:
            logger.warning(f"Could not parse request_json: {err}")

    user_id = user_id or "user"
    session_id = session_id or f"session_{int(time.time())}"

    # Build types.Content object correctly regardless of whether raw_message is dict, Content, or str
    if isinstance(raw_message, types.Content):
        content = raw_message
    elif isinstance(raw_message, dict):
        try:
            content = types.Content(**raw_message)
        except Exception:
            parts_data = raw_message.get("parts", [])
            parts = []
            for p in parts_data:
                if isinstance(p, dict) and "text" in p:
                    parts.append(types.Part.from_text(text=str(p["text"])))
                elif isinstance(p, str):
                    parts.append(types.Part.from_text(text=p))
            if not parts and "text" in raw_message:
                parts = [types.Part.from_text(text=str(raw_message["text"]))]
            content = types.Content(
                role=raw_message.get("role", "user"),
                parts=parts or [types.Part.from_text(text=str(raw_message))],
            )
    elif isinstance(raw_message, str):
        content = types.Content(role="user", parts=[types.Part.from_text(text=raw_message)])
    else:
        content = types.Content(role="user", parts=[types.Part.from_text(text=str(raw_message or ""))])

    return class_method, kwargs, user_id, session_id, content, is_gemini_enterprise


@app.post("/api/stream_reasoning_engine")
async def stream_reasoning_engine(request: FastAPIRequest):
    """Serve the Reasoning Engine streaming contract for the Vertex AI Console Playground and Gemini Enterprise."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    class_method, kwargs, user_id, session_id, content, is_ge = _parse_reasoning_engine_input(body)

    try:
        await session_service.create_session(
            app_name="gcp_agent", user_id=user_id, session_id=session_id
        )
    except Exception:
        pass

    async def event_generator():
        try:
            from vertexai.agent_engines import _utils
        except ImportError:
            from agentplatform._genai import _agent_engines_utils as _utils

        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                event_dict = _utils.dump_event_for_json(event)
                if is_ge:
                    # Gemini Enterprise streaming_agent_run_with_events contract
                    chunk = {
                        "events": [event_dict],
                        "session_id": session_id,
                        "artifacts": [],
                    }
                    yield json.dumps(chunk) + "\n"
                else:
                    # Vertex AI Console Playground / SDK stream_query contract
                    yield json.dumps(event_dict) + "\n"
        except Exception as exc:
            logger.error(f"Error during streaming reasoning engine execution: {exc}", exc_info=True)
            if is_ge:
                err_event = {
                    "content": {"parts": [{"text": f"Error: {exc}"}], "role": "agent"},
                    "author": "agent",
                    "actions": {},
                }
                yield json.dumps({"events": [err_event], "session_id": session_id, "artifacts": []}) + "\n"
            raise

    return StreamingResponse(event_generator(), media_type="application/json")


@app.post("/api/reasoning_engine")
async def reasoning_engine_query(request: FastAPIRequest):
    """Serve the Reasoning Engine synchronous contract."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    class_method, kwargs, user_id, session_id, content, _ = _parse_reasoning_engine_input(body)

    if class_method in ("create_session", "async_create_session"):
        session = await session_service.create_session(
            app_name="gcp_agent", user_id=user_id, session_id=session_id
        )
        return JSONResponse(content={"output": {"id": session.id, "user_id": user_id}})

    if class_method in ("get_session", "async_get_session"):
        session = await session_service.get_session(
            app_name="gcp_agent", user_id=user_id, session_id=session_id
        )
        if session:
            return JSONResponse(content={"output": {"id": session.id, "user_id": user_id}})
        return JSONResponse(content={"output": None})

    if class_method in ("list_sessions", "async_list_sessions"):
        sessions = await session_service.list_sessions(
            app_name="gcp_agent", user_id=user_id
        )
        return JSONResponse(content={"output": [s.id for s in (sessions or [])]})

    if class_method in ("delete_session", "async_delete_session"):
        await session_service.delete_session(
            app_name="gcp_agent", user_id=user_id, session_id=session_id
        )
        return JSONResponse(content={"output": None})

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
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                agent_response_text = event.content.parts[0].text

    return JSONResponse(content={"output": agent_response_text})

