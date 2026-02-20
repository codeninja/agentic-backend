"""Main ADK agent definition for the Ninja Setup Assistant.

Uses Google Gemini as the model. When the ``google-genai`` package is not
installed (or no API key is configured), falls back to a stub interface so
that the tool layer remains fully testable without LLM calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

from ninja_setup_assistant.prompts import SYSTEM_PROMPT
from ninja_setup_assistant.tools import (
    SchemaWorkspace,
    add_entity,
    add_relationship,
    confirm_schema,
    create_domain,
    introspect_database,
    review_schema,
)

# ---------------------------------------------------------------------------
# Thin abstraction over LLM providers — allows real ADK or a stub
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Minimal interface for an LLM chat provider."""

    async def send_message(self, message: str) -> "AgentResponse": ...


@dataclass
class AgentResponse:
    """Response from the agent containing text and/or tool calls."""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False


# ---------------------------------------------------------------------------
# Tool dispatcher — routes tool-call names to implementations
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict[str, Any] = {
    "add_entity": add_entity,
    "add_relationship": add_relationship,
    "create_domain": create_domain,
    "review_schema": review_schema,
    "confirm_schema": confirm_schema,
    "introspect_database": introspect_database,
}


async def dispatch_tool_call(
    workspace: SchemaWorkspace,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Execute a tool by name with the given arguments.

    Returns:
        The tool's string result.

    Raises:
        ValueError: If the tool name is unknown.
    """
    func = _TOOL_REGISTRY.get(tool_name)
    if func is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    # Inject workspace as the first argument
    if asyncio.iscoroutinefunction(func):
        return await func(workspace, **arguments)
    return func(workspace, **arguments)


# ---------------------------------------------------------------------------
# Gemini ADK provider (optional — requires google-genai)
# ---------------------------------------------------------------------------


def _try_create_gemini_provider(system_prompt: str) -> LLMProvider | None:
    """Attempt to create a Gemini-backed provider.

    Returns ``None`` if the SDK is not installed or no API key is set.
    """
    try:
        from google import genai  # noqa: F401  # type: ignore[import-untyped]
        from google.genai import types  # noqa: F401  # type: ignore[import-untyped]
    except ImportError:
        return None

    import os

    if not os.environ.get("GOOGLE_API_KEY"):
        return None

    return _GeminiProvider(system_prompt=system_prompt)


class _GeminiProvider:
    """Wraps the google-genai SDK for conversational tool-use."""

    def __init__(self, system_prompt: str) -> None:
        from google import genai  # type: ignore[import-untyped]
        from google.genai import types  # type: ignore[import-untyped]

        self._client = genai.Client()
        self._model = "gemini-2.0-flash"
        self._system_prompt = system_prompt
        self._history: list[types.Content] = []

    async def send_message(self, message: str) -> AgentResponse:
        from google.genai import types  # type: ignore[import-untyped]

        self._history.append(types.Content(role="user", parts=[types.Part(text=message)]))

        from ninja_setup_assistant.tools import TOOL_DECLARATIONS

        tools = [types.FunctionDeclaration(**decl) for decl in TOOL_DECLARATIONS]

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self._model,
            contents=self._history,
            config=types.GenerateContentConfig(
                system_instruction=self._system_prompt,
                tools=[types.Tool(function_declarations=tools)],
                temperature=0.7,
            ),
        )

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append({"name": fc.name, "arguments": dict(fc.args)})
                elif hasattr(part, "text") and part.text:
                    text_parts.append(part.text)

        self._history.append(response.candidates[0].content)

        return AgentResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
        )


# ---------------------------------------------------------------------------
# Stub provider — for environments without an LLM
# ---------------------------------------------------------------------------


class StubProvider:
    """A no-op LLM provider for testing and environments without API keys.

    Returns a canned response prompting the user to configure an LLM.
    """

    async def send_message(self, message: str) -> AgentResponse:
        return AgentResponse(
            text=(
                "I'm running in stub mode (no LLM configured). "
                "You can still use the tools directly via the CLI. "
                "Set GOOGLE_API_KEY to enable the conversational assistant."
            ),
        )


# ---------------------------------------------------------------------------
# SetupAssistant — the main agent class
# ---------------------------------------------------------------------------


class SetupAssistant:
    """Conversational setup assistant that drives ``ninjastack init``.

    Wraps an LLM provider and a tool workspace. Each user message is sent
    to the LLM; any tool calls in the response are executed automatically
    and their results fed back to the LLM for a follow-up response.
    """

    def __init__(
        self,
        project_name: str = "my-ninja-project",
        provider: LLMProvider | None = None,
    ) -> None:
        from ninja_core.schema.project import AgenticSchema

        self.workspace = SchemaWorkspace(schema=AgenticSchema(project_name=project_name))

        if provider is not None:
            self.provider = provider
        else:
            gemini = _try_create_gemini_provider(SYSTEM_PROMPT)
            self.provider = gemini if gemini is not None else StubProvider()

    async def chat(self, user_message: str) -> str:
        """Send a user message and return the assistant's text response.

        Tool calls are executed automatically. If the LLM returns tool calls,
        their results are fed back for a follow-up response (up to 5 rounds
        to prevent infinite loops).
        """
        response = await self.provider.send_message(user_message)
        collected_text: list[str] = []

        max_rounds = 5
        for _ in range(max_rounds):
            if response.text:
                collected_text.append(response.text)

            if not response.tool_calls:
                break

            # Execute all tool calls and collect results
            tool_results: list[str] = []
            for tc in response.tool_calls:
                result = await dispatch_tool_call(self.workspace, tc["name"], tc["arguments"])
                tool_results.append(f"[{tc['name']}]: {result}")

            # Feed tool results back to the LLM
            tool_feedback = "\n".join(tool_results)
            response = await self.provider.send_message(f"Tool results:\n{tool_feedback}")
        else:
            collected_text.append("(Reached maximum tool-call rounds)")

        return "\n".join(collected_text)
