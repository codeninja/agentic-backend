"""Tests for the SQL introspection provider using a real SQLite database."""

import pytest
from ninja_core.schema.entity import FieldType, StorageEngine
from ninja_core.schema.relationship import Cardinality, RelationshipType
from ninja_introspect.providers.sql import SQLProvider, _table_to_pascal
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    bio = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    posts = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    view_count = Column(Integer, default=0)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author = relationship("User", back_populates="posts")


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    label = Column(String(50), nullable=False, unique=True)


@pytest.fixture
async def sqlite_url(tmp_path):
    """Create a SQLite database with test tables and return the URL."""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return url


async def test_introspects_tables(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    entity_names = {e.name for e in result.entities}
    assert "Users" in entity_names
    assert "Posts" in entity_names
    assert "Tags" in entity_names


async def test_entity_storage_engine(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    for entity in result.entities:
        assert entity.storage_engine == StorageEngine.SQL


async def test_entity_collection_name(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    users = next(e for e in result.entities if e.name == "Users")
    assert users.collection_name == "users"


async def test_fields_detected(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    users = next(e for e in result.entities if e.name == "Users")
    field_names = {f.name for f in users.fields}
    assert "id" in field_names
    assert "name" in field_names
    assert "email" in field_names
    assert "bio" in field_names
    assert "is_active" in field_names


async def test_primary_key_detected(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    users = next(e for e in result.entities if e.name == "Users")
    id_field = next(f for f in users.fields if f.name == "id")
    assert id_field.primary_key is True
    assert id_field.indexed is True


async def test_field_types_mapped(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    users = next(e for e in result.entities if e.name == "Users")
    fields_by_name = {f.name: f for f in users.fields}

    assert fields_by_name["id"].field_type == FieldType.INTEGER
    assert fields_by_name["name"].field_type == FieldType.STRING
    assert fields_by_name["bio"].field_type == FieldType.TEXT


async def test_nullable_detected(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    users = next(e for e in result.entities if e.name == "Users")
    fields_by_name = {f.name: f for f in users.fields}

    assert fields_by_name["bio"].nullable is True
    assert fields_by_name["name"].nullable is False


async def test_foreign_keys_produce_relationships(sqlite_url):
    provider = SQLProvider()
    result = await provider.introspect(sqlite_url)

    assert len(result.relationships) >= 1
    fk_rel = next(r for r in result.relationships if r.source_entity == "Posts")
    assert fk_rel.target_entity == "Users"
    assert fk_rel.relationship_type == RelationshipType.HARD
    assert fk_rel.cardinality == Cardinality.MANY_TO_ONE
    assert fk_rel.source_field == "author_id"
    assert fk_rel.target_field == "id"


async def test_empty_database():
    """An empty database should produce no entities."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "empty.db")
        url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(url)
        async with engine.begin():
            pass  # No tables created
        await engine.dispose()

        provider = SQLProvider()
        result = await provider.introspect(url)
        assert result.entities == []
        assert result.relationships == []


def test_table_to_pascal():
    assert _table_to_pascal("user_accounts") == "UserAccounts"
    assert _table_to_pascal("posts") == "Posts"
    assert _table_to_pascal("a_b_c") == "ABC"
