"""Base agent classes — DataAgent, DomainAgent, CoordinatorAgent.

DataAgent extends ADK ``BaseAgent`` for deterministic CRUD (no LLM).
DomainAgent and CoordinatorAgent wrap ADK ``LlmAgent`` with scoped
sub-agents and tools, preserving the Ninja Stack delegation hierarchy.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Callable

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema
from pydantic import model_validator

from ninja_agents.tools import generate_crud_tools, invoke_tool
from ninja_agents.tracing import TraceContext

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
                data.setdefault("name", f"data_agent_{entity.name.lower()}")
                data.setdefault(
                    "description",
                    f"Data agent for {entity.name} — deterministic CRUD",
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
        """Execute a tool by name.  Raises ``KeyError`` if not in scope."""
        tool = self._tool_map.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not in scope for agent '{self.name}'. Available: {self.tool_names}")
        span = trace.start_span(self.name) if trace else None
        try:
            return invoke_tool(tool, span=span, **kwargs)
        finally:
            if trace:
                trace.finish_span(self.name)

    # -- ADK BaseAgent contract ------------------------------------------

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Deterministic execution: read the requested tool + args from
        session state, run the tool, and yield a single result event."""
        tool_name: str = ctx.session.state.get("tool_name", "")
        tool_kwargs: dict[str, Any] = ctx.session.state.get("tool_kwargs", {})

        tool = self._tool_map.get(tool_name)
        if tool is None:
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=f"Unknown tool: {tool_name}",
            )
            return

        result = tool(**tool_kwargs)
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
        self.name = f"domain_agent_{domain.name.lower()}"
        self._data_agents: dict[str, DataAgent] = {da.entity.name: da for da in data_agents}

        model = _REASONING_MODEL.get(self.config.reasoning_level, _DEFAULT_MODEL)
        self.agent = LlmAgent(
            name=self.name,
            model=model,
            description=f"Domain agent for {domain.name}",
            instruction=(
                f"You are the {domain.name} domain agent. Delegate CRUD operations to your DataAgent sub-agents."
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
        """Delegate a tool call to a DataAgent.  Raises ``KeyError`` if
        the entity is not in this domain."""
        da = self._data_agents.get(entity_name)
        if da is None:
            raise KeyError(f"Entity '{entity_name}' not in domain '{self.domain.name}'. Available: {self.entity_names}")
        if trace:
            trace.start_span(self.name)
        try:
            return da.execute(tool_name, trace=trace, **kwargs)
        finally:
            if trace:
                trace.finish_span(self.name)

    def execute(self, request: str, trace: TraceContext | None = None) -> dict[str, Any]:
        """Process a domain-level request (stub — full impl uses LLM)."""
        if trace:
            trace.start_span(self.name)
        try:
            return {
                "agent": self.name,
                "domain": self.domain.name,
                "request": request,
                "available_entities": self.entity_names,
                "uses_llm": self.uses_llm,
            }
        finally:
            if trace:
                trace.finish_span(self.name)


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

        For parallel execution use ``Orchestrator.fan_out()`` instead.
        """
        results: dict[str, Any] = {}
        for domain_name in target_domains:
            da = self._domain_agents.get(domain_name)
            if da is None:
                results[domain_name] = {"error": f"Unknown domain: {domain_name}"}
                continue
            results[domain_name] = da.execute(request, trace=trace)
        return results


# -- Factory functions (pure ADK) -----------------------------------------------


def create_domain_agent(
    domain: DomainSchema,
    data_agents: list[DataAgent],
) -> LlmAgent:
    """Factory: create a bare ADK LlmAgent for a domain."""
    model = _REASONING_MODEL.get(domain.agent_config.reasoning_level, _DEFAULT_MODEL)
    return LlmAgent(
        name=f"domain_agent_{domain.name.lower()}",
        model=model,
        description=f"Domain agent for {domain.name} — cross-entity reasoning",
        instruction=(f"You are the {domain.name} domain agent. Delegate CRUD operations to your DataAgent sub-agents."),
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
