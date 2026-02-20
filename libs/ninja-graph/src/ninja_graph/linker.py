"""Vector similarity → soft edges.

Queries vector stores to create edges between semantically related entities
above a configurable similarity threshold.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ninja_graph.protocols import GraphBackend


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for querying a vector store for similar items."""

    async def query_similar(self, entity_id: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return a list of (entity_id, similarity_score) pairs."""
        ...


async def link_similar_entities(
    backend: GraphBackend,
    vector_store: VectorStore,
    entity_ids: list[str],
    similarity_threshold: float = 0.8,
    top_k: int = 10,
    edge_type: str = "SIMILAR_TO",
) -> int:
    """Create soft edges between entities with similarity above threshold.

    Args:
        backend: Graph backend to write edges to.
        vector_store: Vector store to query for similarities.
        entity_ids: List of entity IDs to find similarities for.
        similarity_threshold: Minimum similarity score to create an edge.
        top_k: Maximum number of similar items to retrieve per entity.
        edge_type: Edge label for similarity edges.

    Returns:
        Number of edges created.
    """
    created: set[tuple[str, str]] = set()
    count = 0

    for entity_id in entity_ids:
        similar_items = await vector_store.query_similar(entity_id, top_k=top_k)
        for other_id, score in similar_items:
            if other_id == entity_id:
                continue
            if score < similarity_threshold:
                continue
            # Avoid duplicate edges
            edge_key = (min(entity_id, other_id), max(entity_id, other_id))
            if edge_key in created:
                continue
            created.add(edge_key)
            await backend.create_edge(
                source_id=entity_id,
                target_id=other_id,
                edge_type=edge_type,
                properties={"similarity": score},
            )
            count += 1

    return count
