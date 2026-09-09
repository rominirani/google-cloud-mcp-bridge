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
                             ▼ Native ADK Invocation (:streamQuery)
 ┌────────────────────────────────────────────────────────┐
 │ 2. Agent Runtime (Gemini Enterprise Agent Platform)    │
 │    - Native ADK root_agent                             │
 │    - Auto-cataloged in Google Cloud Agent Registry     │
 │    - skills/recommender/SKILL.md (Instructions)        │
 │    - Native McpToolset (Zero custom client code)       │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼ JSON-RPC over HTTPS (OAuth2 Bearer token)
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
│   └── agent.py          # Native ADK Agent using McpToolset + Reasoning Engine routes
├── agent.py              # Root wrapper re-exporting from gcp_agent
├── skills/
│   └── recommender/
│       └── SKILL.md      # Skill instructions for cost and idle resource analysis
├── Dockerfile            # Container image build for Agent Runtime / Cloud Run
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

### 2. Set Up Python Virtual Environment
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

### 3. Configure Google Cloud Project & Enable APIs
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

### 4. Test Locally (No Cloud Deployment)

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

### 5. Deploy to Agent Runtime & Publish to Gemini Enterprise

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
