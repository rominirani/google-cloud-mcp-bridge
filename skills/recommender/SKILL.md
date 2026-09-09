---
name: gcp-recommender-finops
metadata:
  category: CloudManagement
description: >
  Audits Google Cloud resources, fetches cost optimization and right-sizing
  recommendations, and summarizes potential financial savings using the Google Cloud
  Recommender remote MCP server. Use when users ask to analyze GCP costs, find idle
  disks or VMs, optimize cloud spend, or review resource efficiency.
---

# Google Cloud Recommender & FinOps Skill

This skill instructs the agent on how to use the Google Cloud Recommender remote MCP
server tools to audit projects, find unused cloud resources, and generate structured
cost optimization reports.

## Available Tools from Remote MCP Server

The remote MCP server (`https://recommender.googleapis.com/mcp`) exposes the following tools:

- `list_recommendations`: Retrieves active recommendations for a given project, location, and recommender type.
  - **Required argument**: `parent` (Format: `projects/<project_id>/locations/<location>/recommenders/<recommender_id>`)
- `get_recommendation`: Fetches complete details for a specific recommendation ID.
  - **Required argument**: `name` (Full recommendation resource path)
- `list_insights`: Retrieves underlying telemetry insights backing recommendations.
- `get_insight`: Fetches details of a specific insight.

---

## Supported Recommender IDs

When a user asks to review a project, map their request to the appropriate Recommender ID:

| User Intent | Recommender ID | Location Scope |
| :--- | :--- | :--- |
| **Idle VMs** | `google.compute.instance.IdleResourceRecommender` | Regional or Zonal (e.g. `us-central1-a`) |
| **Idle Persistent Disks** | `google.compute.disk.IdleResourceRecommender` | Regional or Zonal |
| **VM Right-Sizing** | `google.compute.instance.MachineTypeRecommender` | Regional or Zonal |
| **Committed Use Discounts** | `google.compute.commitment.UsageCommitmentRecommender` | Regional / Global |
| **IAM Over-privilege** | `google.iam.policy.Recommender` | `global` |

---

## Workflow Steps

When a user asks for a project audit or cost analysis, follow these steps sequentially:

### Step 1: Identify Project and Scope
- If the user does not mention a Google Cloud project ID, ask for it before proceeding.
- If the user does not specify a region, check common zones or run a search across primary project regions.

### Step 2: Fetch Recommendations
- Formulate the `parent` path string:
  `projects/<PROJECT_ID>/locations/<LOCATION>/recommenders/<RECOMMENDER_ID>`
- Execute `list_recommendations` for the relevant recommender types (idle disks, idle instances, right-sizing).

### Step 3: Calculate and Triage Impact
- Inspect the `primaryImpact` object on each returned recommendation:
  - Extract the projected currency code and amount: `primaryImpact.costProjection.cost.units` and `nanos`.
  - Negative cost indicates **savings** (money saved by taking action).
- Filter out recommendations marked as `CLAIMED` or `DISMISSED`. Focus only on `ACTIVE` items.

### Step 4: Output Presentation
Always present findings in an executive-ready Markdown table:

```markdown
### Summary of Findings for Project: [PROJECT_ID]

| Resource Type | Resource Name | Issue Identified | Estimated Monthly Savings | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| Persistent Disk | `disk-data-archive` | Unattached for > 14 days | $45.00 / month | Snapshot and delete disk |
| Compute Engine | `staging-web-vm` | CPU utilization < 2% | $112.50 / month | Stop or downsize instance |

**Total Estimated Monthly Savings**: $157.50 / month  
**Total Estimated Annual Savings**: $1,890.00 / year
```

---

## Safety and Guardrail Rules

1. **Read-Only Operation**: This skill is strictly designed for discovery, reporting, and recommendations.
2. **Explicit Confirmation Required**: Never execute remediation commands (such as deleting disks or stopping VMs) without showing the user the exact resource name, projected savings, and asking for explicit confirmation.
3. **Transparent Assumptions**: If cost estimates are projections based on 730 hours/month, state this clearly in the summary notes.
