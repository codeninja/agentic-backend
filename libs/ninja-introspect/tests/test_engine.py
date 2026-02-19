"""Tests for the introspection engine orchestrator."""

from __future__ import annotations

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_introspect.engine import IntrospectionEngine, _detect_provider
from ninja_introspect.providers.base import IntrospectionProvider, IntrospectionResult
from ninja_introspect.providers.graph import GraphProvider
from ninja_introspect.providers.mongo import MongoProvider
from ninja_introspect.providers.sql import SQLProvider
from ninja_introspect.providers.vector import VectorProvider
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship


class TestDetectProvider:
    def test_sqlite(self):
        assert isinstance(_detect_provider("sqlite+aiosqlite:///test.db"), SQLProvider)

    def test_postgresql(self):
        assert isinstance(_detect_provider("postgresql://localhost/db"), SQLProvider)

    def test_postgresql_asyncpg(self):
        assert isinstance(_detect_provider("postgresql+asyncpg://localhost/db"), SQLProvider)

    def test_mongodb(self):
        assert isinstance(_detect_provider("mongodb://localhost:27017/db"), MongoProvider)

    def test_mongodb_srv(self):
        assert isinstance(_detect_provider("mongodb+srv://host/db"), MongoProvider)

    def test_neo4j(self):
        assert isinstance(_detect_provider("neo4j://localhost:7687"), GraphProvider)

    def test_bolt(self):
        assert isinstance(_detect_provider("bolt://localhost:7687"), GraphProvider)

    def test_http_vector(self):
        assert isinstance(_detect_provider("http://localhost:8000"), VectorProvider)

    def test_path_vector(self):
        assert isinstance(_detect_provider("/tmp/chroma_data"), VectorProvider)

    def test_unknown_scheme_raises(self):
        with pytest.raises(ValueError, match="Cannot detect provider"):
            _detect_provider("ftp://example.com")


class Base(DeclarativeBase):
    pass


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    employees = relationship("Employee", back_populates="department")


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    dept_id = Column(Integer, ForeignKey("departments.id"))
    department = relationship("Department", back_populates="employees")


@pytest.fixture
async def sqlite_url(tmp_path):
    db_path = tmp_path / "engine_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return url


async def test_engine_with_sql(sqlite_url):
    engine = IntrospectionEngine(project_name="test-project")
    schema = await engine.run([sqlite_url])

    assert schema.project_name == "test-project"
    assert schema.version == "1.0"
    assert len(schema.entities) == 2

    entity_names = {e.name for e in schema.entities}
    assert "Departments" in entity_names
    assert "Employees" in entity_names

    assert len(schema.relationships) >= 1


async def test_engine_with_custom_provider():
    """Test that custom provider overrides work."""

    class FakeProvider(IntrospectionProvider):
        async def introspect(self, connection_string: str) -> IntrospectionResult:
            return IntrospectionResult(
                entities=[
                    EntitySchema(
                        name="FakeEntity",
                        storage_engine=StorageEngine.SQL,
                        fields=[FieldSchema(name="id", field_type=FieldType.INTEGER, primary_key=True)],
                    )
                ]
            )

    engine = IntrospectionEngine(project_name="custom")
    schema = await engine.run(
        ["custom://db"],
        providers={"custom://db": FakeProvider()},
    )

    assert len(schema.entities) == 1
    assert schema.entities[0].name == "FakeEntity"


async def test_engine_multiple_sources(sqlite_url):
    """Test merging results from multiple providers."""

    class MockMongoProvider(IntrospectionProvider):
        async def introspect(self, connection_string: str) -> IntrospectionResult:
            return IntrospectionResult(
                entities=[
                    EntitySchema(
                        name="Products",
                        storage_engine=StorageEngine.MONGO,
                        fields=[
                            FieldSchema(name="_id", field_type=FieldType.STRING, primary_key=True),
                            FieldSchema(name="title", field_type=FieldType.STRING),
                        ],
                        collection_name="products",
                    )
                ]
            )

    engine = IntrospectionEngine(project_name="multi")
    schema = await engine.run(
        [sqlite_url, "mongodb://localhost:27017/shop"],
        providers={"mongodb://localhost:27017/shop": MockMongoProvider()},
    )

    # Should have SQL entities + Mongo entity
    entity_names = {e.name for e in schema.entities}
    assert "Departments" in entity_names
    assert "Employees" in entity_names
    assert "Products" in entity_names

    storage_engines = {e.storage_engine for e in schema.entities}
    assert StorageEngine.SQL in storage_engines
    assert StorageEngine.MONGO in storage_engines
