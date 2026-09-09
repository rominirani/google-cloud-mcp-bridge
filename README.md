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
 ┌────────────────────────────────────────────────────────┐
 │ 1. End User in Gemini Enterprise Web Chat              │
 │    "What idle resources can we clean up in prod?"     │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼ A2A Invocation
 ┌────────────────────────────────────────────────────────┐
 │ 2. Cloud Run Service                                   │
 │    - agent.py (ADK root_agent + A2A endpoint)          │
 │    - skills/recommender/SKILL.md (Instructions)        │
 │    - Native McpToolset (Zero custom client code)       │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼ JSON-RPC over HTTP (Bearer token)
 ┌────────────────────────────────────────────────────────┐
 │ 3. Google-Managed Remote MCP Server                    │
 │    https://recommender.googleapis.com/mcp              │
 └────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
google-cloud-mcp-bridge/
├── gcp_agent/            # ADK Agent package (valid Python module for ADK loader)
│   ├── __init__.py       # Exports root_agent for ADK loader
│   └── agent.py          # Native ADK Agent using McpToolset + A2A endpoint
├── agent.py              # Root wrapper re-exporting from gcp_agent for backward compatibility
├── skills/
│   └── recommender/
│       └── SKILL.md      # Skill instructions for cost and idle resource analysis
├── Dockerfile            # Container image build for Cloud Run
├── requirements.txt      # Python dependencies (google-adk[mcp,gcp,a2a])
├── test_client.py        # Local script to verify ADK McpToolset discovery
├── test_chat.py          # Local script to run conversational prompts via ADK Runner
├── deploy.sh             # Script to deploy to Cloud Run and publish via agents-cli
└── README.md             # Project documentation
```

---

## Quickstart

### 1. Set Up Python Virtual Environment
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

### 2. Configure Google Cloud Project & Enable APIs
```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
gcloud config set project "$GOOGLE_CLOUD_PROJECT"

# Enable all required APIs
gcloud services enable \
  recommender.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  agentregistry.googleapis.com \
  discoveryengine.googleapis.com \
  aiplatform.googleapis.com \
  --project="$GOOGLE_CLOUD_PROJECT"
```

### 3. Test Locally (No Cloud Deployment)

#### Test A: Verify Remote MCP Tool Discovery
```bash
gcloud auth application-default login

python test_client.py
```

#### Test B: Run Conversational Prompts via ADK Runner
```bash
# Enable Vertex AI for LLM reasoning with Application Default Credentials
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"

# Run a test prompt
python test_chat.py "What recommendations can you provide for persistent disks?"
```

#### Test C: Test FastAPI & A2A Endpoints Locally
```bash
# Start local server
uvicorn agent:app --host 0.0.0.0 --port 8080

# In another terminal: verify health check & Agent Card
curl http://localhost:8080/healthz
curl http://localhost:8080/.well-known/agent-card.json
```

#### Test D: Visual Browser Chat via `adk web`
```bash
# Start ADK development server with Web UI and A2A endpoints pointing to gcp_agent
adk web --port 8085 --a2a gcp_agent

# Open http://127.0.0.1:8085/dev-ui/ in your browser
```

### 4. Deploy to Cloud Run and Publish to Gemini Enterprise
```bash
export GOOGLE_CLOUD_REGION="us-central1"
export GEMINI_ENTERPRISE_APP_ID="projects/PROJECT_NUMBER/locations/global/collections/default_collection/engines/APP_ID"

chmod +x deploy.sh
./deploy.sh
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
