"""Pluggable per-entity validation hooks."""

from __future__ import annotations

from typing import Any, Protocol

from ninja_boundary.audit import AuditLog, CoercionAction


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, entity_name: str, field_name: str, message: str) -> None:
        self.entity_name = entity_name
        self.field_name = field_name
        self.message = message
        super().__init__(f"Validation failed for {entity_name}.{field_name}: {message}")


class Validator(Protocol):
    """Protocol for pluggable validators."""

    def validate(self, field_name: str, value: Any, data: dict[str, Any]) -> Any:
        """Validate and optionally transform a field value.

        Returns the (possibly transformed) value.
        Raises ValidationError if validation fails.
        """
        ...


class ValidatorRegistry:
    """Registry for per-entity validation hooks."""

    def __init__(self) -> None:
        self._validators: dict[str, list[Validator]] = {}

    def register(self, entity_name: str, validator: Validator) -> None:
        """Register a validator for an entity."""
        self._validators.setdefault(entity_name, []).append(validator)

    def run(
        self,
        entity_name: str,
        data: dict[str, Any],
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        """Run all registered validators for an entity against the data."""
        validators = self._validators.get(entity_name, [])
        for validator in validators:
            for field_name, value in list(data.items()):
                try:
                    result = validator.validate(field_name, value, data)
                    if result is not value:
                        if audit:
                            audit.record(
                                entity_name,
                                field_name,
                                CoercionAction.TYPE_CAST,
                                value,
                                result,
                                "custom validator transformation",
                            )
                        data[field_name] = result
                except ValidationError:
                    if audit:
                        audit.record(
                            entity_name,
                            field_name,
                            CoercionAction.VALIDATION_ERROR,
                            value,
                            None,
                            "custom validation failed",
                        )
                    raise
        return data
