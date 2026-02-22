"""Tests for the BoundaryProcessor — full integration pipeline."""

from datetime import datetime
from typing import Any

import pytest
from ninja_boundary.audit import CoercionAction
from ninja_boundary.boundary import BoundaryProcessor
from ninja_boundary.coercion import CoercionError, StrictnessLevel
from ninja_boundary.drift import DriftType
from ninja_boundary.validators import ValidationError, ValidatorRegistry
from ninja_core.schema.entity import (
    EntitySchema,
    FieldConstraint,
    FieldSchema,
    FieldType,
    StorageEngine,
)


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


# ===========================================================================
# Constraint validation at runtime
# ===========================================================================

def _constrained_schema() -> EntitySchema:
    """Entity with various field constraints for testing runtime validation."""
    return EntitySchema(
        name="Product",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(
                name="sku",
                field_type=FieldType.STRING,
                constraints=FieldConstraint(pattern=r"^[A-Z]{2}-\d{4}$"),
            ),
            FieldSchema(
                name="name",
                field_type=FieldType.STRING,
                constraints=FieldConstraint(min_length=2, max_length=50),
            ),
            FieldSchema(
                name="price",
                field_type=FieldType.FLOAT,
                constraints=FieldConstraint(ge=0.0, le=99999.99),
            ),
            FieldSchema(
                name="category",
                field_type=FieldType.ENUM,
                constraints=FieldConstraint(enum_values=["electronics", "clothing", "food"]),
            ),
        ],
    )


class TestConstraintValidation:
    """Tests for runtime field constraint validation in the boundary processor."""

    def test_pattern_match_passes(self):
        """Value matching the pattern passes validation."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "Widget",
            "price": 9.99,
            "category": "electronics",
        }
        result = processor.process(data, schema)
        assert result.data["sku"] == "AB-1234"

    def test_pattern_mismatch_rejected(self):
        """Value not matching the pattern raises ValidationError."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "invalid-sku",
            "name": "Widget",
            "price": 9.99,
            "category": "electronics",
        }
        with pytest.raises(ValidationError, match="does not match pattern"):
            processor.process(data, schema)

    def test_pattern_audit_on_failure(self):
        """Pattern validation failure is recorded in the audit log."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "bad",
            "name": "Widget",
            "price": 9.99,
            "category": "electronics",
        }
        with pytest.raises(ValidationError):
            processor.process(data, schema)

    def test_min_length_rejected(self):
        """String shorter than min_length is rejected."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "X",  # too short (min_length=2)
            "price": 9.99,
            "category": "electronics",
        }
        with pytest.raises(ValidationError, match="min_length"):
            processor.process(data, schema)

    def test_max_length_rejected(self):
        """String longer than max_length is rejected."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "A" * 51,  # too long (max_length=50)
            "price": 9.99,
            "category": "electronics",
        }
        with pytest.raises(ValidationError, match="max_length"):
            processor.process(data, schema)

    def test_ge_constraint_rejected(self):
        """Numeric value below ge is rejected."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "Widget",
            "price": -1.0,  # below ge=0.0
            "category": "electronics",
        }
        with pytest.raises(ValidationError, match="less than minimum"):
            processor.process(data, schema)

    def test_le_constraint_rejected(self):
        """Numeric value above le is rejected."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "Widget",
            "price": 100000.0,  # above le=99999.99
            "category": "electronics",
        }
        with pytest.raises(ValidationError, match="exceeds maximum"):
            processor.process(data, schema)

    def test_enum_constraint_rejected(self):
        """Value not in enum_values is rejected."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "Widget",
            "price": 9.99,
            "category": "toys",  # not in enum_values
        }
        with pytest.raises(ValidationError, match="not one of the allowed values"):
            processor.process(data, schema)

    def test_null_value_skips_constraints(self):
        """Null values should not be validated against constraints."""
        schema = EntitySchema(
            name="Item",
            storage_engine=StorageEngine.SQL,
            fields=[
                FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                FieldSchema(
                    name="code",
                    field_type=FieldType.STRING,
                    nullable=True,
                    constraints=FieldConstraint(pattern=r"^[A-Z]+$"),
                ),
            ],
        )
        processor = BoundaryProcessor()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "code": None,
        }
        result = processor.process(data, schema)
        assert result.data["code"] is None

    def test_all_constraints_pass(self):
        """All constraints pass for valid data — full pipeline works."""
        processor = BoundaryProcessor()
        schema = _constrained_schema()
        data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "AB-1234",
            "name": "Widget Pro",
            "price": 49.99,
            "category": "electronics",
        }
        result = processor.process(data, schema)
        assert result.data["sku"] == "AB-1234"
        assert result.data["price"] == 49.99
