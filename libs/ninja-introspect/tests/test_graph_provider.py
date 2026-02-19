"""Tests for the Neo4j graph introspection provider using mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from ninja_core.schema.entity import FieldType, StorageEngine
from ninja_core.schema.relationship import RelationshipType
from ninja_introspect.providers.graph import GraphProvider, _python_type_to_field_type


class TestPythonTypeToFieldType:
    def test_bool(self):
        assert _python_type_to_field_type(True) == FieldType.BOOLEAN

    def test_int(self):
        assert _python_type_to_field_type(42) == FieldType.INTEGER

    def test_float(self):
        assert _python_type_to_field_type(3.14) == FieldType.FLOAT

    def test_list(self):
        assert _python_type_to_field_type([1, 2]) == FieldType.ARRAY

    def test_string(self):
        assert _python_type_to_field_type("hello") == FieldType.STRING


class _AsyncIterator:
    """Helper to make a list async-iterable (for mocking Neo4j results)."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


def _make_record(data: dict):
    """Create a mock Neo4j record."""
    record = MagicMock()
    record.__getitem__ = lambda self, key: data[key]
    return record


def _make_mock_driver(labels: list[str], nodes: dict[str, list[dict]], rels: list[dict]):
    """Create a mock Neo4j async driver."""
    driver = MagicMock()

    session = MagicMock()

    async def mock_run(query, **kwargs):
        result = MagicMock()
        if "db.labels" in query:
            records = [_make_record({"label": lbl}) for lbl in labels]
            result.__aiter__ = lambda self: _AsyncIterator(records).__aiter__()
            result.__anext__ = lambda self: _AsyncIterator(records).__anext__()
        elif "properties(n)" in query:
            # Extract label from query
            label = None
            for lbl in labels:
                if f"`{lbl}`" in query:
                    label = lbl
                    break
            docs = nodes.get(label, [])
            records = [_make_record({"props": doc}) for doc in docs]
            result.__aiter__ = lambda self, r=records: _AsyncIterator(r).__aiter__()
            result.__anext__ = lambda self, r=records: _AsyncIterator(r).__anext__()
        elif "MATCH (a)-[r]->(b)" in query:
            records = [_make_record(r) for r in rels]
            result.__aiter__ = lambda self, r=records: _AsyncIterator(r).__aiter__()
            result.__anext__ = lambda self, r=records: _AsyncIterator(r).__anext__()
        else:
            result.__aiter__ = lambda self: _AsyncIterator([]).__aiter__()
            result.__anext__ = lambda self: _AsyncIterator([]).__anext__()
        return result

    session.run = mock_run

    ctx_manager = MagicMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=session)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    driver.session.return_value = ctx_manager
    driver.close = AsyncMock()

    return driver


@patch("ninja_introspect.providers.graph.AsyncGraphDatabase")
async def test_introspect_nodes(mock_neo4j):
    nodes = {
        "Person": [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ],
    }
    mock_driver = _make_mock_driver(
        labels=["Person"],
        nodes=nodes,
        rels=[],
    )
    mock_neo4j.driver.return_value = mock_driver

    provider = GraphProvider()
    result = await provider.introspect("bolt://localhost:7687")

    assert len(result.entities) == 1
    entity = result.entities[0]
    assert entity.name == "Person"
    assert entity.storage_engine == StorageEngine.GRAPH

    field_names = {f.name for f in entity.fields}
    assert "name" in field_names
    assert "age" in field_names


@patch("ninja_introspect.providers.graph.AsyncGraphDatabase")
async def test_introspect_relationships(mock_neo4j):
    nodes = {
        "Person": [{"name": "Alice"}],
        "Company": [{"name": "Acme"}],
    }
    rels = [
        {"rel_type": "WORKS_AT", "src": "Person", "tgt": "Company"},
    ]
    mock_driver = _make_mock_driver(
        labels=["Person", "Company"],
        nodes=nodes,
        rels=rels,
    )
    mock_neo4j.driver.return_value = mock_driver

    provider = GraphProvider()
    result = await provider.introspect("bolt://localhost:7687")

    assert len(result.relationships) == 1
    rel = result.relationships[0]
    assert rel.source_entity == "Person"
    assert rel.target_entity == "Company"
    assert rel.relationship_type == RelationshipType.GRAPH
    assert rel.edge_label == "WORKS_AT"


@patch("ninja_introspect.providers.graph.AsyncGraphDatabase")
async def test_empty_graph(mock_neo4j):
    mock_driver = _make_mock_driver(labels=[], nodes={}, rels=[])
    mock_neo4j.driver.return_value = mock_driver

    provider = GraphProvider()
    result = await provider.introspect("bolt://localhost:7687")

    assert result.entities == []
    assert result.relationships == []


@patch("ninja_introspect.providers.graph.AsyncGraphDatabase")
async def test_field_types_inferred(mock_neo4j):
    nodes = {
        "Item": [
            {"count": 5, "price": 9.99, "active": True, "tags": ["a", "b"]},
        ],
    }
    mock_driver = _make_mock_driver(labels=["Item"], nodes=nodes, rels=[])
    mock_neo4j.driver.return_value = mock_driver

    provider = GraphProvider()
    result = await provider.introspect("bolt://localhost:7687")

    entity = result.entities[0]
    fields_by_name = {f.name: f for f in entity.fields}
    assert fields_by_name["count"].field_type == FieldType.INTEGER
    assert fields_by_name["price"].field_type == FieldType.FLOAT
    assert fields_by_name["active"].field_type == FieldType.BOOLEAN
    assert fields_by_name["tags"].field_type == FieldType.ARRAY
