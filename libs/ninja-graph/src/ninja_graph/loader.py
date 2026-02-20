"""Bulk data import — takes entity data and creates Neo4j nodes/edges.

Uses the GraphBackend protocol so it works with both the in-memory backend
(for testing) and a real Neo4j driver.
"""

from __future__ import annotations

from typing import Any

from ninja_graph.mapper import GraphSchema
from ninja_graph.protocols import GraphBackend


async def load_nodes(
    backend: GraphBackend,
    label: str,
    records: list[dict[str, Any]],
    id_field: str = "id",
) -> int:
    """Bulk-create nodes from a list of records.

    Args:
        backend: Graph backend to write to.
        label: Node label for all records.
        records: List of dicts, each becoming a node.
        id_field: Key in each record used as the node ID.

    Returns:
        Number of nodes created.
    """
    count = 0
    for record in records:
        node_id = str(record.get(id_field, ""))
        if not node_id:
            continue
        await backend.create_node(label=label, node_id=node_id, properties=record)
        count += 1
    return count


async def load_edges(
    backend: GraphBackend,
    records: list[dict[str, Any]],
    source_id_field: str,
    target_id_field: str,
    edge_type: str,
) -> int:
    """Bulk-create edges from a list of records containing source/target pairs.

    Args:
        backend: Graph backend to write to.
        records: Dicts containing at least source and target ID fields.
        source_id_field: Key for the source node ID.
        target_id_field: Key for the target node ID.
        edge_type: Edge type label.

    Returns:
        Number of edges created.
    """
    count = 0
    for record in records:
        source_id = str(record.get(source_id_field, ""))
        target_id = str(record.get(target_id_field, ""))
        if not source_id or not target_id:
            continue
        props = {k: v for k, v in record.items() if k not in (source_id_field, target_id_field)}
        await backend.create_edge(source_id=source_id, target_id=target_id, edge_type=edge_type, properties=props)
        count += 1
    return count


async def load_from_schema(
    backend: GraphBackend,
    schema: GraphSchema,
    entity_data: dict[str, list[dict[str, Any]]],
    relationship_data: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, int]:
    """Load a full graph from an ASD-derived schema and entity data.

    Args:
        backend: Graph backend to write to.
        schema: GraphSchema from map_asd_to_graph_schema().
        entity_data: Mapping of entity name -> list of records.
        relationship_data: Optional mapping of edge type name -> list of
            dicts with 'source' and 'target' keys.

    Returns:
        Dict with counts: {"nodes": N, "edges": M}.
    """
    total_nodes = 0
    for node_label in schema.node_labels:
        records = entity_data.get(node_label.name, [])
        id_field = node_label.primary_key or "id"
        total_nodes += await load_nodes(backend, node_label.name, records, id_field)

    total_edges = 0
    if relationship_data:
        for edge_type in schema.edge_types:
            records = relationship_data.get(edge_type.name, [])
            total_edges += await load_edges(
                backend, records, source_id_field="source", target_id_field="target", edge_type=edge_type.name
            )

    return {"nodes": total_nodes, "edges": total_edges}
