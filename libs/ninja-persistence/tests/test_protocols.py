"""Tests for the Repository protocol."""

from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_persistence.adapters.chroma import ChromaVectorAdapter
from ninja_persistence.adapters.graph import GraphAdapter
from ninja_persistence.adapters.milvus import MilvusVectorAdapter
from ninja_persistence.adapters.mongo import MongoAdapter
from ninja_persistence.adapters.sql import SQLAdapter
from ninja_persistence.protocols import Repository
from sqlalchemy.ext.asyncio import create_async_engine


def _make_entity(engine: StorageEngine) -> EntitySchema:
    return EntitySchema(
        name="Test",
        storage_engine=engine,
        fields=[FieldSchema(name="id", field_type=FieldType.STRING, primary_key=True)],
    )


def test_sql_adapter_is_repository():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    adapter = SQLAdapter(engine=engine, entity=_make_entity(StorageEngine.SQL))
    assert isinstance(adapter, Repository)


def test_mongo_adapter_is_repository():
    adapter = MongoAdapter(entity=_make_entity(StorageEngine.MONGO))
    assert isinstance(adapter, Repository)


def test_graph_adapter_is_repository():
    adapter = GraphAdapter(entity=_make_entity(StorageEngine.GRAPH))
    assert isinstance(adapter, Repository)


def test_chroma_adapter_is_repository():
    adapter = ChromaVectorAdapter(entity=_make_entity(StorageEngine.VECTOR))
    assert isinstance(adapter, Repository)


def test_milvus_adapter_is_repository():
    adapter = MilvusVectorAdapter(entity=_make_entity(StorageEngine.VECTOR))
    assert isinstance(adapter, Repository)
