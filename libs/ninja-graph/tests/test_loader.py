"""Tests for the bulk data loader."""

from __future__ import annotations

from ninja_core.schema.project import AgenticSchema
from ninja_graph.loader import load_edges, load_from_schema, load_nodes
from ninja_graph.mapper import map_asd_to_graph_schema
from ninja_graph.memory_backend import InMemoryGraphBackend


async def test_load_nodes(backend: InMemoryGraphBackend):
    records = [
        {"id": "u1", "name": "Alice"},
        {"id": "u2", "name": "Bob"},
    ]
    count = await load_nodes(backend, "User", records)

    assert count == 2
    node = await backend.get_node("u1")
    assert node is not None
    assert node["name"] == "Alice"
    assert node["label"] == "User"


async def test_load_nodes_custom_id_field(backend: InMemoryGraphBackend):
    records = [{"user_id": "u1", "name": "Alice"}]
    count = await load_nodes(backend, "User", records, id_field="user_id")

    assert count == 1
    assert await backend.get_node("u1") is not None


async def test_load_nodes_skips_missing_id(backend: InMemoryGraphBackend):
    records = [{"name": "No ID"}, {"id": "u1", "name": "Has ID"}]
    count = await load_nodes(backend, "User", records)

    assert count == 1


async def test_load_edges(backend: InMemoryGraphBackend):
    await backend.create_node("User", "u1", {})
    await backend.create_node("Post", "p1", {})

    records = [{"author_id": "u1", "post_id": "p1", "role": "primary"}]
    count = await load_edges(backend, records, "author_id", "post_id", "AUTHORED")

    assert count == 1
    edges = await backend.get_all_edges()
    assert len(edges) == 1
    assert edges[0]["type"] == "AUTHORED"


async def test_load_edges_skips_missing_ids(backend: InMemoryGraphBackend):
    records = [
        {"source": "u1"},  # missing target
        {"target": "p1"},  # missing source
    ]
    count = await load_edges(backend, records, "source", "target", "LINK")

    assert count == 0


async def test_load_from_schema(backend: InMemoryGraphBackend, sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)

    entity_data = {
        "User": [
            {"id": "u1", "name": "Alice", "email": "alice@example.com"},
            {"id": "u2", "name": "Bob", "email": "bob@example.com"},
        ],
        "Post": [
            {"id": "p1", "title": "Hello World", "author_id": "u1"},
        ],
        "Comment": [
            {"id": "c1", "body": "Great post!", "post_id": "p1", "user_id": "u2"},
        ],
    }

    relationship_data = {
        "AUTHORED_BY": [{"source": "p1", "target": "u1"}],
        "HAS_COMMENT": [{"source": "p1", "target": "c1"}],
        "COMMENTED_BY": [{"source": "c1", "target": "u2"}],
    }

    result = await load_from_schema(backend, schema, entity_data, relationship_data)

    assert result["nodes"] == 4
    assert result["edges"] == 3


async def test_load_from_schema_no_relationships(backend: InMemoryGraphBackend, sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    entity_data = {"User": [{"id": "u1", "name": "Alice", "email": "a@b.com"}]}

    result = await load_from_schema(backend, schema, entity_data)

    assert result["nodes"] == 1
    assert result["edges"] == 0


async def test_load_from_schema_empty_data(backend: InMemoryGraphBackend, sample_asd: AgenticSchema):
    schema = map_asd_to_graph_schema(sample_asd)
    result = await load_from_schema(backend, schema, {})

    assert result["nodes"] == 0
    assert result["edges"] == 0
