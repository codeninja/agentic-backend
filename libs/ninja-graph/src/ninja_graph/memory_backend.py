"""In-memory graph backend for testing — dict-based adjacency list."""

from __future__ import annotations

from collections import deque
from typing import Any


class InMemoryGraphBackend:
    """Dict-based adjacency list that mirrors the GraphBackend protocol."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        # edges stored as: source_id -> list of (target_id, edge_type, properties)
        self._edges: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}

    async def create_node(self, label: str, node_id: str, properties: dict[str, Any]) -> None:
        self._nodes[node_id] = {"id": node_id, "label": label, **properties}

    async def create_edge(
        self, source_id: str, target_id: str, edge_type: str, properties: dict[str, Any] | None = None
    ) -> None:
        self._edges.setdefault(source_id, []).append((target_id, edge_type, properties or {}))
        # Bidirectional for traversal
        self._edges.setdefault(target_id, []).append((source_id, edge_type, properties or {}))

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    async def get_neighbors(self, node_id: str, edge_type: str | None = None, depth: int = 1) -> list[dict[str, Any]]:
        visited: set[str] = {node_id}
        current_layer: set[str] = {node_id}
        results: list[dict[str, Any]] = []

        for _ in range(depth):
            next_layer: set[str] = set()
            for nid in current_layer:
                for target_id, etype, _ in self._edges.get(nid, []):
                    if target_id not in visited and (edge_type is None or etype == edge_type):
                        visited.add(target_id)
                        next_layer.add(target_id)
                        node = self._nodes.get(target_id)
                        if node:
                            results.append(node)
            current_layer = next_layer

        return results

    async def find_path(self, start_id: str, end_id: str, max_depth: int = 5) -> list[str] | None:
        if start_id not in self._nodes or end_id not in self._nodes:
            return None
        if start_id == end_id:
            return [start_id]

        queue: deque[list[str]] = deque([[start_id]])
        visited: set[str] = {start_id}

        while queue:
            path = queue.popleft()
            if len(path) > max_depth + 1:
                return None

            current = path[-1]
            for target_id, _, _ in self._edges.get(current, []):
                if target_id == end_id:
                    return path + [target_id]
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append(path + [target_id])

        return None

    async def get_all_nodes(self) -> list[dict[str, Any]]:
        return list(self._nodes.values())

    async def get_all_edges(self) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        edges: list[dict[str, Any]] = []
        for source_id, edge_list in self._edges.items():
            for target_id, edge_type, props in edge_list:
                key = (min(source_id, target_id), max(source_id, target_id), edge_type)
                if key not in seen:
                    seen.add(key)
                    edges.append(
                        {
                            "source": source_id,
                            "target": target_id,
                            "type": edge_type,
                            **props,
                        }
                    )
        return edges

    async def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
