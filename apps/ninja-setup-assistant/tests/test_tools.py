"""Tests for the setup assistant tool functions.

All tools are tested independently of any LLM — they operate directly on
the SchemaWorkspace.
"""

from __future__ import annotations

import json

import pytest
from ninja_core.schema.entity import FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipType
from ninja_setup_assistant.tools import (
    SchemaWorkspace,
    add_entity,
    add_relationship,
    confirm_schema,
    create_domain,
    review_schema,
)


@pytest.fixture()
def workspace() -> SchemaWorkspace:
    return SchemaWorkspace(schema=AgenticSchema(project_name="test-project"))


# ---------------------------------------------------------------------------
# add_entity
# ---------------------------------------------------------------------------


class TestAddEntity:
    def test_add_basic_entity(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(
            workspace,
            name="User",
            fields=[
                {"name": "id", "field_type": "uuid", "primary_key": True},
                {"name": "email", "field_type": "string", "unique": True},
                {"name": "name", "field_type": "string"},
            ],
        )
        assert "Added entity 'User'" in result
        assert len(workspace.schema.entities) == 1
        entity = workspace.schema.entities[0]
        assert entity.name == "User"
        assert entity.storage_engine == StorageEngine.SQL
        assert len(entity.fields) == 3

    def test_add_entity_with_storage_engine(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(
            workspace,
            name="Product",
            fields=[{"name": "id", "field_type": "string"}],
            storage_engine="mongo",
        )
        assert "mongo" in result
        assert workspace.schema.entities[0].storage_engine == StorageEngine.MONGO

    def test_add_entity_with_description(self, workspace: SchemaWorkspace) -> None:
        add_entity(
            workspace,
            name="Order",
            fields=[{"name": "id", "field_type": "uuid"}],
            description="Customer orders",
        )
        assert workspace.schema.entities[0].description == "Customer orders"

    def test_duplicate_entity_rejected(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        result = add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "string"}])
        assert "already exists" in result
        assert len(workspace.schema.entities) == 1

    def test_field_type_defaults_to_string(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="Tag", fields=[{"name": "label"}])
        assert workspace.schema.entities[0].fields[0].field_type == FieldType.STRING

    def test_boolean_fields_from_string(self, workspace: SchemaWorkspace) -> None:
        add_entity(
            workspace,
            name="User",
            fields=[{"name": "id", "field_type": "uuid", "primary_key": "true", "nullable": "false"}],
        )
        field = workspace.schema.entities[0].fields[0]
        assert field.primary_key is True
        assert field.nullable is False

    def test_multiple_entities(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        add_entity(workspace, name="Post", fields=[{"name": "id", "field_type": "uuid"}])
        assert len(workspace.schema.entities) == 2


# ---------------------------------------------------------------------------
# add_relationship
# ---------------------------------------------------------------------------


class TestAddRelationship:
    @pytest.fixture(autouse=True)
    def _setup_entities(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        add_entity(workspace, name="Post", fields=[{"name": "id", "field_type": "uuid"}])

    def test_add_basic_relationship(self, workspace: SchemaWorkspace) -> None:
        result = add_relationship(
            workspace,
            name="user_posts",
            source_entity="Post",
            target_entity="User",
        )
        assert "Added relationship" in result
        assert len(workspace.schema.relationships) == 1
        rel = workspace.schema.relationships[0]
        assert rel.source_entity == "Post"
        assert rel.target_entity == "User"
        assert rel.relationship_type == RelationshipType.HARD
        assert rel.cardinality == Cardinality.MANY_TO_ONE

    def test_add_relationship_with_cardinality(self, workspace: SchemaWorkspace) -> None:
        add_relationship(
            workspace,
            name="user_posts",
            source_entity="User",
            target_entity="Post",
            cardinality="one_to_many",
        )
        assert workspace.schema.relationships[0].cardinality == Cardinality.ONE_TO_MANY

    def test_add_graph_relationship(self, workspace: SchemaWorkspace) -> None:
        add_relationship(
            workspace,
            name="user_wrote_post",
            source_entity="User",
            target_entity="Post",
            relationship_type="graph",
            cardinality="many_to_many",
        )
        rel = workspace.schema.relationships[0]
        assert rel.relationship_type == RelationshipType.GRAPH

    def test_missing_source_entity(self, workspace: SchemaWorkspace) -> None:
        result = add_relationship(
            workspace,
            name="bad_rel",
            source_entity="NonExistent",
            target_entity="User",
        )
        assert "not found" in result
        assert len(workspace.schema.relationships) == 0

    def test_missing_target_entity(self, workspace: SchemaWorkspace) -> None:
        result = add_relationship(
            workspace,
            name="bad_rel",
            source_entity="User",
            target_entity="NonExistent",
        )
        assert "not found" in result

    def test_relationship_with_fields(self, workspace: SchemaWorkspace) -> None:
        add_relationship(
            workspace,
            name="post_author",
            source_entity="Post",
            target_entity="User",
            source_field="author_id",
            target_field="id",
        )
        rel = workspace.schema.relationships[0]
        assert rel.source_field == "author_id"
        assert rel.target_field == "id"


# ---------------------------------------------------------------------------
# create_domain
# ---------------------------------------------------------------------------


class TestCreateDomain:
    @pytest.fixture(autouse=True)
    def _setup_entities(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        add_entity(workspace, name="Post", fields=[{"name": "id", "field_type": "uuid"}])

    def test_create_domain(self, workspace: SchemaWorkspace) -> None:
        result = create_domain(workspace, name="Content", entities=["User", "Post"])
        assert "Created domain" in result
        assert len(workspace.schema.domains) == 1
        assert workspace.schema.domains[0].name == "Content"
        assert workspace.schema.domains[0].entities == ["User", "Post"]

    def test_create_domain_with_description(self, workspace: SchemaWorkspace) -> None:
        create_domain(workspace, name="Users", entities=["User"], description="User management")
        assert workspace.schema.domains[0].description == "User management"

    def test_domain_with_missing_entity(self, workspace: SchemaWorkspace) -> None:
        result = create_domain(workspace, name="Bad", entities=["User", "NonExistent"])
        assert "not found" in result
        assert len(workspace.schema.domains) == 0

    def test_duplicate_domain_rejected(self, workspace: SchemaWorkspace) -> None:
        create_domain(workspace, name="Users", entities=["User"])
        result = create_domain(workspace, name="Users", entities=["Post"])
        assert "already exists" in result
        assert len(workspace.schema.domains) == 1


# ---------------------------------------------------------------------------
# review_schema
# ---------------------------------------------------------------------------


class TestReviewSchema:
    def test_empty_schema(self, workspace: SchemaWorkspace) -> None:
        result = review_schema(workspace)
        assert "No entities defined" in result

    def test_schema_with_entities(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        result = review_schema(workspace)
        assert "User" in result
        assert "sql" in result
        assert "Entities (1)" in result

    def test_schema_with_relationships(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        add_entity(workspace, name="Post", fields=[{"name": "id", "field_type": "uuid"}])
        add_relationship(workspace, name="user_posts", source_entity="Post", target_entity="User")
        result = review_schema(workspace)
        assert "Relationships (1)" in result
        assert "user_posts" in result

    def test_schema_with_domains(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        create_domain(workspace, name="Users", entities=["User"])
        result = review_schema(workspace)
        assert "Domains (1)" in result


# ---------------------------------------------------------------------------
# confirm_schema
# ---------------------------------------------------------------------------


class TestConfirmSchema:
    def test_confirm_empty_schema(self, workspace: SchemaWorkspace) -> None:
        result = confirm_schema(workspace)
        assert "Cannot confirm" in result

    def test_confirm_valid_schema(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        result = confirm_schema(workspace)
        data = json.loads(result)
        assert data["project_name"] == "test-project"
        assert len(data["entities"]) == 1
        assert data["entities"][0]["name"] == "User"

    def test_confirm_preserves_all_data(self, workspace: SchemaWorkspace) -> None:
        add_entity(workspace, name="User", fields=[{"name": "id", "field_type": "uuid"}])
        add_entity(workspace, name="Post", fields=[{"name": "id", "field_type": "uuid"}])
        add_relationship(workspace, name="user_posts", source_entity="Post", target_entity="User")
        create_domain(workspace, name="Content", entities=["User", "Post"])

        result = confirm_schema(workspace)
        data = json.loads(result)
        assert len(data["entities"]) == 2
        assert len(data["relationships"]) == 1
        assert len(data["domains"]) == 1
