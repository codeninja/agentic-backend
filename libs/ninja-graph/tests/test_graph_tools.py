"""Tests for the ADK-compatible agent tools."""

from __future__ import annotations

import pytest
from ninja_graph.memory_backend import InMemoryGraphBackend
from ninja_graph.tools import find_related, get_community, traverse_path


@pytest.fixture
async def populated_backend() -> InMemoryGraphBackend:
    """Backend with a small social graph for tool testing."""
    b = InMemoryGraphBackend()
    await b.create_node("User", "alice", {"name": "Alice"})
    await b.create_node("User", "bob", {"name": "Bob"})
    await b.create_node("User", "charlie", {"name": "Charlie"})
    await b.create_node("Post", "post1", {"title": "Hello World"})
    await b.create_node("Post", "post2", {"title": "Graph RAG"})

    await b.create_edge("alice", "post1", "AUTHORED")
    await b.create_edge("bob", "post2", "AUTHORED")
    await b.create_edge("alice", "bob", "FOLLOWS")
    await b.create_edge("bob", "charlie", "FOLLOWS")
    await b.create_edge("charlie", "post1", "LIKED")
    return b


async def test_find_related_depth_1(populated_backend: InMemoryGraphBackend):
    result = await find_related(populated_backend, "alice", depth=1)
    ids = {r["id"] for r in result}

    assert "post1" in ids
    assert "bob" in ids
    # charlie is 2 hops away, should not appear at depth 1
    assert "charlie" not in ids


async def test_find_related_depth_2(populated_backend: InMemoryGraphBackend):
    result = await find_related(populated_backend, "alice", depth=2)
    ids = {r["id"] for r in result}

    assert "bob" in ids
    assert "post1" in ids
    # charlie and post2 are at depth 2 via alice->bob->charlie and alice->bob->post2
    assert "charlie" in ids
    assert "post2" in ids


async def test_find_related_with_edge_filter(populated_backend: InMemoryGraphBackend):
    result = await find_related(populated_backend, "alice", depth=2, edge_type="FOLLOWS")
    ids = {r["id"] for r in result}

    assert "bob" in ids
    assert "charlie" in ids
    # Posts connected via AUTHORED, not FOLLOWS
    assert "post1" not in ids


async def test_find_related_no_neighbors(populated_backend: InMemoryGraphBackend):
    await populated_backend.create_node("Tag", "orphan", {"name": "lonely"})
    result = await find_related(populated_backend, "orphan", depth=3)
    assert result == []


async def test_traverse_path_direct(populated_backend: InMemoryGraphBackend):
    result = await traverse_path(populated_backend, "alice", "bob")

    assert result["path"] == ["alice", "bob"]
    assert result["length"] == 1


async def test_traverse_path_multi_hop(populated_backend: InMemoryGraphBackend):
    result = await traverse_path(populated_backend, "alice", "charlie")

    assert result["path"] is not None
    assert result["path"][0] == "alice"
    assert result["path"][-1] == "charlie"
    assert result["length"] >= 1


async def test_traverse_path_not_found(populated_backend: InMemoryGraphBackend):
    await populated_backend.create_node("Tag", "orphan", {})
    result = await traverse_path(populated_backend, "alice", "orphan")

    assert result["path"] is None
    assert result["length"] == 0


async def test_get_community(populated_backend: InMemoryGraphBackend):
    result = await get_community(populated_backend, "alice")

    # All nodes are connected, so they should all be in the same community
    ids = {r["id"] for r in result}
    assert "alice" in ids


async def test_get_community_unknown_entity(populated_backend: InMemoryGraphBackend):
    result = await get_community(populated_backend, "nonexistent")
    assert result == []
