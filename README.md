# Google Cloud Remote MCP Bridge to Gemini Enterprise

A minimal, production-ready reference architecture connecting official **Google Cloud Remote Model Context Protocol (MCP) servers** to **Gemini Enterprise** using the **Google Agent Development Kit (ADK)**.

---

## Why Minimal Code? (Native ADK `McpToolset`)

Unlike custom agent setups that require writing hundreds of lines of HTTP JSON-RPC boilerplate, this repository uses the native **`McpToolset`** in Google ADK (`google-adk[mcp]`).

Connecting to any Google Cloud Remote MCP server is declared in a few lines of Python:

```python
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

root_agent = Agent(
    name="gcp_recommender_agent",
    model="gemini-2.5-flash",
    instruction=load_instructions(),  # from skills/recommender/SKILL.md
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url="https://recommender.googleapis.com/mcp"
            ),
            header_provider=get_auth_headers,
        )
    ],
)
```

ADK automatically handles:
1. Dynamic tool discovery (`tools/list`).
2. Schema conversion for the Gemini model.
3. Invoking the remote MCP tools (`tools/call`) over HTTPS.
4. Token refresh via `header_provider`.

---

## Architecture Overview

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. End User in Gemini Enterprise Web Chat                              │
 │    "What idle persistent disks can we clean up in project my-gcp-proj?"│
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼ (1) Authenticated RPC (:streamQuery)
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 2. Vertex AI Agent Runtime (Reasoning Engine Gateway)                  │
 │    - Routes HTTP POST to container: /api/stream_reasoning_engine       │
 │    - Manages serverless container lifecycle & session binding          │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼ (2) HTTP POST with unwrapped JSON payload
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 3. Hosted ADK Container (gcp_agent/agent.py)                           │
 │    - Endpoint /api/stream_reasoning_engine parses Gemini Enterprise req│
 │    - ADK Runner invokes root_agent with skills/recommender/SKILL.md    │
 │    - Gemini 2.5 Flash decides to call list_recommendations tool        │
 │    - McpToolset calls get_auth_headers() for fresh OAuth2 ADC token    │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼ (3) JSON-RPC over HTTPS (OAuth2 Bearer token)
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 4. Google-Managed Remote MCP Server                                    │
 │    https://recommender.googleapis.com/mcp                              │
 │    - Authorizes caller via IAM (roles/mcp.toolUser)                    │
 │    - Executes query against Google Cloud Recommender API               │
 │    - Returns live resource recommendations                             │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼ (4) Streaming JSON chunks back to UI
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 5. Streaming Event Yielding to Gemini Enterprise                       │
 │    - agent.py yields {"events": [...], "session_id": ..., "artifacts": []}
 │    - Gemini Enterprise streams formatted table & actions in real time  │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## Deep Dive: `gcp_agent/agent.py` & Hosted Endpoints

The container serves three critical functions: defining the ADK agent, handling remote authentication, and exposing the **Vertex AI Reasoning Engine** HTTP contracts required by Agent Runtime and Gemini Enterprise.

### 1. Dynamic Authentication (`get_auth_headers`)
Google Cloud OAuth2 access tokens expire after 3,600 seconds (1 hour). Hardcoding tokens causes agents to fail silently in production.
- `get_auth_headers()` is supplied as a callable to `McpToolset(header_provider=get_auth_headers)`.
- ADK executes this callback **dynamically before every remote tool call**, checking validity and calling `credentials.refresh()` if needed.
- In addition to `Authorization: Bearer <token>`, it injects `X-Goog-User-Project` when running with user-level Application Default Credentials (ADC), ensuring Google Cloud quota and billing are properly resolved.

### 2. Mandatory Health Probes (`GET /`, `/health`, `/healthz`)
- Google Cloud Agent Runtime infrastructure periodically sends HTTP `GET` requests to verify container responsiveness.
- Returning `{"status": "ok", "agent": "..."}` ensures the container passes readiness/liveness checks and prevents premature container restarts.

### 3. Synchronous Operations (`POST /api/reasoning_engine`)
- Implements the Vertex AI Reasoning Engine contract for session lifecycle methods:
  - `create_session` / `async_create_session`: Creates an isolated session in the session service.
  - `get_session` / `async_get_session`: Retrieves active session metadata.
  - `list_sessions` / `async_list_sessions`: Lists all existing sessions for a user.
  - `delete_session` / `async_delete_session`: Cleans up session state.
  - Synchronous query fallback: Returns `{"output": "..."}` with the final agent response.

