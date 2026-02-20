"""Main ADK agent definition for the Ninja Setup Assistant.

Creates a real ``LlmAgent`` powered by Gemini with schema-manipulation tools.
When no API key is configured the module falls back to a lightweight stub so
that the tool layer remains fully testable without LLM calls.
"""

from __future__ import annotations

import os
from typing import Any

from google.adk.agents import LlmAgent
from ninja_core.schema.project import AgenticSchema

from ninja_setup_assistant.prompts import SETUP_ASSISTANT_PROMPT
from ninja_setup_assistant.tools import SchemaWorkspace, create_adk_tools

# Default model — matches the project convention in ninja-agents.
_DEFAULT_MODEL = "gemini-2.5-pro"

# Application name used by the ADK runner / session service.
APP_NAME = "ninja_setup_assistant"


def create_setup_agent(
    workspace: SchemaWorkspace,
    *,
    model: str = _DEFAULT_MODEL,
) -> LlmAgent:
    """Create the setup assistant ``LlmAgent`` bound to *workspace*.

    The returned agent has six tools (add_entity, add_relationship,
    create_domain, review_schema, confirm_schema, introspect_database)
    that operate on the shared workspace.
    """
    tools = create_adk_tools(workspace)
    return LlmAgent(
        name="ninja_setup_assistant",
        model=model,
        description="Ninja Stack project setup wizard",
        instruction=SETUP_ASSISTANT_PROMPT,
        tools=tools,
    )


def has_api_key() -> bool:
    """Return ``True`` if a Gemini API key is available."""
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY"))


# ---------------------------------------------------------------------------
# High-level wrapper for programmatic use
# ---------------------------------------------------------------------------


class SetupAssistant:
    """Convenience wrapper around the ADK agent + runner.

    Provides a simple ``chat()`` interface for programmatic use and testing.
    When no API key is available the assistant runs in stub mode.
    """

    def __init__(
        self,
        project_name: str = "my-ninja-project",
        *,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self.workspace = SchemaWorkspace(schema=AgenticSchema(project_name=project_name))
        self.model = model
        self.agent = create_setup_agent(self.workspace, model=model)
        self._stub_mode = not has_api_key()

    @property
    def is_stub(self) -> bool:
        return self._stub_mode

    async def chat(self, user_message: str) -> str:
        """Send a user message and return the assistant's text response.

        In stub mode (no API key) returns a canned message.  With a real key
        the message is routed through the ADK ``Runner``.
        """
        if self._stub_mode:
            return (
                "I'm running in stub mode (no LLM configured). "
                "You can still use the tools directly via the CLI. "
                "Set GOOGLE_API_KEY to enable the conversational assistant."
            )

        # Use the ADK runner for a real conversation turn.
        return await self._run_turn(user_message)

    async def _run_turn(self, user_message: str) -> str:
        """Execute a single conversation turn via the ADK runner."""
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai.types import Content, Part

        session_service = InMemorySessionService()
        runner = Runner(
            agent=self.agent,
            app_name=APP_NAME,
            session_service=session_service,
        )

        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id="setup_user",
        )

        content = Content(role="user", parts=[Part(text=user_message)])
        collected: list[str] = []
        async for event in runner.run_async(
            user_id="setup_user",
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        collected.append(part.text)

        return "\n".join(collected) if collected else "(No response from agent)"

    def get_tool_functions(self) -> dict[str, Any]:
        """Return a mapping of tool names for inspection/testing."""
        return {fn.__name__: fn for fn in create_adk_tools(self.workspace)}
