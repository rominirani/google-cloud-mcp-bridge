"""Local verification test for ADK Agent with Google Cloud Remote MCP Server.

Run this script to verify that the ADK agent successfully connects to the
Google Cloud remote MCP endpoint and discovers tools using McpToolset.

Usage:
    python test_client.py
"""

import asyncio
from agent import root_agent


async def main():
    print("=" * 60)
    print(" ADK Remote MCP Toolset - Connection Test")
    print("=" * 60)
    print(f"Agent Name : {root_agent.name}")
    print(f"Model      : {root_agent.model}")
    print("-" * 60)

    print("Fetching tools via native ADK McpToolset...")
    try:
        # Get tools from the configured McpToolset
        mcp_toolset = root_agent.tools[0]
        tools = await mcp_toolset.get_tools()
        print(f"  [SUCCESS] Discovered {len(tools)} tools from Google Cloud:\n")
        for idx, tool in enumerate(tools, 1):
            name = getattr(tool, "name", str(tool))
            desc = getattr(tool, "description", "No description provided.")
            print(f"  {idx}. {name}")
            print(f"     Description: {desc[:100]}..." if len(desc) > 100 else f"     Description: {desc}")
    except Exception as e:
        print(f"  [FAILED] Error discovering tools: {e}")
        print("\nTroubleshooting:")
        print("1. Run 'gcloud auth application-default login' to refresh local credentials.")
        print("2. Ensure your GCP identity has 'roles/mcp.toolUser' and 'roles/recommender.viewer'.")
        return

    print("\n" + "=" * 60)
    print(" All connection checks passed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
