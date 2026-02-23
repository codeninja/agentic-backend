"""Base agent classes — DataAgent, DomainAgent, CoordinatorAgent.

DataAgent extends ADK ``BaseAgent`` for deterministic CRUD (no LLM).
DomainAgent and CoordinatorAgent wrap ADK ``LlmAgent`` with scoped
sub-agents and tools, preserving the Ninja Stack delegation hierarchy.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Any, Callable

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema
from pydantic import model_validator

from ninja_agents.safety import (
    AgentSafetyError,
    InvalidToolAccess,
    safe_error_message,
    validate_request_size,
    validate_tool_kwargs_size,
    validate_tool_name,
)
from ninja_agents.tools import generate_crud_tools, invoke_tool
from ninja_agents.tracing import TraceContext

# Pattern for valid agent-facing names: starts with a letter, then letters/digits/underscores/hyphens/spaces.
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_ -]*$")


def sanitize_agent_name(name: str) -> str:
    """Sanitize a domain or entity name before interpolation into LLM prompts.

    Validates that the name contains no control characters and matches
    the safe name pattern.  Raises ``ValueError`` if the name is empty,
    contains control characters (newlines, tabs, null bytes, etc.), or
    contains disallowed characters.
    """
    if not name or not name.strip():
        raise ValueError(f"Name is empty after sanitization: {name!r}")
    # Reject any control characters (prevents prompt injection via newlines etc.)
    if re.search(r"[\x00-\x1f\x7f-\x9f]", name):
        raise ValueError(
            f"Name contains disallowed characters (control characters): {name!r}"
        )
    cleaned = name.strip()
    if not _SAFE_NAME_RE.match(cleaned):
        raise ValueError(
            f"Name contains disallowed characters: {cleaned!r}. "
            f"Must match {_SAFE_NAME_RE.pattern}"
        )
    return cleaned

# Default model for LLM-powered agents (Gemini via ADK).
_DEFAULT_MODEL = "gemini-2.5-pro"

# Map reasoning levels to model identifiers.
_REASONING_MODEL: dict[ReasoningLevel, str] = {
    ReasoningLevel.NONE: "",
    ReasoningLevel.LOW: "gemini-2.0-flash",
    ReasoningLevel.MEDIUM: "gemini-2.5-flash",
    ReasoningLevel.HIGH: _DEFAULT_MODEL,
}


class DataAgent(BaseAgent):
    """Deterministic agent that owns a single entity.

    Extends ADK ``BaseAgent`` — performs CRUD operations via its scoped
    tool set without LLM calls (unless reasoning_level is explicitly raised).
    """

    entity: EntitySchema
    config: AgentConfig = AgentConfig(reasoning_level=ReasoningLevel.NONE)
    tools: list[Callable[..., Any]] = []  # type: ignore[assignment]

    @model_validator(mode="before")
    @classmethod
    def _derive_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            entity = data.get("entity")
            if isinstance(entity, EntitySchema):
                safe_name = sanitize_agent_name(entity.name)
                data.setdefault("name", f"data_agent_{safe_name.lower()}")
                data.setdefault(
                    "description",
                    f"Data agent for {safe_name} — deterministic CRUD",
                )
        return data

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        if not self.tools:
            self.tools = generate_crud_tools(self.entity)
        # Build internal lookup by function __name__.
        self._tool_map: dict[str, Callable[..., Any]] = {t.__name__: t for t in self.tools}

    @property
    def uses_llm(self) -> bool:
        return self.config.reasoning_level != ReasoningLevel.NONE

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_map.keys())

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        return self._tool_map.get(name)

    def execute(
        self,
        tool_name: str,
        trace: TraceContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute a tool by name.

        Validates the tool name format before lookup and enforces size limits
        on keyword arguments.

        Raises:
            InvalidToolAccess: If the tool name is malformed or denied
                by ``tool_permissions``.
            AgentInputTooLarge: If kwargs exceed size limits.
            KeyError: If the tool is not in this agent's scope.
        """
        validate_tool_name(tool_name)
        if self.config.tool_permissions and tool_name not in self.config.tool_permissions:
            raise InvalidToolAccess(
                f"Tool '{tool_name}' is not permitted for agent '{self.name}'."
            )
        validate_tool_kwargs_size(kwargs)
        tool = self._tool_map.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not in scope for agent '{self.name}'.")
        span = trace.start_span(self.name) if trace else None
        try:
            return invoke_tool(tool, span=span, **kwargs)
        finally:
            if span:
                trace.finish_span(span.span_id)

    # -- ADK BaseAgent contract ------------------------------------------

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Deterministic execution: read the requested tool + args from
        session state, run the tool, and yield a single result event."""
        tool_name: str = ctx.session.state.get("tool_name", "")
        tool_kwargs: dict[str, Any] = ctx.session.state.get("tool_kwargs", {})

        try:
            validate_tool_name(tool_name)
        except (InvalidToolAccess, AgentSafetyError):
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content="Invalid tool name.",
            )
            return

        # Enforce tool_permissions if configured
        if self.config.tool_permissions and tool_name not in self.config.tool_permissions:
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=InvalidToolAccess.client_message,
            )
            return

        tool = self._tool_map.get(tool_name)
        if tool is None:
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content="Requested tool is not available.",
            )
            return

        try:
            validate_tool_kwargs_size(tool_kwargs)
            result = tool(**tool_kwargs)
        except Exception as exc:
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=safe_error_message(exc),
            )
            return

        ctx.session.state["result"] = result
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=str(result),
        )


class DomainAgent:
    """LLM-powered agent that owns a domain (group of entities).

    Wraps an ADK ``LlmAgent`` whose ``sub_agents`` are the domain's
    ``DataAgent`` instances.  Provides convenience methods for synchronous
    delegation and execution that work without an LLM call (useful for
    testing and deterministic paths).
    """

    def __init__(
        self,
        domain: DomainSchema,
        data_agents: list[DataAgent],
        config: AgentConfig | None = None,
    ) -> None:
        self.domain = domain
        self.config = config or domain.agent_config
        safe_domain = sanitize_agent_name(domain.name)
        self.name = f"domain_agent_{safe_domain.lower()}"
        self._data_agents: dict[str, DataAgent] = {da.entity.name: da for da in data_agents}

        model = _REASONING_MODEL.get(self.config.reasoning_level, _DEFAULT_MODEL)
        self.agent = LlmAgent(
            name=self.name,
            model=model,
            description=f"Domain agent for {safe_domain}",
            instruction=(
                f"You are the {safe_domain} domain agent. "
                "Delegate CRUD operations to your DataAgent sub-agents."
            ),
            tools=[],
            sub_agents=list(data_agents),
        )

    @property
    def uses_llm(self) -> bool:
        return self.config.reasoning_level != ReasoningLevel.NONE

    @property
    def entity_names(self) -> list[str]:
        return list(self._data_agents.keys())

    def get_data_agent(self, entity_name: str) -> DataAgent | None:
        return self._data_agents.get(entity_name)

    def delegate(
        self,
        entity_name: str,
        tool_name: str,
        trace: TraceContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Delegate a tool call to a DataAgent.

        Validates the entity name and tool name before delegation.

        Raises:
            KeyError: If the entity is not in this domain.
            InvalidToolAccess: If the tool name is malformed.
        """
        da = self._data_agents.get(entity_name)
        if da is None:
            raise KeyError(f"Entity '{entity_name}' not in domain '{self.domain.name}'.")
        validate_tool_name(tool_name)
        span = trace.start_span(self.name) if trace else None
        try:
            return da.execute(tool_name, trace=trace, **kwargs)
        finally:
            if span:
                trace.finish_span(span.span_id)

    def execute(self, request: str, trace: TraceContext | None = None) -> dict[str, Any]:
        """Process a domain-level request (stub — full impl uses LLM).

        Validates request size before processing.

        Raises:
            AgentInputTooLarge: If the request exceeds the size limit.
        """
        validate_request_size(request)
        span = trace.start_span(self.name) if trace else None
        try:
            return {
                "agent": self.name,
                "domain": self.domain.name,
                "request": request,
                "available_entities": self.entity_names,
                "uses_llm": self.uses_llm,
            }
        finally:
            if span:
                trace.finish_span(span.span_id)


