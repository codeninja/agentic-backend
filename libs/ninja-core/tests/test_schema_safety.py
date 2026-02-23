"""Tests for schema-level safety validators (name and description validation)."""

import pytest
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import (
    MAX_DESCRIPTION_LENGTH,
    EntitySchema,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from pydantic import ValidationError


def _id_field() -> FieldSchema:
    return FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True)


# ---------------------------------------------------------------------------
# EntitySchema.name validation
# ---------------------------------------------------------------------------


class TestEntityNameValidation:
    def test_valid_pascal_case(self) -> None:
        e = EntitySchema(name="User", storage_engine=StorageEngine.SQL, fields=[_id_field()])
        assert e.name == "User"

    def test_valid_snake_case(self) -> None:
        e = EntitySchema(name="audit_log", storage_engine=StorageEngine.SQL, fields=[_id_field()])
        assert e.name == "audit_log"

    def test_valid_single_letter(self) -> None:
        e = EntitySchema(name="X", storage_engine=StorageEngine.SQL, fields=[_id_field()])
        assert e.name == "X"

    def test_valid_max_length(self) -> None:
        name = "A" + "b" * 63  # 64 chars total
        e = EntitySchema(name=name, storage_engine=StorageEngine.SQL, fields=[_id_field()])
        assert e.name == name

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            EntitySchema(name="Audit Log", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_hyphens(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            EntitySchema(name="audit-log", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_starts_with_number(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            EntitySchema(name="1Entity", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_newlines(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            EntitySchema(name="Entity\nevil", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_semicolons(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            EntitySchema(name="Entity;DROP", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            EntitySchema(name="A" * 65, storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_python_keyword(self) -> None:
        with pytest.raises(ValidationError, match="reserved keyword"):
            EntitySchema(name="class", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_def_keyword(self) -> None:
        with pytest.raises(ValidationError, match="reserved keyword"):
            EntitySchema(name="def", storage_engine=StorageEngine.SQL, fields=[_id_field()])

    def test_rejects_import_keyword(self) -> None:
        with pytest.raises(ValidationError, match="reserved keyword"):
            EntitySchema(name="import", storage_engine=StorageEngine.SQL, fields=[_id_field()])


# ---------------------------------------------------------------------------
# EntitySchema.description validation
# ---------------------------------------------------------------------------


class TestEntityDescriptionValidation:
    def test_valid_description(self) -> None:
        e = EntitySchema(
            name="User",
            storage_engine=StorageEngine.SQL,
            fields=[_id_field()],
            description="Represents system users.",
        )
        assert e.description == "Represents system users."

    def test_none_description_allowed(self) -> None:
        e = EntitySchema(name="User", storage_engine=StorageEngine.SQL, fields=[_id_field()])
        assert e.description is None

    def test_max_length_description(self) -> None:
        desc = "x" * MAX_DESCRIPTION_LENGTH
        e = EntitySchema(
            name="User",
            storage_engine=StorageEngine.SQL,
            fields=[_id_field()],
            description=desc,
        )
        assert len(e.description) == MAX_DESCRIPTION_LENGTH

    def test_rejects_too_long_description(self) -> None:
        with pytest.raises(ValidationError, match="Description too long"):
            EntitySchema(
                name="User",
                storage_engine=StorageEngine.SQL,
                fields=[_id_field()],
                description="x" * (MAX_DESCRIPTION_LENGTH + 1),
            )


# ---------------------------------------------------------------------------
# FieldSchema.name validation
# ---------------------------------------------------------------------------


class TestFieldNameValidation:
    def test_valid_snake_case(self) -> None:
        f = FieldSchema(name="created_at", field_type=FieldType.DATETIME)
        assert f.name == "created_at"

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            FieldSchema(name="created at", field_type=FieldType.DATETIME)

    def test_rejects_starts_with_number(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            FieldSchema(name="1field", field_type=FieldType.STRING)

    def test_rejects_python_keyword(self) -> None:
        with pytest.raises(ValidationError, match="reserved keyword"):
            FieldSchema(name="class", field_type=FieldType.STRING)

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            FieldSchema(name="field;evil", field_type=FieldType.STRING)

    def test_rejects_pydantic_model_config(self) -> None:
        with pytest.raises(ValidationError, match="Pydantic reserved attribute"):
            FieldSchema(name="model_config", field_type=FieldType.STRING)

    def test_rejects_pydantic_model_fields(self) -> None:
        with pytest.raises(ValidationError, match="Pydantic reserved attribute"):
            FieldSchema(name="model_fields", field_type=FieldType.STRING)

    def test_rejects_pydantic_model_validate(self) -> None:
        with pytest.raises(ValidationError, match="Pydantic reserved attribute"):
            FieldSchema(name="model_validate", field_type=FieldType.STRING)

    def test_rejects_pydantic_model_dump(self) -> None:
        with pytest.raises(ValidationError, match="Pydantic reserved attribute"):
            FieldSchema(name="model_dump", field_type=FieldType.STRING)

    def test_rejects_pydantic_model_dump_json(self) -> None:
        with pytest.raises(ValidationError, match="Pydantic reserved attribute"):
            FieldSchema(name="model_dump_json", field_type=FieldType.STRING)

    def test_allows_model_prefix_non_reserved(self) -> None:
        """Field names starting with 'model_' that are not reserved are valid."""
        f = FieldSchema(name="model_name", field_type=FieldType.STRING)
        assert f.name == "model_name"


# ---------------------------------------------------------------------------
# DomainSchema.name validation
# ---------------------------------------------------------------------------


class TestDomainNameValidation:
    def test_valid_name(self) -> None:
        d = DomainSchema(name="Billing", entities=["Order"])
        assert d.name == "Billing"

    def test_valid_underscore_name(self) -> None:
        d = DomainSchema(name="order_management", entities=["Order"])
        assert d.name == "order_management"

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            DomainSchema(name="Order Management", entities=["Order"])

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            DomainSchema(name="Billing; DROP TABLE", entities=["Order"])

    def test_rejects_python_keyword(self) -> None:
        with pytest.raises(ValidationError, match="reserved keyword"):
            DomainSchema(name="import", entities=["Order"])

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            DomainSchema(name="A" * 65, entities=["Order"])

    def test_rejects_too_long_description(self) -> None:
        with pytest.raises(ValidationError, match="Description too long"):
            DomainSchema(
                name="Billing",
                entities=["Order"],
                description="x" * (MAX_DESCRIPTION_LENGTH + 1),
            )
