"""Tests for EntitySchema and FieldSchema models."""

import pytest
from ninja_core.schema import (
    EmbeddingConfig,
    EntitySchema,
    FieldConstraint,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from pydantic import ValidationError


def _id_field() -> FieldSchema:
    return FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True)


class TestFieldSchema:
    def test_minimal_field(self):
        f = FieldSchema(name="title", field_type=FieldType.STRING)
        assert f.name == "title"
        assert f.field_type == FieldType.STRING
        assert f.nullable is False
        assert f.default is None
        assert f.primary_key is False

    def test_field_with_constraints(self):
        c = FieldConstraint(min_length=1, max_length=255, pattern=r"^[a-z]+$")
        f = FieldSchema(name="slug", field_type=FieldType.STRING, constraints=c)
        assert f.constraints is not None
        assert f.constraints.min_length == 1
        assert f.constraints.max_length == 255

    def test_field_with_embedding(self):
        emb = EmbeddingConfig(model="text-embedding-3-small", dimensions=1536)
        f = FieldSchema(name="content", field_type=FieldType.TEXT, embedding=emb)
        assert f.embedding is not None
        assert f.embedding.dimensions == 1536

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            FieldSchema(name="", field_type=FieldType.STRING)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            FieldSchema(name="x", field_type=FieldType.STRING, bogus="nope")

    def test_embedding_dimensions_must_be_positive(self):
        with pytest.raises(ValidationError):
            EmbeddingConfig(model="m", dimensions=0)

    def test_constraint_numeric(self):
        c = FieldConstraint(ge=0, le=100)
        assert c.ge == 0
        assert c.le == 100

    def test_constraint_enum_values(self):
        c = FieldConstraint(enum_values=["a", "b", "c"])
        assert c.enum_values == ["a", "b", "c"]


class TestEntitySchema:
    def test_sql_entity(self):
        e = EntitySchema(
            name="User",
            storage_engine=StorageEngine.SQL,
            fields=[
                _id_field(),
                FieldSchema(name="email", field_type=FieldType.STRING, unique=True),
            ],
        )
        assert e.name == "User"
        assert e.storage_engine == StorageEngine.SQL
        assert len(e.fields) == 2

    def test_mongo_entity(self):
        e = EntitySchema(
            name="AuditLog",
            storage_engine=StorageEngine.MONGO,
            fields=[_id_field()],
            collection_name="audit_logs",
        )
        assert e.collection_name == "audit_logs"

    def test_graph_entity(self):
        e = EntitySchema(
            name="Person",
            storage_engine=StorageEngine.GRAPH,
            fields=[_id_field(), FieldSchema(name="name", field_type=FieldType.STRING)],
        )
        assert e.storage_engine == StorageEngine.GRAPH

    def test_vector_entity(self):
        emb = EmbeddingConfig(model="text-embedding-3-small", dimensions=1536)
        e = EntitySchema(
            name="Document",
            storage_engine=StorageEngine.VECTOR,
            fields=[
                _id_field(),
                FieldSchema(name="content", field_type=FieldType.TEXT, embedding=emb),
            ],
        )
        assert e.storage_engine == StorageEngine.VECTOR

    def test_entity_requires_at_least_one_field(self):
        with pytest.raises(ValidationError):
            EntitySchema(name="Empty", storage_engine=StorageEngine.SQL, fields=[])

    def test_entity_with_tags(self):
        e = EntitySchema(
            name="Product",
            storage_engine=StorageEngine.SQL,
            fields=[_id_field()],
            tags=["core", "inventory"],
        )
        assert e.tags == ["core", "inventory"]

    def test_entity_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            EntitySchema(
                name="X",
                storage_engine=StorageEngine.SQL,
                fields=[_id_field()],
                nonexistent="boom",
            )