### 4. Streaming Event Engine (`POST /api/stream_reasoning_engine`)
- This is the **primary production endpoint** invoked when a user chats in Gemini Enterprise or the Vertex AI Console Playground.
- **Payload Unwrapping (`_parse_reasoning_engine_input`)**:
  - Gemini Enterprise sends a `streaming_agent_run_with_events` RPC where user input is nested inside a JSON string field named `request_json`.
  - Vertex AI Playground sends standard `stream_query` with an `input` dict.
  - `_parse_reasoning_engine_input()` seamlessly normalizes both shapes, extracts `user_id`, `session_id`, and builds an ADK-native `types.Content` object.
- **Streaming Chunks Generator (`event_generator`)**:
  - Executes `runner.run_async()`.
  - Converts ADK events into the JSON chunk contract expected by Gemini Enterprise:
    ```json
    {"events": [{"content": {"parts": [{"text": "..."}], "role": "agent"}, "author": "agent"}], "session_id": "sess_123", "artifacts": []}
    ```
  - Emitting these streaming chunks prevents stream timeout and eliminates the error: `Reasoning Engine stream closed cleanly without producing any events`.

---

## End-to-End Request Lifecycle & Architecture Trace

When an enterprise user asks a question in Gemini Enterprise, here is the complete 12-step journey of the request:

```
[User Chat Prompt]
       │
       ▼
 1. User asks: "What idle persistent disks can we clean up in project my-gcp-project in zone us-central1-a?"
       │
       ▼
 2. Gemini Enterprise Orchestrator (Discovery Engine) identifies the GCP Recommender Agent in Agent Registry.
       │
       ▼
 3. Gemini Enterprise calls Reasoning Engine streamQuery RPC:
    Method: streaming_agent_run_with_events
    Body: {"class_method": "streaming_agent_run_with_events", "input": {"request_json": "{\"message\": \"...\"}"}}
       │
       ▼
 4. Vertex AI Agent Runtime routes HTTP POST to container: /api/stream_reasoning_engine
       │
       ▼
 5. FastAPI handler (_parse_reasoning_engine_input) unwraps request_json and builds types.Content object.
       │
       ▼
 6. ADK Runner (runner.run_async) passes the prompt and SKILL.md instructions to Gemini 2.5 Flash.
       │
       ▼
 7. Gemini 2.5 Flash decides to invoke the remote tool:
    FunctionCall: list_recommendations(parent="projects/my-gcp-project/locations/us-central1-a/recommenders/google.compute.disk.IdleResourceRecommender")
       │
       ▼
 8. ADK McpToolset calls get_auth_headers() to obtain fresh OAuth2 Bearer token with X-Goog-User-Project.
       │
       ▼
 9. ADK McpToolset sends HTTPS JSON-RPC request (tools/call) to:
    https://recommender.googleapis.com/mcp
       │
       ▼
10. Google Remote MCP Server authenticates IAM permissions (roles/mcp.toolUser) and queries Google Cloud Recommender API.
       │
       ▼
11. Gemini 2.5 Flash receives raw JSON recommendations, calculates monthly/annual savings, formats an executive Markdown table, and produces actionable gcloud cleanup commands.
       │
       ▼
12. agent.py yields streaming event chunks ({"events": [...], "session_id": ..., "artifacts": []}\n) back through Agent Runtime to the Gemini Enterprise Chat UI in real time.
```

---

## Project Structure

```
google-cloud-mcp-bridge/
├── gcp_agent/            # ADK Agent package (valid Python module for ADK loader)
│   ├── __init__.py       # Exports root_agent for ADK loader
│   └── agent.py          # Native ADK Agent using McpToolset + Reasoning Engine routes
├── agent.py              # Root wrapper re-exporting from gcp_agent
├── skills/
│   └── recommender/
│       └── SKILL.md      # Skill instructions for cost and idle resource analysis
├── Dockerfile            # Container image build for Agent Runtime
├── requirements.txt      # Python dependencies (google-adk[mcp,gcp])
├── test_client.py        # Local script to verify ADK McpToolset discovery
├── test_chat.py          # Local script to run conversational prompts via ADK Runner
├── deploy.sh             # Script to deploy to Agent Runtime and publish via agents-cli
└── README.md             # Project documentation
```

---

## Quickstart

### 1. Install `uv` and `agents-cli`

`agents-cli` is Google Cloud's official CLI toolkit for developing, evaluating, and deploying AI agents on Google Cloud. Install it using `uv`:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install agents-cli
uv tool install google-agents-cli

# Verify installation
agents-cli info
```

### 2. Scaffold or Bootstrap the Project with `agents-cli`

If starting a new agent from scratch, you can scaffold it in one command using `agents-cli scaffold create`:

```bash
# Scaffold an ADK Agent targeting Vertex AI Agent Runtime in rapid-prototype mode
agents-cli scaffold create gcp-recommender-agent \
  --agent adk \
  --deployment-target agent_runtime \
  --region us-central1 \
  --prototype
