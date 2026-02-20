"""CLI runner that starts the conversational setup assistant loop.

Uses the ADK ``Runner`` with ``InMemorySessionService`` to drive a real
Gemini-powered conversation.  Falls back gracefully when no API key is set.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from ninja_cli.state import init_state
from ninja_core.schema.project import AgenticSchema

from ninja_setup_assistant.assistant import APP_NAME, create_setup_agent, has_api_key
from ninja_setup_assistant.tools import SchemaWorkspace, confirm_schema, review_schema


async def run_assistant(
    project_name: str = "my-ninja-project",
    root: Path = Path("."),
) -> AgenticSchema | None:
    """Run the interactive setup assistant loop.

    Args:
        project_name: Name for the new project.
        root: Project root directory.

    Returns:
        The finalized AgenticSchema, or ``None`` if the user cancelled.
    """
    init_state(project_name, root)

    if not has_api_key():
        print("Error: No Gemini API key found.\nSet GOOGLE_API_KEY or GOOGLE_GENAI_API_KEY to use the setup assistant.")
        return None

    workspace = SchemaWorkspace(schema=AgenticSchema(project_name=project_name))
    agent = create_setup_agent(workspace)

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "local_user"
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    print("=" * 60)
    print("  Ninja Stack Setup Assistant")
    print("=" * 60)
    print()
    print("Type 'quit' or 'exit' to cancel.")
    print("Type 'review' to see the current schema.")
    print("Type 'done' to finalize the schema.")
    print()

    # Initial greeting
    greeting = await _send_message(runner, user_id, session.id, "Hello, I want to set up a new project.")
    print(f"Assistant: {greeting}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return None

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Setup cancelled.")
            return None

        if user_input.lower() == "review":
            summary = review_schema(workspace)
            print(f"\n{summary}\n")
            continue

        if user_input.lower() == "done":
            schema_json = confirm_schema(workspace)
            if schema_json.startswith("Cannot confirm"):
                print(f"\n{schema_json}\n")
                continue

            state_dir = root / ".ninjastack"
            state_dir.mkdir(parents=True, exist_ok=True)
            schema_path = state_dir / "schema.json"
            schema_path.write_text(schema_json + "\n", encoding="utf-8")

            schema = workspace.schema
            print(f"\nSchema saved to {schema_path}")
            print(f"  Entities: {len(schema.entities)}")
            print(f"  Relationships: {len(schema.relationships)}")
            print(f"  Domains: {len(schema.domains)}")
            return schema

        # Normal conversational turn via ADK runner
        response = await _send_message(runner, user_id, session.id, user_input)
        print(f"\nAssistant: {response}\n")


async def _send_message(
    runner: Runner,
    user_id: str,
    session_id: str,
    message: str,
) -> str:
    """Send a single message through the ADK runner and collect the response."""
    content = Content(role="user", parts=[Part(text=message)])
    collected: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    collected.append(part.text)

    return "\n".join(collected) if collected else "(No response)"


def main() -> None:
    """Entry point for ``ninjastack init`` with the setup assistant."""
    project_name = "my-ninja-project"
    if len(sys.argv) > 1:
        project_name = sys.argv[1]

    result = asyncio.run(run_assistant(project_name=project_name))
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
