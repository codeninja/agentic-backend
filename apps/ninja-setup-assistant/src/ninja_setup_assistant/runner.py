"""CLI runner that starts the conversational setup assistant loop.

Integrates with the ninja-cli ``init`` command to provide an interactive
schema-design experience.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ninja_cli.state import init_state
from ninja_core.schema.project import AgenticSchema

from ninja_setup_assistant.assistant import SetupAssistant
from ninja_setup_assistant.tools import confirm_schema, review_schema


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
    # Initialize project state
    init_state(project_name, root)

    assistant = SetupAssistant(project_name=project_name)

    print("=" * 60)
    print("  Ninja Stack Setup Assistant")
    print("=" * 60)
    print()
    print("Type 'quit' or 'exit' to cancel.")
    print("Type 'review' to see the current schema.")
    print("Type 'done' to finalize the schema.")
    print()

    # Initial greeting
    greeting = await assistant.chat("Hello, I want to set up a new project.")
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
            summary = review_schema(assistant.workspace)
            print(f"\n{summary}\n")
            continue

        if user_input.lower() == "done":
            schema_json = confirm_schema(assistant.workspace)
            if schema_json.startswith("Cannot confirm"):
                print(f"\n{schema_json}\n")
                continue

            # Write the finalized schema
            state_dir = root / ".ninjastack"
            state_dir.mkdir(parents=True, exist_ok=True)
            schema_path = state_dir / "schema.json"
            schema_path.write_text(schema_json + "\n", encoding="utf-8")

            schema = assistant.workspace.schema
            print(f"\nSchema saved to {schema_path}")
            print(f"  Entities: {len(schema.entities)}")
            print(f"  Relationships: {len(schema.relationships)}")
            print(f"  Domains: {len(schema.domains)}")
            return schema

        # Normal conversational turn
        response = await assistant.chat(user_input)
        print(f"\nAssistant: {response}\n")


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