class CoordinatorAgent:
    """Top-level routing agent that delegates to DomainAgents.

    Wraps an ADK ``LlmAgent`` whose ``sub_agents`` are the underlying
    ``DomainAgent.agent`` instances.  Uses LLM for intent classification
    and result synthesis.
    """

    def __init__(
        self,
        domain_agents: list[DomainAgent],
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig(reasoning_level=ReasoningLevel.HIGH)
        self.name = "coordinator"
        self._domain_agents: dict[str, DomainAgent] = {da.domain.name: da for da in domain_agents}

        model = _REASONING_MODEL.get(self.config.reasoning_level, _DEFAULT_MODEL)
        self.agent = LlmAgent(
            name=self.name,
            model=model,
            description="Coordinator that routes requests across domains",
            instruction=(
                "You are the top-level coordinator. Classify the user's intent "
                "and delegate to the appropriate domain agent."
            ),
            tools=[],
            sub_agents=[da.agent for da in domain_agents],
        )

    @property
    def domain_names(self) -> list[str]:
        return list(self._domain_agents.keys())

    def get_domain_agent(self, domain_name: str) -> DomainAgent | None:
        return self._domain_agents.get(domain_name)

    def route(
        self,
        request: str,
        target_domains: list[str],
        trace: TraceContext | None = None,
    ) -> dict[str, Any]:
        """Route a request to specific domains and collect results.

        Validates request size before routing. For parallel execution use
        ``Orchestrator.fan_out()`` instead.

        Raises:
            AgentInputTooLarge: If the request exceeds the size limit.
        """
        validate_request_size(request)
        results: dict[str, Any] = {}
        for domain_name in target_domains:
            da = self._domain_agents.get(domain_name)
            if da is None:
                results[domain_name] = {"error": "Unknown domain."}
                continue
            results[domain_name] = da.execute(request, trace=trace)
        return results


# -- Factory functions (pure ADK) -----------------------------------------------


def create_domain_agent(
    domain: DomainSchema,
    data_agents: list[DataAgent],
) -> LlmAgent:
    """Factory: create a bare ADK LlmAgent for a domain.

    Sanitizes the domain name before interpolation into the LLM instruction.

    Raises:
        ValueError: If the domain name fails sanitization.
    """
    safe_domain = sanitize_agent_name(domain.name)
    model = _REASONING_MODEL.get(domain.agent_config.reasoning_level, _DEFAULT_MODEL)
    return LlmAgent(
        name=f"domain_agent_{safe_domain.lower()}",
        model=model,
        description=f"Domain agent for {safe_domain} — cross-entity reasoning",
        instruction=(
            f"You are the {safe_domain} domain agent. "
            "Delegate CRUD operations to your DataAgent sub-agents."
        ),
        tools=[],
        sub_agents=list(data_agents),
    )


def create_coordinator_agent(
    domain_agents: list[DomainAgent],
) -> LlmAgent:
    """Factory: create a bare ADK LlmAgent coordinator."""
    return LlmAgent(
        name="coordinator",
        model=_DEFAULT_MODEL,
        description="Coordinator that routes requests across domains",
        instruction=("Classify the user's intent and delegate to the appropriate domain agent."),
        tools=[],
        sub_agents=[da.agent for da in domain_agents],
    )
