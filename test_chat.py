"""Local test script to run conversational prompts through the ADK agent.

Usage:
    # Using Vertex AI with Application Default Credentials:
    export GOOGLE_GENAI_USE_VERTEXAI=true
    export GOOGLE_CLOUD_PROJECT="your-project-id"
    export GOOGLE_CLOUD_LOCATION="us-central1"

    python test_chat.py "Hello! What tools do you have?"
    python test_chat.py "Audit project my-project-id for idle persistent disks"

    # Alternatively, using a Gemini API Key:
    export GEMINI_API_KEY="your-api-key"
    python test_chat.py
"""

import asyncio
import os
import sys
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agent import root_agent


async def main():
    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Hello! What cost optimization tools do you have available?"
    )

    print("=" * 60)
    print(" ADK Local Agent Runner Test")
    print("=" * 60)
    print(f"Agent Name : {root_agent.name}")
    print(f"Model      : {root_agent.model}")
    print(f"User Prompt: {prompt}")
    print("-" * 60)

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="gcp_agent", user_id="local_tester", session_id="local_session"
    )

    runner = Runner(
        agent=root_agent, app_name="gcp_agent", session_service=session_service
    )

    print("Agent processing prompt (reasoning and calling remote MCP tools)...")
    try:
        async for event in runner.run_async(
            user_id="local_tester",
            session_id="local_session",
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=prompt)]
            ),
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    print("\nAgent Response:\n")
                    print(event.content.parts[0].text)
                else:
                    print("\n[INFO] Response completed with no content.")
    except Exception as e:
        print(f"\n[ERROR] Runner execution failed: {e}")
        print("\nTroubleshooting:")
        print("1. For Vertex AI: export GOOGLE_GENAI_USE_VERTEXAI=true and GOOGLE_CLOUD_PROJECT=your-project-id")
        print("2. For Gemini API: export GEMINI_API_KEY=your-api-key")
        print("3. Ensure 'gcloud auth application-default login' is active.")


if __name__ == "__main__":
    asyncio.run(main())
