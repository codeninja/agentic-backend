"""ASD loading, repository wiring, and agent routing setup.

Provides helper factories used by the app factory to wire ninja-core,
ninja-persistence, ninja-agents, and ninja-gql together at startup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ninja_agents.base import CoordinatorAgent, DataAgent, DomainAgent
from ninja_agents.orchestrator import Orchestrator
from ninja_core.schema.project import AgenticSchema
from ninja_core.serialization.io import load_schema
from ninja_persistence.connections import ConnectionManager
from ninja_persistence.protocols import Repository
from ninja_persistence.registry import AdapterRegistry


def load_asd(path: Path) -> AgenticSchema:
    """Load an Agentic Schema Definition from disk.

    Delegates to ``ninja_core.serialization.io.load_schema``.

    Args:
        path: Path to the ASD JSON file.

    Returns:
        The parsed ``AgenticSchema`` instance.
    """
    return load_schema(path)


def make_repo_getter(
    asd: AgenticSchema,
    connections_path: Path | None = None,
) -> Callable[[str], Repository[Any]]:
    """Build a repo-getter callback from ASD entities and connection config.

    Creates an ``AdapterRegistry`` backed by a ``ConnectionManager`` loaded
    from the connections file, then returns a callable that maps entity names
    to ``Repository`` instances.

    Args:
        asd: The project's Agentic Schema Definition.
        connections_path: Path to ``connections.json``.  Defaults to
            ``.ninjastack/connections.json``.

    Returns:
        A callable ``(entity_name: str) -> Repository``.
    """
    conn_path = connections_path or Path(".ninjastack/connections.json")
    conn_manager = ConnectionManager.from_file(conn_path)
    registry = AdapterRegistry(conn_manager)

    # Build a lookup from entity name → EntitySchema for fast resolution.
    entity_map = {entity.name: entity for entity in asd.entities}

    def _get_repo(entity_name: str) -> Repository[Any]:
        entity = entity_map.get(entity_name)
        if entity is None:
            raise KeyError(f"Entity '{entity_name}' not found in ASD. Available: {list(entity_map.keys())}")
        return registry.get_repository(entity)

    return _get_repo


class AgentRouterAdapter:
    """Adapter that satisfies the ``AgentRouter`` protocol from ninja-gql.

    Wraps an ``Orchestrator`` instance so that ``ask(query, domain=...)``
    delegates to ``Orchestrator.fan_out()``.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def ask(self, query: str, *, domain: str | None = None) -> dict[str, Any]:
        """Route a natural-language query through the orchestrator.

        Args:
            query: The user's question or command.
            domain: Optional domain name to target.  When ``None``, the
                orchestrator fans out to all domains.

        Returns:
            Dict of domain-name → result mappings from the orchestrator.
        """
        target_domains = [domain] if domain else None
        return await self._orchestrator.fan_out(
            request=query,
            target_domains=target_domains,
        )


def make_orchestrator(asd: AgenticSchema) -> Orchestrator:
    """Build a fully wired ``Orchestrator`` from the ASD.

    Constructs the DataAgent → DomainAgent → CoordinatorAgent → Orchestrator
    hierarchy from the ASD's domain and entity definitions.

    Args:
        asd: The project's Agentic Schema Definition.

    Returns:
        A configured ``Orchestrator`` ready for fan-out execution.
    """
    entity_map = {entity.name: entity for entity in asd.entities}
    domain_agents: list[DomainAgent] = []

    for domain in asd.domains:
        data_agents: list[DataAgent] = []
        for entity_name in domain.entities:
            entity = entity_map.get(entity_name)
            if entity is not None:
                data_agents.append(DataAgent(entity=entity))
        domain_agents.append(DomainAgent(domain=domain, data_agents=data_agents))

    coordinator = CoordinatorAgent(domain_agents=domain_agents)
    return Orchestrator(coordinator=coordinator)


def make_agent_router(asd: AgenticSchema) -> AgentRouterAdapter:
    """Build an ``AgentRouterAdapter`` from the ASD.

    Convenience wrapper that creates the full orchestrator stack and wraps
    it in the adapter expected by ``ninja_gql.build_schema()``.

    Args:
        asd: The project's Agentic Schema Definition.

    Returns:
        An ``AgentRouterAdapter`` implementing the ``AgentRouter`` protocol.
    """
    orchestrator = make_orchestrator(asd)
    return AgentRouterAdapter(orchestrator)
