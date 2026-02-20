"""Tests for the BoundaryProcessor — full integration pipeline."""

from datetime import datetime
from typing import Any

import pytest
from ninja_boundary.audit import CoercionAction
from ninja_boundary.boundary import BoundaryProcessor
from ninja_boundary.coercion import CoercionError, StrictnessLevel
from ninja_boundary.drift import DriftType
from ninja_boundary.validators import ValidationError, ValidatorRegistry
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine


def _user_schema() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.MONGO,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="age", field_type=FieldType.INTEGER),
            FieldSchema(name="active", field_type=FieldType.BOOLEAN),
            FieldSchema(name="created_at", field_type=FieldType.DATETIME),
            FieldSchema(name="email", field_type=FieldType.STRING, nullable=True),
        ],
    )


class TestBoundaryProcessor:
    def test_mongo_string_int_coercion(self):
        """Acceptance: A Mongo document with string '123' in an int field must coerce successfully."""
        processor = BoundaryProcessor()
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice",
            "age": "30",  # String in int field
            "active": True,
        }
        result = processor.process(data, schema)
        assert result.data["age"] == 30
        assert isinstance(result.data["age"], int)

    def test_missing_created_at_gets_default(self):
        """Acceptance: A missing created_at field must get a sensible default."""
        processor = BoundaryProcessor()
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice",
            "age": 30,
            "active": True,
        }
        result = processor.process(data, schema)
        assert "created_at" in result.data
        assert isinstance(result.data["created_at"], datetime)

    def test_extra_field_triggers_drift(self):
        """Acceptance: A new unexpected field triggers a drift warning."""
        processor = BoundaryProcessor()
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice",
            "age": 30,
            "active": True,
            "phone": "555-1234",  # Not in schema
        }
        result = processor.process(data, schema)
        extra = [e for e in result.drift_events if e.drift_type == DriftType.EXTRA_FIELD]
        assert len(extra) == 1
        assert extra[0].field_name == "phone"

    def test_audit_captures_coercions(self):
        """Acceptance: Audit log captures every transformation with before/after values."""
        processor = BoundaryProcessor()
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice",
            "age": "30",
            "active": "true",
        }
        result = processor.process(data, schema)
        type_casts = result.audit.filter_by_action(CoercionAction.TYPE_CAST)
        assert len(type_casts) >= 2  # age and active were coerced
        for entry in type_casts:
            assert entry.before is not None or entry.after is not None
            assert entry.entity_name == "User"

    def test_full_pipeline(self):
        """End-to-end: coerce + defaults + drift detection all in one pass."""
        processor = BoundaryProcessor()
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Bob",
            "age": "25",
            "active": "yes",
            "extra_field": "surprise",
        }
        result = processor.process(data, schema)
        # Coercion worked
        assert result.data["age"] == 25
        assert result.data["active"] is True
        # Defaults applied
        assert "created_at" in result.data
        assert isinstance(result.data["created_at"], datetime)
        # Drift detected
        assert any(e.field_name == "extra_field" for e in result.drift_events)
        # Audit has entries
        assert len(result.audit) > 0

    def test_strict_mode_rejects_type_mismatch(self):
        processor = BoundaryProcessor(strictness=StrictnessLevel.STRICT)
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice",
            "age": "30",  # strict mode won't allow str->int
            "active": True,
        }
        with pytest.raises(CoercionError):
            processor.process(data, schema)

    def test_custom_validators_run(self):
        class NoSpacesValidator:
            def validate(self, field_name: str, value: Any, data: dict[str, Any]) -> Any:
                if field_name == "name" and isinstance(value, str) and " " in value:
                    raise ValidationError("User", field_name, "no spaces allowed")
                return value

        registry = ValidatorRegistry()
        registry.register("User", NoSpacesValidator())
        processor = BoundaryProcessor(validator_registry=registry)
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice Bob",
            "age": 30,
            "active": True,
        }
        with pytest.raises(ValidationError):
            processor.process(data, schema)

    def test_nullable_empty_string_coercion(self):
        processor = BoundaryProcessor()
        schema = _user_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Alice",
            "age": 30,
            "active": True,
            "email": "",  # nullable string stays as empty string
        }
        result = processor.process(data, schema)
        # STRING type keeps empty string even when nullable
        assert result.data["email"] == ""
