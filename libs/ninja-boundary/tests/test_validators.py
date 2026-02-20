"""Tests for pluggable validators."""

from typing import Any

import pytest
from ninja_boundary.audit import AuditLog
from ninja_boundary.validators import ValidationError, ValidatorRegistry


class UpperCaseValidator:
    """Test validator that uppercases string fields."""

    def validate(self, field_name: str, value: Any, data: dict[str, Any]) -> Any:
        if field_name == "name" and isinstance(value, str):
            return value.upper()
        return value


class RejectNegativeValidator:
    """Test validator that rejects negative numbers."""

    def validate(self, field_name: str, value: Any, data: dict[str, Any]) -> Any:
        if field_name == "age" and isinstance(value, int) and value < 0:
            raise ValidationError("User", field_name, "age cannot be negative")
        return value


class TestValidatorRegistry:
    def test_register_and_run(self):
        registry = ValidatorRegistry()
        registry.register("User", UpperCaseValidator())
        data = {"name": "alice", "age": 30}
        result = registry.run("User", data)
        assert result["name"] == "ALICE"

    def test_no_validators_passthrough(self):
        registry = ValidatorRegistry()
        data = {"name": "alice"}
        result = registry.run("User", data)
        assert result["name"] == "alice"

    def test_validation_error_raised(self):
        registry = ValidatorRegistry()
        registry.register("User", RejectNegativeValidator())
        data = {"name": "alice", "age": -5}
        with pytest.raises(ValidationError):
            registry.run("User", data)

    def test_audit_records_transformation(self):
        registry = ValidatorRegistry()
        registry.register("User", UpperCaseValidator())
        audit = AuditLog()
        data = {"name": "alice"}
        registry.run("User", data, audit=audit)
        assert len(audit) == 1

    def test_multiple_validators(self):
        registry = ValidatorRegistry()
        registry.register("User", UpperCaseValidator())
        registry.register("User", RejectNegativeValidator())
        data = {"name": "alice", "age": 25}
        result = registry.run("User", data)
        assert result["name"] == "ALICE"
        assert result["age"] == 25
