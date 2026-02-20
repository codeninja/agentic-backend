"""ADK-compatible tool definitions for agents.

Provides graph traversal tools that agents can use to query the knowledge graph:
- find_related: Find entities related to a given entity up to N hops.
- traverse_path: Find the shortest path between two entities.
- get_community: Get all entities in the same community cluster.
"""

from __future__ import annotations

from typing import Any

from ninja_graph.community import get_community_members
from ninja_graph.protocols import GraphBackend


async def find_related(
    backend: GraphBackend,
    entity_id: str,
    depth: int = 2,
    edge_type: str | None = None,
) -> list[dict[str, Any]]:
    """Find entities related to the given entity within the specified depth.

    This is an ADK-compatible tool for agent traversal.

    Args:
        backend: Graph backend to query.
        entity_id: Starting entity ID.
        depth: Maximum number of hops (default: 2).
        edge_type: Optional filter to only follow edges of this type.

    Returns:
        List of related entity dicts.
    """
    return await backend.get_neighbors(entity_id, edge_type=edge_type, depth=depth)


async def traverse_path(
    backend: GraphBackend,
    start: str,
    end: str,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Find the shortest path between two entities.

    Args:
        backend: Graph backend to query.
        start: Starting entity ID.
        end: Ending entity ID.
        max_depth: Maximum path length to search.

    Returns:
        Dict with 'path' (list of node IDs) and 'length', or 'path': None if not found.
    """
    path = await backend.find_path(start, end, max_depth=max_depth)
    if path is None:
        return {"path": None, "length": 0}
    return {"path": path, "length": len(path) - 1}


async def get_community(
    backend: GraphBackend,
    entity_id: str,
) -> list[dict[str, Any]]:
    """Get all entities in the same community as the given entity.

    Args:
        backend: Graph backend to query.
        entity_id: Entity to find community for.

    Returns:
        List of entity dicts in the same community.
    """
    return await get_community_members(backend, entity_id)
