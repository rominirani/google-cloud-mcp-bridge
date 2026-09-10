# Google Cloud Remote MCP Bridge to Gemini Enterprise

A production-ready reference architecture connecting **Model Context Protocol (MCP) servers** and **Agent Skills** to **Gemini Enterprise** using the **Google Agent Development Kit (ADK)** and **Vertex AI Agent Runtime**.

---

## The Vision: Combining MCP Servers with Skills in Gemini Enterprise

An enterprise AI assistant requires two distinct, complementary dimensions to deliver dependable business value:
1. **The "Hands" (Tool Execution)**: Provided by the **Model Context Protocol (MCP)**. Remote MCP servers expose standardized, discoverable APIs, databases, and services to LLMs via JSON-RPC contracts (`tools/list` and `tools/call`).
2. **The "Playbook" (Domain Intelligence)**: Provided by **Agent Skills (`SKILL.md`)**. Skills codify domain expertise, standard operating procedures (SOPs), multi-step investigation logic, mathematical reasoning formulas, output formatting contracts, and guardrails.

By pairing an **MCP Server** with an **Agent Skill** inside the **Google Agent Development Kit (ADK)** and hosting it on **Vertex AI Agent Runtime**, we create a governed, enterprise-grade AI teammate surfaced directly in **Gemini Enterprise**—where employees and teams collaborate daily.

```mermaid
flowchart LR
    subgraph Inputs ["1. Agent Composition"]
        MCP["<b>Remote MCP Server</b><br/><i>(Actions & Tools)</i><br/>• Google-Managed (Recommender, BigQuery...)<br/>• Or your own Custom MCP Server"]
        Skill["<b>Agent Skill (SKILL.md)</b><br/><i>(Playbook & SOPs)</i><br/>• Investigation protocols<br/>• Calculations & synthesis<br/>• Executive formatting & safety"]
    end

    subgraph Runtime ["2. Runtime & Governance"]
        ADK["<b>ADK Agent Bridge</b><br/><i>(google-adk[mcp])</i><br/>Dynamic Auth + Tool Binding"]
        VAI["<b>Vertex AI Agent Runtime</b><br/><i>(Serverless Reasoning Engine)</i>"]
        Registry["<b>Google Cloud Agent Registry</b><br/><i>(Central Fleet Catalog)</i>"]
    end

    subgraph Experience ["3. Enterprise Consumption"]
        GE["<b>Gemini Enterprise App</b><br/><i>(Corporate Conversational Portal)</i>"]
        User(["<b>Enterprise Users</b><br/><i>(FinOps, SREs, Product, Execs)</i>"])
    end

    MCP --> ADK
    Skill --> ADK
    ADK --> VAI
    VAI -.->|Auto-Catalog| Registry
    Registry -.->|Bind & Publish| GE
    VAI -->|Streaming Event Chunks| GE
    User <-->|Natural Language Chat| GE
```

### Value Proposition

- **Democratizing Enterprise Operations**: Enables non-technical stakeholders (FinOps, product managers, leadership) to audit, inspect, and interact with live cloud infrastructure using conversational natural language.
- **Universal Blueprint (Google-Managed or Custom MCP Servers)**: While this implementation uses Google Cloud's **Recommender MCP Server**, the architecture is 100% generic:
  - Connect to **any Google-managed remote MCP server** (Compute Engine, BigQuery, Cloud Storage, Billing).
  - Connect to **your own custom remote MCP server** (internal enterprise microservices, ServiceNow, ERP, or CMDB) with identical runtime and publishing mechanics.
- **Automated Fleet Governance**: Deploying to Agent Runtime automatically registers your agent in **Google Cloud Agent Registry**.

### Why Wrap an MCP Server with a Skill? (Skill vs. Raw MCP Server)

Exposing a raw MCP server directly to an LLM provides tools without context. Wrapping the MCP server with an **Agent Skill (`SKILL.md`)** transforms raw endpoints into a trusted colleague:

| Dimension | Exposing Raw MCP Server Directly | Wrapping MCP Server with an Agent Skill (`SKILL.md`) |
| :--- | :--- | :--- |
| **Operational Playbook (SOPs)** | **Absent**: Model sees flat functions (`list_recommendations`) without knowing execution order or scoping rules. | **Deterministic**: Skill establishes standard operating procedures: scoping project/zone, checking specific recommenders, and ranking findings. |
| **Data Interpretation** | **Unstructured**: Raw multi-megabyte JSON payloads lead to hallucinated summaries or unformatted dumps. | **Quantitative Synthesis**: Skill directs extraction of monetary savings (`primaryImpact.costProjection`), annual run-rate math, and executive Markdown tables. |
| **Actionable Remediation** | **Passive**: Highlights issues without verified paths to resolve them. | **Actionable Solutions**: Generates tested, copy-pasteable `gcloud` CLI commands or remediation steps with safety notices. |
| **Guardrails & Safety** | **Uncontrolled**: Risk of accidental mutations or parameter hallucinations. | **Strictly Governed**: Enforces read-only defaults and requires explicit user confirmation before destructive actions. |

> **Key Takeaway**: An MCP server gives an AI assistant **hands**; a Skill gives it **judgment**.

---

## Project Structure

```
google-cloud-mcp-bridge/
├── gcp_agent/            # ADK Agent package
│   ├── __init__.py       # Exports root_agent for ADK loader
│   └── agent.py          # Native ADK Agent using McpToolset & Reasoning Engine routes
├── skills/
│   └── recommender/
│       └── SKILL.md      # Skill instructions for cost and idle resource analysis
├── agents-cli-manifest.yaml # Project descriptor and deployment target metadata
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

> [!IMPORTANT]
> **Using the Companion Repository? You Can Skip `scaffold create`!**
> 
> If you have cloned this repository, **you do not need to run `agents-cli scaffold create`**. The entire project layout, virtual environment setup, ADK agent logic, skill instructions, and configuration files are already pre-assembled for you. Proceed directly to **Step 3 (Set Up Python Virtual Environment)**.
> 
> **If you prefer to scaffold your own project from scratch:**
> 1. Run the `agents-cli scaffold create` command below to generate a fresh ADK project skeleton.
> 2. Then, copy over the essential bridge files from this repository into your new project:
>    - `gcp_agent/agent.py` — The core ADK Agent definition with `McpToolset` and Vertex AI Reasoning Engine routes.
>    - `gcp_agent/__init__.py` — Package entrypoint exposing `root_agent`.
>    - `skills/recommender/SKILL.md` — Domain reasoning instructions for analyzing idle disks and cloud spend.
>    - `requirements.txt` — Project dependencies (`google-adk[mcp,gcp]`).
>    - `test_client.py` & `test_chat.py` — Local validation scripts.
>    - `deploy.sh` — Deployment and Gemini Enterprise registration script.

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

# Enable required APIs for Agent Runtime, Agent Registry, and Gemini Enterprise
gcloud services enable \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com \
  recommender.googleapis.com \
  discoveryengine.googleapis.com \
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
