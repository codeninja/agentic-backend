"""Tests for setup assistant tool input validation (safety layer)."""

from __future__ import annotations

import pytest
from ninja_core.schema.entity import MAX_DESCRIPTION_LENGTH
from ninja_core.schema.project import AgenticSchema
from ninja_setup_assistant.tools import (
    SchemaWorkspace,
    add_entity,
    create_domain,
)


@pytest.fixture()
def workspace() -> SchemaWorkspace:
    return SchemaWorkspace(schema=AgenticSchema(project_name="test-project"))


def _valid_fields() -> list[dict[str, str]]:
    return [{"name": "id", "field_type": "uuid", "primary_key": "true"}]


# ---------------------------------------------------------------------------
# Entity name validation
# ---------------------------------------------------------------------------


class TestEntityNameValidation:
    def test_rejects_empty_name(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(workspace, name="", fields=_valid_fields())
        assert "must not be empty" in result

    def test_rejects_special_chars(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(workspace, name="Entity;DROP", fields=_valid_fields())
        assert "not a valid identifier" in result

    def test_rejects_spaces(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(workspace, name="My Entity", fields=_valid_fields())
        assert "not a valid identifier" in result

    def test_rejects_starts_with_number(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(workspace, name="1Entity", fields=_valid_fields())
        assert "not a valid identifier" in result

    def test_rejects_too_long(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(workspace, name="A" * 65, fields=_valid_fields())
        assert "not a valid identifier" in result

    def test_accepts_valid_name(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(workspace, name="User", fields=_valid_fields())
        assert "Added entity" in result


# ---------------------------------------------------------------------------
# Field name validation
# ---------------------------------------------------------------------------


class TestFieldNameValidation:
    def test_rejects_empty_field_name(self, workspace: SchemaWorkspace) -> None:
        fields = [{"name": "", "field_type": "string"}]
        result = add_entity(workspace, name="User", fields=fields)
        assert "must not be empty" in result

    def test_rejects_special_chars_in_field(self, workspace: SchemaWorkspace) -> None:
        fields = [{"name": "field;evil", "field_type": "string", "primary_key": "true"}]
        result = add_entity(workspace, name="User", fields=fields)
        assert "not a valid identifier" in result

    def test_rejects_invalid_field_type(self, workspace: SchemaWorkspace) -> None:
        fields = [{"name": "id", "field_type": "invalid_type", "primary_key": "true"}]
        result = add_entity(workspace, name="User", fields=fields)
        assert "Invalid field type" in result


# ---------------------------------------------------------------------------
# Description length validation
# ---------------------------------------------------------------------------


class TestDescriptionValidation:
    def test_rejects_too_long_entity_description(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(
            workspace,
            name="User",
            fields=_valid_fields(),
            description="x" * (MAX_DESCRIPTION_LENGTH + 1),
        )
        assert "description too long" in result.lower()

    def test_accepts_max_length_description(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(
            workspace,
            name="User",
            fields=_valid_fields(),
            description="x" * MAX_DESCRIPTION_LENGTH,
        )
        assert "Added entity" in result


# ---------------------------------------------------------------------------
# Storage engine validation
# ---------------------------------------------------------------------------


class TestStorageEngineValidation:
    def test_rejects_invalid_storage_engine(self, workspace: SchemaWorkspace) -> None:
        result = add_entity(
            workspace,
            name="User",
            fields=_valid_fields(),
            storage_engine="invalid_engine",
        )
        assert "Invalid storage engine" in result


# ---------------------------------------------------------------------------
# Domain name validation
# ---------------------------------------------------------------------------


class TestDomainNameValidation:
    def test_rejects_empty_domain_name(self, workspace: SchemaWorkspace) -> None:
        result = create_domain(workspace, name="", entities=["User"])
        assert "must not be empty" in result

    def test_rejects_special_chars(self, workspace: SchemaWorkspace) -> None:
        result = create_domain(workspace, name="Domain;evil", entities=["User"])
        assert "not a valid identifier" in result

    def test_rejects_too_long_domain_description(self, workspace: SchemaWorkspace) -> None:
        # First add an entity so create_domain can proceed
        add_entity(workspace, name="User", fields=_valid_fields())
        result = create_domain(
            workspace,
            name="Billing",
            entities=["User"],
            description="x" * (MAX_DESCRIPTION_LENGTH + 1),
        )
        assert "description too long" in result.lower()
