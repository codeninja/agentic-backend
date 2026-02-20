"""Tests for the vector similarity linker."""

from __future__ import annotations

from ninja_graph.linker import VectorStore, link_similar_entities
from ninja_graph.memory_backend import InMemoryGraphBackend


class MockVectorStore:
    """Mock vector store for testing."""

    def __init__(self, similarities: dict[str, list[tuple[str, float]]]) -> None:
        self._similarities = similarities

    async def query_similar(self, entity_id: str, top_k: int = 10) -> list[tuple[str, float]]:
        return self._similarities.get(entity_id, [])[:top_k]


def test_mock_implements_protocol():
    assert isinstance(MockVectorStore({}), VectorStore)


async def test_link_similar_entities(backend: InMemoryGraphBackend):
    await backend.create_node("Doc", "d1", {"title": "Python Guide"})
    await backend.create_node("Doc", "d2", {"title": "Python Tutorial"})
    await backend.create_node("Doc", "d3", {"title": "Cooking Recipes"})

    store = MockVectorStore(
        {
            "d1": [("d2", 0.95), ("d3", 0.3)],
            "d2": [("d1", 0.95), ("d3", 0.25)],
            "d3": [("d1", 0.3), ("d2", 0.25)],
        }
    )

    count = await link_similar_entities(backend, store, entity_ids=["d1", "d2", "d3"], similarity_threshold=0.8)

    assert count == 1  # Only d1-d2 above threshold
    edges = await backend.get_all_edges()
    assert len(edges) == 1
    assert edges[0]["type"] == "SIMILAR_TO"


async def test_link_no_duplicates(backend: InMemoryGraphBackend):
    """Bidirectional similarities should not create duplicate edges."""
    await backend.create_node("Doc", "d1", {})
    await backend.create_node("Doc", "d2", {})

    store = MockVectorStore(
        {
            "d1": [("d2", 0.9)],
            "d2": [("d1", 0.9)],
        }
    )

    count = await link_similar_entities(backend, store, entity_ids=["d1", "d2"], similarity_threshold=0.5)
    assert count == 1


async def test_link_skips_self(backend: InMemoryGraphBackend):
    await backend.create_node("Doc", "d1", {})

    store = MockVectorStore({"d1": [("d1", 1.0)]})

    count = await link_similar_entities(backend, store, entity_ids=["d1"], similarity_threshold=0.5)
    assert count == 0


async def test_link_custom_edge_type(backend: InMemoryGraphBackend):
    await backend.create_node("Doc", "d1", {})
    await backend.create_node("Doc", "d2", {})

    store = MockVectorStore({"d1": [("d2", 0.9)]})

    count = await link_similar_entities(
        backend, store, entity_ids=["d1"], similarity_threshold=0.5, edge_type="SEMANTIC_MATCH"
    )

    assert count == 1
    edges = await backend.get_all_edges()
    assert edges[0]["type"] == "SEMANTIC_MATCH"


async def test_link_stores_similarity_score(backend: InMemoryGraphBackend):
    await backend.create_node("Doc", "d1", {})
    await backend.create_node("Doc", "d2", {})

    store = MockVectorStore({"d1": [("d2", 0.92)]})

    await link_similar_entities(backend, store, entity_ids=["d1"], similarity_threshold=0.5)

    edges = await backend.get_all_edges()
    assert edges[0]["similarity"] == 0.92


async def test_link_below_threshold(backend: InMemoryGraphBackend):
    await backend.create_node("Doc", "d1", {})
    await backend.create_node("Doc", "d2", {})

    store = MockVectorStore({"d1": [("d2", 0.5)]})

    count = await link_similar_entities(backend, store, entity_ids=["d1"], similarity_threshold=0.8)
    assert count == 0


async def test_link_top_k_limit(backend: InMemoryGraphBackend):
    for i in range(5):
        await backend.create_node("Doc", f"d{i}", {})

    store = MockVectorStore(
        {
            "d0": [("d1", 0.95), ("d2", 0.93), ("d3", 0.91), ("d4", 0.90)],
        }
    )

    count = await link_similar_entities(backend, store, entity_ids=["d0"], similarity_threshold=0.5, top_k=2)
    assert count == 2
