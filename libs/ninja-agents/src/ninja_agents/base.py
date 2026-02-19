"""Base agent classes — DataAgent, DomainAgent, CoordinatorAgent.

All follow ADK patterns with scoped tool access and tracing.
"""

from __future__ import annotations

from typing import Any

from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema

from ninja_agents.tools import ToolDefinition, generate_crud_tools, invoke_tool
from ninja_agents.tracing import TraceContext


class DataAgent:
    """Deterministic agent that owns a single entity.

    Performs CRUD operations via its scoped tool set.
    No LLM calls unless reasoning_level is explicitly set above NONE.
    """

    def __init__(
        self,
        entity: EntitySchema,
        config: AgentConfig | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> None:
        self.entity = entity
        self.config = config or AgentConfig(reasoning_level=ReasoningLevel.NONE)
        self.name = f"data_agent_{entity.name.lower()}"
        self._tools = {t.name: t for t in (tools or generate_crud_tools(entity))}

    @property
    def uses_llm(self) -> bool:
        return self.config.reasoning_level != ReasoningLevel.NONE

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def execute(self, tool_name: str, trace: TraceContext | None = None, **kwargs: Any) -> Any:
        """Execute a tool by name. Raises KeyError if tool is not in scope."""
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not in scope for agent '{self.name}'. Available: {self.tool_names}")
        span = trace.start_span(self.name) if trace else None
        try:
            result = invoke_tool(tool, span=span, **kwargs)
            return result
        finally:
            if trace:
                trace.finish_span(self.name)


class DomainAgent:
    """LLM-powered agent that owns a domain (group of entities).

    Delegates to its DataAgents for actual CRUD, uses LLM for
    reasoning over cross-entity queries and ambiguity resolution.
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
        self._data_agents = {da.entity.name: da for da in data_agents}

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
        """Delegate a tool call to a DataAgent. Raises KeyError if entity not in domain."""
        da = self._data_agents.get(entity_name)
        if da is None:
            raise KeyError(f"Entity '{entity_name}' not in domain '{self.domain.name}'. Available: {self.entity_names}")
        if trace:
            trace.start_span(self.name)
        try:
            result = da.execute(tool_name, trace=trace, **kwargs)
            return result
        finally:
            if trace:
                trace.finish_span(self.name)

    def execute(self, request: str, trace: TraceContext | None = None) -> dict[str, Any]:
        """Process a domain-level request.

        In a full implementation, this would use LLM to plan which
        DataAgents to call. Here we return a structured stub.
        """
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

    Uses LLM for intent classification, plan execution,
    and result synthesis across domains.
    """

    def __init__(
        self,
        domain_agents: list[DomainAgent],
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig(reasoning_level=ReasoningLevel.HIGH)
        self.name = "coordinator"
        self._domain_agents = {da.domain.name: da for da in domain_agents}

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

        For parallel execution, use Orchestrator.fan_out() instead.
        """
        results: dict[str, Any] = {}
        for domain_name in target_domains:
            da = self._domain_agents.get(domain_name)
            if da is None:
                results[domain_name] = {"error": f"Unknown domain: {domain_name}"}
                continue
            results[domain_name] = da.execute(request, trace=trace)
        return results
