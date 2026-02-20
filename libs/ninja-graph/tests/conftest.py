"""Shared fixtures for ninja-graph tests."""

from __future__ import annotations

import pytest
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType
from ninja_graph.memory_backend import InMemoryGraphBackend


@pytest.fixture
def backend() -> InMemoryGraphBackend:
    return InMemoryGraphBackend()


@pytest.fixture
def sample_asd() -> AgenticSchema:
    """A sample ASD with Users, Posts, and Comments."""
    return AgenticSchema(
        project_name="test-project",
        entities=[
            EntitySchema(
                name="User",
                storage_engine=StorageEngine.SQL,
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                    FieldSchema(name="name", field_type=FieldType.STRING),
                    FieldSchema(name="email", field_type=FieldType.STRING, unique=True),
                ],
            ),
            EntitySchema(
                name="Post",
                storage_engine=StorageEngine.SQL,
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                    FieldSchema(name="title", field_type=FieldType.STRING),
                    FieldSchema(name="author_id", field_type=FieldType.UUID),
                ],
            ),
            EntitySchema(
                name="Comment",
                storage_engine=StorageEngine.MONGO,
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                    FieldSchema(name="body", field_type=FieldType.TEXT),
                    FieldSchema(name="post_id", field_type=FieldType.UUID),
                    FieldSchema(name="user_id", field_type=FieldType.UUID),
                ],
            ),
        ],
        relationships=[
            RelationshipSchema(
                name="authored_by",
                source_entity="Post",
                target_entity="User",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.MANY_TO_ONE,
                source_field="author_id",
                target_field="id",
                edge_label="AUTHORED_BY",
            ),
            RelationshipSchema(
                name="has_comment",
                source_entity="Post",
                target_entity="Comment",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id",
                target_field="post_id",
            ),
            RelationshipSchema(
                name="commented_by",
                source_entity="Comment",
                target_entity="User",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.MANY_TO_ONE,
                source_field="user_id",
                target_field="id",
            ),
        ],
    )
