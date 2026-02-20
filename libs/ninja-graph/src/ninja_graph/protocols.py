"""Protocol definitions for graph backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphBackend(Protocol):
    """Abstract interface for a graph database backend.

    Implementations must support async node/edge CRUD and traversal queries.
    The in-memory backend is used for testing; the Neo4j backend for production.
    """

    async def create_node(self, label: str, node_id: str, properties: dict[str, Any]) -> None: ...

    async def create_edge(
        self, source_id: str, target_id: str, edge_type: str, properties: dict[str, Any] | None = None
    ) -> None: ...

    async def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    async def get_neighbors(self, node_id: str, edge_type: str | None = None, depth: int = 1) -> list[dict[str, Any]]:
        """Return neighbor nodes up to the given depth."""
        ...

    async def find_path(self, start_id: str, end_id: str, max_depth: int = 5) -> list[str] | None:
        """Return a list of node IDs forming the shortest path, or None."""
        ...

    async def get_all_nodes(self) -> list[dict[str, Any]]: ...

    async def get_all_edges(self) -> list[dict[str, Any]]: ...

    async def clear(self) -> None: ...
