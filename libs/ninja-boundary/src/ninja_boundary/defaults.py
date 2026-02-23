"""Convention-based default resolver per field type."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ninja_core.schema.entity import FieldSchema, FieldType

from ninja_boundary.audit import AuditLog, CoercionAction

# Convention-based defaults keyed by FieldType
_FIELD_TYPE_DEFAULTS: dict[FieldType, Any] = {
    FieldType.STRING: "",
    FieldType.TEXT: "",
    FieldType.INTEGER: 0,
    FieldType.FLOAT: 0.0,
    FieldType.BOOLEAN: False,
    FieldType.JSON: {},
    FieldType.ARRAY: [],
}

# Fields whose name hints at a timestamp convention
_TIMESTAMP_FIELD_NAMES = {"created_at", "updated_at", "created", "updated", "timestamp"}


def _generate_default(field: FieldSchema) -> Any:
    """Generate a sensible default for a field based on its type and name."""
    # Check field-level explicit default first
    if field.default is not None:
        return field.default

    # Name-based conventions
    lower_name = field.name.lower()

    if lower_name in _TIMESTAMP_FIELD_NAMES and field.field_type in (FieldType.DATETIME, FieldType.STRING):
        return datetime.now(timezone.utc)

    if lower_name == "id" and field.field_type == FieldType.UUID:
        return str(uuid4())

    # Type-based defaults
    return _FIELD_TYPE_DEFAULTS.get(field.field_type)


class DefaultResolver:
    """Fills in missing fields with convention-based defaults."""

    def __init__(self, custom_defaults: dict[str, Any] | None = None) -> None:
        self._custom_defaults = custom_defaults or {}

    def resolve(
        self,
        data: dict[str, Any],
        field: FieldSchema,
        entity_name: str,
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        """If field is missing from data, apply a default value. Returns the (possibly mutated) data."""
        if field.name in data:
            return data

        # Nullable fields can stay None
        if field.nullable:
            return data

        # Check custom defaults
        custom_key = f"{entity_name}.{field.name}"
        if custom_key in self._custom_defaults:
            default = self._custom_defaults[custom_key]
        elif field.name in self._custom_defaults:
            default = self._custom_defaults[field.name]
        else:
            default = _generate_default(field)

        if default is not None:
            data[field.name] = default
            if audit:
                audit.record(
                    entity_name,
                    field.name,
                    CoercionAction.DEFAULT_APPLIED,
                    None,
                    default,
                    f"missing field, applied {field.field_type.value} default",
                )

        return data
