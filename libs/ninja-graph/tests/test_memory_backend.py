"""Tests for the in-memory graph backend."""

from __future__ import annotations

from ninja_graph.memory_backend import InMemoryGraphBackend
from ninja_graph.protocols import GraphBackend


def test_implements_protocol():
    assert isinstance(InMemoryGraphBackend(), GraphBackend)


async def test_create_and_get_node(backend: InMemoryGraphBackend):
    await backend.create_node("User", "u1", {"name": "Alice"})
    node = await backend.get_node("u1")

    assert node is not None
    assert node["id"] == "u1"
    assert node["label"] == "User"
    assert node["name"] == "Alice"


async def test_get_nonexistent_node(backend: InMemoryGraphBackend):
    assert await backend.get_node("missing") is None


async def test_create_edge_and_get_neighbors(backend: InMemoryGraphBackend):
    await backend.create_node("User", "u1", {"name": "Alice"})
    await backend.create_node("Post", "p1", {"title": "Hello"})
    await backend.create_edge("u1", "p1", "AUTHORED")

    neighbors = await backend.get_neighbors("u1")
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == "p1"


async def test_get_neighbors_with_edge_type_filter(backend: InMemoryGraphBackend):
    await backend.create_node("User", "u1", {"name": "Alice"})
    await backend.create_node("Post", "p1", {"title": "Hello"})
    await backend.create_node("User", "u2", {"name": "Bob"})
    await backend.create_edge("u1", "p1", "AUTHORED")
    await backend.create_edge("u1", "u2", "FOLLOWS")

    authored = await backend.get_neighbors("u1", edge_type="AUTHORED")
    assert len(authored) == 1
    assert authored[0]["id"] == "p1"

    follows = await backend.get_neighbors("u1", edge_type="FOLLOWS")
    assert len(follows) == 1
    assert follows[0]["id"] == "u2"


async def test_get_neighbors_multi_hop(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    await backend.create_node("C", "c", {})
    await backend.create_edge("a", "b", "LINK")
    await backend.create_edge("b", "c", "LINK")

    # Depth 1: only b
    depth1 = await backend.get_neighbors("a", depth=1)
    assert len(depth1) == 1
    assert depth1[0]["id"] == "b"

    # Depth 2: b and c
    depth2 = await backend.get_neighbors("a", depth=2)
    ids = {n["id"] for n in depth2}
    assert ids == {"b", "c"}


async def test_find_path_direct(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    await backend.create_edge("a", "b", "LINK")

    path = await backend.find_path("a", "b")
    assert path == ["a", "b"]


async def test_find_path_multi_hop(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    await backend.create_node("C", "c", {})
    await backend.create_edge("a", "b", "LINK")
    await backend.create_edge("b", "c", "LINK")

    path = await backend.find_path("a", "c")
    assert path == ["a", "b", "c"]


async def test_find_path_no_path(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    # No edge

    path = await backend.find_path("a", "b")
    assert path is None


async def test_find_path_same_node(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    path = await backend.find_path("a", "a")
    assert path == ["a"]


async def test_find_path_nonexistent_node(backend: InMemoryGraphBackend):
    assert await backend.find_path("x", "y") is None


async def test_get_all_nodes(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})

    nodes = await backend.get_all_nodes()
    assert len(nodes) == 2


async def test_get_all_edges(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    await backend.create_edge("a", "b", "LINK")

    edges = await backend.get_all_edges()
    assert len(edges) == 1
    assert edges[0]["source"] in ("a", "b")
    assert edges[0]["type"] == "LINK"


async def test_get_all_edges_no_duplicates(backend: InMemoryGraphBackend):
    """Bidirectional storage shouldn't produce duplicate edges."""
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    await backend.create_edge("a", "b", "LINK")

    edges = await backend.get_all_edges()
    assert len(edges) == 1


async def test_clear(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_edge("a", "a", "SELF")
    await backend.clear()

    assert await backend.get_all_nodes() == []
    assert await backend.get_all_edges() == []
