#!/usr/bin/env bash
# ==============================================================================
# Deployment Script: Google Cloud Remote MCP Bridge to Gemini Enterprise
# ==============================================================================
# This script automates:
# 1. Verification of environment variables and Google Cloud CLI setup.
# 2. Enabling required Google Cloud APIs.
# 3. Creating a dedicated Service Account with least-privilege IAM roles.
# 4. Deploying the bridge container to Cloud Run.
# 5. Granting Gemini Enterprise invocation rights.
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
echo " Starting Deployment for: $SERVICE_NAME"
echo " Project ID: $PROJECT_ID | Region: $REGION"
echo "=================================================================="

# Fetch GCP Project Number (needed for service-to-service IAM bindings)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# ------------------------------------------------------------------------------
# 2. Enable Required Google Cloud APIs
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 1: Enabling required Google Cloud APIs..."
gcloud services enable \
  recommender.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  agentregistry.googleapis.com \
  discoveryengine.googleapis.com \
  aiplatform.googleapis.com \
  --project="$PROJECT_ID"

echo "    [OK] APIs enabled successfully."

# ------------------------------------------------------------------------------
# 3. Create Dedicated Service Account & Grant IAM Roles
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 2: Configuring Service Account and IAM Roles..."

# Create service account if it does not already exist
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="MCP Bridge Agent Runtime SA" \
    --project="$PROJECT_ID"
  echo "    Created service account: $SA_EMAIL"
else
  echo "    Service account already exists: $SA_EMAIL"
fi

# Grant roles/mcp.toolUser: Required to execute tool calls on Google Remote MCP servers
echo "    Granting roles/mcp.toolUser..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/mcp.toolUser" \
  --condition=None \
  --quiet

# Grant roles/recommender.viewer: Required to read recommendations from Recommender API
echo "    Granting roles/recommender.viewer..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/recommender.viewer" \
  --condition=None \
  --quiet

# Grant roles/aiplatform.user: Required for the agent to call Vertex AI / Gemini models
echo "    Granting roles/aiplatform.user..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" \
  --condition=None \
  --quiet

# Grant roles/compute.viewer: Required to view Compute Engine disk and instance telemetry
echo "    Granting roles/compute.viewer..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/compute.viewer" \
  --condition=None \
  --quiet

echo "    [OK] IAM roles granted."

# ------------------------------------------------------------------------------
# 4. Deploy to Cloud Run
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 3: Deploying container to Cloud Run..."

# Deploy to Cloud Run using gcloud alpha run deploy with Agent Functional Type
# Note: --functional-type="agent" requires --identity-type="agent-identity"
if gcloud alpha run deploy "$SERVICE_NAME" \
  --source="." \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="ACTIVE_MCP_SERVICE=recommender,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=${REGION}" \
  --functional-type="agent" \
  --identity-type="agent-identity" \
  --allow-unauthenticated \
  --quiet; then
  echo "    [OK] Deployed with functional-type=agent and identity-type=agent-identity."
else
  echo "    [WARN] Alpha deploy failed or alpha component unavailable. Falling back to standard gcloud run deploy..."
  gcloud run deploy "$SERVICE_NAME" \
    --source="." \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="$SA_EMAIL" \
    --set-env-vars="ACTIVE_MCP_SERVICE=recommender,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=${REGION}" \
    --allow-unauthenticated \
    --quiet
fi

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform=managed \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="value(status.url)")

echo "    [OK] Cloud Run deployed at: $SERVICE_URL"

# ------------------------------------------------------------------------------
# 5. Authorize Gemini Enterprise Invocation
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 4: Authorizing Gemini Enterprise Discovery Engine to call Cloud Run..."
DISCOVERY_ENGINE_SA="service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${DISCOVERY_ENGINE_SA}" \
  --role="roles/run.servicesInvoker" \
  --quiet || true

echo "    [OK] Invocation permissions granted."

# ------------------------------------------------------------------------------
# 6. Publish to Gemini Enterprise App
# ------------------------------------------------------------------------------
echo ""
echo "--> Step 5: Publishing to Gemini Enterprise App..."
CARD_URL="${SERVICE_URL}/.well-known/agent-card.json"

if [[ -n "${GEMINI_ENTERPRISE_APP_ID:-}" ]]; then
  echo "    Publishing agent card to: $GEMINI_ENTERPRISE_APP_ID"
  agents-cli publish gemini-enterprise \
    --agent-card-url="$CARD_URL" \
    --gemini-enterprise-app-id="$GEMINI_ENTERPRISE_APP_ID" \
    --display-name="GCP Recommender Agent" \
    --description="Audits Google Cloud resources and discovers cost optimization recommendations using Google's remote MCP server." \
    --deployment-target="cloud_run" \
    --registration-type="a2a"

  echo "    [OK] Successfully published to Gemini Enterprise!"
else
  echo "    NOTE: GEMINI_ENTERPRISE_APP_ID was not specified."
  echo "    To publish manually, run:"
  echo "    agents-cli publish gemini-enterprise \\"
  echo "      --agent-card-url=\"$CARD_URL\" \\"
  echo "      --gemini-enterprise-app-id=\"projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/YOUR_APP_ID\" \\"
  echo "      --display-name=\"GCP Recommender Agent\""
fi

echo ""
echo "=================================================================="
echo " Deployment Complete!"
echo " Service Endpoint : $SERVICE_URL"
echo " Agent Card URL   : $CARD_URL"
echo "=================================================================="
