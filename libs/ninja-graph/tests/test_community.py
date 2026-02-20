"""Tests for community detection."""

from __future__ import annotations

from ninja_graph.community import detect_communities, get_community_members, get_community_summary
from ninja_graph.memory_backend import InMemoryGraphBackend


async def test_detect_communities_empty(backend: InMemoryGraphBackend):
    result = await detect_communities(backend)
    assert result == {}


async def test_detect_communities_isolated_nodes(backend: InMemoryGraphBackend):
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})

    result = await detect_communities(backend)
    # Isolated nodes stay in their own community
    assert result["a"] != result["b"]


async def test_detect_communities_connected_cluster(backend: InMemoryGraphBackend):
    # Create a tightly connected cluster
    await backend.create_node("A", "a", {})
    await backend.create_node("B", "b", {})
    await backend.create_node("C", "c", {})
    await backend.create_edge("a", "b", "LINK")
    await backend.create_edge("b", "c", "LINK")
    await backend.create_edge("a", "c", "LINK")

    result = await detect_communities(backend)
    # All in the same community
    assert result["a"] == result["b"] == result["c"]


async def test_detect_communities_two_clusters(backend: InMemoryGraphBackend):
    # Cluster 1: a-b-c
    await backend.create_node("X", "a", {})
    await backend.create_node("X", "b", {})
    await backend.create_node("X", "c", {})
    await backend.create_edge("a", "b", "LINK")
    await backend.create_edge("b", "c", "LINK")
    await backend.create_edge("a", "c", "LINK")

    # Cluster 2: d-e-f
    await backend.create_node("Y", "d", {})
    await backend.create_node("Y", "e", {})
    await backend.create_node("Y", "f", {})
    await backend.create_edge("d", "e", "LINK")
    await backend.create_edge("e", "f", "LINK")
    await backend.create_edge("d", "f", "LINK")

    result = await detect_communities(backend)
    # Within-cluster nodes share community
    assert result["a"] == result["b"] == result["c"]
    assert result["d"] == result["e"] == result["f"]
    # Cross-cluster nodes differ
    assert result["a"] != result["d"]


async def test_get_community_members(backend: InMemoryGraphBackend):
    await backend.create_node("X", "a", {"name": "A"})
    await backend.create_node("X", "b", {"name": "B"})
    await backend.create_node("Y", "c", {"name": "C"})
    await backend.create_edge("a", "b", "LINK")

    members = await get_community_members(backend, "a")
    member_ids = {m["id"] for m in members}

    assert "a" in member_ids
    assert "b" in member_ids


async def test_get_community_members_unknown_entity(backend: InMemoryGraphBackend):
    members = await get_community_members(backend, "nonexistent")
    assert members == []


async def test_get_community_summary(backend: InMemoryGraphBackend):
    await backend.create_node("X", "a", {})
    await backend.create_node("X", "b", {})
    await backend.create_node("Y", "c", {})
    await backend.create_edge("a", "b", "LINK")

    summary = await get_community_summary(backend)

    # Should have at least 2 communities (a+b together, c alone)
    total_members = sum(len(members) for members in summary.values())
    assert total_members == 3
