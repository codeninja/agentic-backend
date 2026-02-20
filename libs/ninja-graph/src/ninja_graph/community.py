"""Community detection algorithms (Louvain-style).

Identifies entity clusters for high-level thematic queries.
Uses a simplified Louvain-inspired algorithm that works on the
in-memory graph backend — no external dependencies required.
"""

from __future__ import annotations

from typing import Any

from ninja_graph.protocols import GraphBackend


async def detect_communities(backend: GraphBackend, max_iterations: int = 10) -> dict[str, int]:
    """Detect communities using a label propagation algorithm.

    Each node starts in its own community. On each iteration, each node adopts
    the community label most common among its neighbors. Iterates until stable
    or max_iterations reached.

    Args:
        backend: Graph backend to read from.
        max_iterations: Maximum number of label propagation rounds.

    Returns:
        Mapping of node_id -> community_id (int).
    """
    nodes = await backend.get_all_nodes()
    edges = await backend.get_all_edges()

    if not nodes:
        return {}

    # Build adjacency from edges
    adjacency: dict[str, list[str]] = {}
    for node in nodes:
        adjacency[node["id"]] = []

    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in adjacency:
            adjacency[src].append(tgt)
        if tgt in adjacency:
            adjacency[tgt].append(src)

    # Initialize: each node is its own community
    node_ids = list(adjacency.keys())
    community: dict[str, int] = {nid: i for i, nid in enumerate(node_ids)}

    for _ in range(max_iterations):
        changed = False
        for nid in node_ids:
            neighbors = adjacency[nid]
            if not neighbors:
                continue

            # Count neighbor community labels
            label_counts: dict[int, int] = {}
            for neighbor in neighbors:
                lbl = community[neighbor]
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

            # Pick the most common label
            best_label = max(label_counts, key=lambda lbl: label_counts[lbl])
            if community[nid] != best_label:
                community[nid] = best_label
                changed = True

        if not changed:
            break

    return community


async def get_community_members(backend: GraphBackend, entity_id: str) -> list[dict[str, Any]]:
    """Get all nodes in the same community as the given entity.

    Args:
        backend: Graph backend to read from.
        entity_id: The entity to find community members for.

    Returns:
        List of node dicts in the same community.
    """
    communities = await detect_communities(backend)
    target_community = communities.get(entity_id)
    if target_community is None:
        return []

    member_ids = [nid for nid, cid in communities.items() if cid == target_community]
    members = []
    for nid in member_ids:
        node = await backend.get_node(nid)
        if node:
            members.append(node)
    return members


async def get_community_summary(backend: GraphBackend) -> dict[int, list[str]]:
    """Get a summary of all communities.

    Returns:
        Mapping of community_id -> list of node IDs.
    """
    communities = await detect_communities(backend)
    summary: dict[int, list[str]] = {}
    for nid, cid in communities.items():
        summary.setdefault(cid, []).append(nid)
    return summary
