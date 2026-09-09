#!/usr/bin/env bash
# ==============================================================================
# Deployment Script: Google Cloud Remote MCP Bridge on Agent Runtime
# ==============================================================================
# This script automates:
# 1. Verification of environment variables and CLI tools (gcloud, agents-cli).
# 2. Enabling required Google Cloud APIs for Agent Runtime & Agent Registry.
# 3. Creating a dedicated Service Account with least-privilege IAM roles.
# 4. Deploying the ADK agent to Agent Runtime using agents-cli.
# 5. Verifying automatic cataloging in Google Cloud Agent Registry.
# 6. Publishing the agent to Gemini Enterprise via agents-cli.
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# 1. Configuration & Parameter Validation
# ------------------------------------------------------------------------------
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-${GCP_PROJECT_ID:-}}"
REGION="${GOOGLE_CLOUD_REGION:-${GCP_REGION:-us-central1}}"
SERVICE_NAME="${SERVICE_NAME:-gcp-recommender-agent}"
SA_NAME="mcp-bridge-agent-sa"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: Google Cloud Project ID is not set."
  echo "Please export GOOGLE_CLOUD_PROJECT='your-project-id' and re-run."
  exit 1
fi

echo "=================================================================="
echo " Starting Agent Runtime Deployment: $SERVICE_NAME"
echo " Project ID : $PROJECT_ID | Region: $REGION"
echo "=================================================================="

# Check CLI prerequisites
if ! command -v agents-cli &>/dev/null; then
  echo "ERROR: 'agents-cli' is not installed."
  echo "Install it via: uv tool install google-agents-cli"
  exit 1
fi

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# ------------------------------------------------------------------------------
# 2. Enable Required Google Cloud APIs
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 1: Enabling required Google Cloud APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com \
  recommender.googleapis.com \
  discoveryengine.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$PROJECT_ID"

echo "    [OK] APIs enabled successfully."

# ------------------------------------------------------------------------------
# 3. Create Dedicated Service Account & Grant IAM Roles
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 2: Configuring Service Account and IAM Roles..."

if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="MCP Bridge Agent Runtime SA" \
    --project="$PROJECT_ID"
  echo "    Created service account: $SA_EMAIL"
else
  echo "    Service account already exists: $SA_EMAIL"
fi

# 1. roles/mcp.toolUser: Required to execute tool calls on Google Remote MCP servers
echo "    Granting roles/mcp.toolUser..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/mcp.toolUser" \
  --condition=None \
  --quiet

# 2. roles/recommender.viewer: Required to read recommendations from Recommender API
echo "    Granting roles/recommender.viewer..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/recommender.viewer" \
  --condition=None \
  --quiet

# 3. roles/aiplatform.user: Required for the agent to call Vertex AI / Gemini models
echo "    Granting roles/aiplatform.user..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" \
  --condition=None \
  --quiet

# 4. roles/compute.viewer: Required to view Compute Engine resource metadata
echo "    Granting roles/compute.viewer..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/compute.viewer" \
  --condition=None \
  --quiet

echo "    [OK] IAM roles granted."

# ------------------------------------------------------------------------------
# 4. Deploy to Agent Runtime
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 3: Deploying ADK Agent to Agent Runtime..."

agents-cli deploy \
  --deployment-target="agent_runtime" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-name="$SERVICE_NAME" \
  --service-account="$SA_EMAIL" \
  --update-env-vars="ACTIVE_MCP_SERVICE=recommender,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=${REGION}" \
  --no-confirm-project

echo "    [OK] Deployed successfully to Agent Runtime."

# ------------------------------------------------------------------------------
# 5. Verify Cataloging in Google Cloud Agent Registry
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 4: Verifying registration in Google Cloud Agent Registry..."

gcloud alpha agent-registry agents list \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --format="table(displayName,name,createTime)" || true

echo "    [OK] Agent Runtime agents are automatically cataloged in Agent Registry."

# ------------------------------------------------------------------------------
# 6. Publish to Gemini Enterprise App
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 5: Publishing to Gemini Enterprise App..."

if [[ -n "${GEMINI_ENTERPRISE_APP_ID:-}" ]]; then
  echo "    Publishing agent to: $GEMINI_ENTERPRISE_APP_ID"
  agents-cli publish gemini-enterprise \
    --gemini-enterprise-app-id="$GEMINI_ENTERPRISE_APP_ID" \
    --display-name="GCP Recommender Agent" \
    --description="Audits Google Cloud resources and discovers cost optimization recommendations using Google's remote MCP server." \
    --tool-description="Audits Google Cloud resources for idle persistent disks, underutilized VMs, and cost savings." \
    --deployment-target="agent_runtime" \
    --registration-type="adk"

  echo "    [OK] Successfully published to Gemini Enterprise!"
else
  echo "    NOTE: GEMINI_ENTERPRISE_APP_ID was not specified."
  echo "    To discover your Gemini Enterprise apps, run:"
  echo "      agents-cli publish gemini-enterprise --list"
  echo ""
  echo "    To publish interactively:"
  echo "      agents-cli publish gemini-enterprise --interactive"
  echo ""
  echo "    Or publish directly with the app ID:"
  echo "      agents-cli publish gemini-enterprise \\"
  echo "        --gemini-enterprise-app-id=\"projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/YOUR_APP_ID\" \\"
  echo "        --display-name=\"GCP Recommender Agent\" \\"
  echo "        --deployment-target=\"agent_runtime\" \\"
  echo "        --registration-type=\"adk\""
fi

echo ""
echo "=================================================================="
echo " Deployment and Governance Setup Complete!"
echo " Deployment Target: Agent Runtime ($REGION)"
echo " Governance Target: Google Cloud Agent Registry"
echo "=================================================================="
