"""Agent-delegated resolvers.

Complex queries that require LLM reasoning are routed to a CoordinatorAgent
(or Domain Agent) instead of hitting the persistence layer directly.
"""

from typing import Any, Callable, Protocol

import strawberry


class AgentRouter(Protocol):
    """Protocol for routing natural-language queries to an agent."""

    async def ask(self, query: str, *, domain: str | None = None) -> dict[str, Any]: ...


def make_agent_query_resolver(
    domain_name: str,
    agent_router: AgentRouter | None = None,
) -> Callable:
    """Return an async resolver: ``ask_{domain}(query) -> JSON``.

    If no *agent_router* is provided the resolver returns an error payload
    indicating that agent routing is not configured.
    """

    async def resolver(query: str) -> strawberry.scalars.JSON:
        if agent_router is None:
            return {"error": "Agent routing not configured", "query": query}
        return await agent_router.ask(query, domain=domain_name)

    resolver.__name__ = f"ask_{domain_name.lower().replace(' ', '_')}"
    return resolver