```

Key scaffolding flags:
- `--agent adk`: Targets the official Google Agent Development Kit framework template.
- `--deployment-target agent_runtime`: Configures serverless hosting on Vertex AI Agent Runtime (Reasoning Engine).
- `--prototype`: Enables rapid iteration on agent instructions and tools before generating CI/CD pipelines.

To add deployment configuration to an existing project at any time:
```bash
agents-cli scaffold enhance . --deployment-target agent_runtime
```

The scaffolding metadata is stored in `agents-cli-manifest.yaml`, allowing subsequent CLI commands (`deploy`, `publish`, `run`) to execute seamlessly without redundant parameters.

### 3. Set Up Python Virtual Environment
```bash
# Verify Python version (3.10+)
python3 --version

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Google Cloud Project & Enable APIs
```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
gcloud config set project "$GOOGLE_CLOUD_PROJECT"

# Enable all required APIs for Agent Runtime & Agent Registry
gcloud services enable \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com \
  recommender.googleapis.com \
  discoveryengine.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$GOOGLE_CLOUD_PROJECT"
```

### 5. Test Locally (No Cloud Deployment)

#### Test A: Verify Remote MCP Tool Discovery
```bash
gcloud auth application-default login

python test_client.py
```

#### Test B: Run Conversational Prompts via ADK Runner
```bash
# Enable Vertex AI for LLM reasoning with Application Default Credentials
export GOOGLE_GENAI_USE_VERTEXAI=true

# Run a test prompt
python test_chat.py "What recommendations can you provide for persistent disks?"
```

#### Test C: Visual Browser Chat via `adk web`
```bash
# Start ADK development server with Web UI pointing to gcp_agent
adk web --port 8085 gcp_agent

# Open http://127.0.0.1:8085/dev-ui/ in your browser
```

---

### 6. Deploy to Agent Runtime & Publish to Gemini Enterprise

#### Automated Deployment via Script
```bash
export GOOGLE_CLOUD_REGION="us-central1"
export GEMINI_ENTERPRISE_APP_ID="projects/PROJECT_NUMBER/locations/global/collections/default_collection/engines/APP_ID"

chmod +x deploy.sh
./deploy.sh
```

#### Step-by-Step Deployment via `agents-cli`
Deploy directly to Google Cloud Agent Runtime:

```bash
agents-cli deploy \
  --deployment-target="agent_runtime" \
  --project="$GOOGLE_CLOUD_PROJECT" \
  --region="$GOOGLE_CLOUD_LOCATION" \
  --service-name="gcp-recommender-agent" \
  --service-account="mcp-bridge-agent-sa@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com" \
  --update-env-vars="ACTIVE_MCP_SERVICE=recommender,GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}"
```

Check deployment status at any time:
```bash
agents-cli deploy --status
```

#### Automatic Cataloging in Google Cloud Agent Registry
When deployed to Agent Runtime, Google Cloud **automatically catalogs** the agent in Agent Registry:

```bash
gcloud alpha agent-registry agents list \
  --project="$GOOGLE_CLOUD_PROJECT" \
  --location="$GOOGLE_CLOUD_LOCATION"
```

#### Publish to Gemini Enterprise App via `agents-cli`
1. List available Gemini Enterprise apps in your project:
```bash
agents-cli publish gemini-enterprise --list
```

2. Bind the deployed agent to your Gemini Enterprise App:
```bash
agents-cli publish gemini-enterprise \
  --gemini-enterprise-app-id="projects/PROJECT_NUMBER/locations/global/collections/default_collection/engines/APP_ID" \
  --display-name="GCP Recommender Agent" \
  --description="Audits Google Cloud resources and discovers cost optimization recommendations using Google's remote MCP server." \
  --tool-description="Audits Google Cloud resources for idle persistent disks, underutilized VMs, and cost savings." \
  --deployment-target="agent_runtime" \
  --registration-type="adk"
```

*(Or simply run `agents-cli publish gemini-enterprise --interactive` to be guided through app selection interactively!)*

#### Test Deployed Agent via `agents-cli run`
```bash
agents-cli run \
  --mode="adk" \
  "Check for idle persistent disks in project ${GOOGLE_CLOUD_PROJECT} in zone us-central1-a"
```

---

## Switching to Other Google Cloud MCP Services

Set the `ACTIVE_MCP_SERVICE` environment variable to switch to another Google Cloud remote MCP server:

```bash
# Switch to Compute Engine Remote MCP
export ACTIVE_MCP_SERVICE="compute"

# Switch to BigQuery Remote MCP
export ACTIVE_MCP_SERVICE="bigquery"
```
