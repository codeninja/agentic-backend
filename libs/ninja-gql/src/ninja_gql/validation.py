"""Input validation for JSON scalar mutations against ASD entity definitions.

Validates ``input`` and ``patch`` payloads passed to CRUD resolvers before
they reach the persistence layer, preventing mass assignment and enforcing
field-level type and constraint checks.
"""

from __future__ import annotations

import re
from typing import Any

from ninja_core.schema.entity import EntitySchema, FieldType


# ---------------------------------------------------------------------------
# Field-type validators
# ---------------------------------------------------------------------------

_STRING_TYPES = frozenset({FieldType.STRING, FieldType.TEXT, FieldType.UUID, FieldType.ENUM, FieldType.BINARY})
_NUMERIC_INT_TYPES = frozenset({FieldType.INTEGER})
_NUMERIC_FLOAT_TYPES = frozenset({FieldType.FLOAT})


def _check_field_type(field_name: str, value: Any, field_type: FieldType) -> str | None:
    """Validate that *value* is compatible with *field_type*.

    Returns an error message string on failure, or ``None`` on success.
    """
    if value is None:
        return None  # Nullability is checked separately

    if field_type in _STRING_TYPES:
        if not isinstance(value, str):
            return f"Field '{field_name}': expected string, got {type(value).__name__}"

    elif field_type in _NUMERIC_INT_TYPES:
        if not isinstance(value, int) or isinstance(value, bool):
            return f"Field '{field_name}': expected integer, got {type(value).__name__}"

    elif field_type in _NUMERIC_FLOAT_TYPES:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"Field '{field_name}': expected number, got {type(value).__name__}"

    elif field_type == FieldType.BOOLEAN:
        if not isinstance(value, bool):
            return f"Field '{field_name}': expected boolean, got {type(value).__name__}"

    elif field_type == FieldType.ARRAY:
        if not isinstance(value, list):
            return f"Field '{field_name}': expected array, got {type(value).__name__}"

    elif field_type in (FieldType.DATETIME, FieldType.DATE):
        if not isinstance(value, str):
            return f"Field '{field_name}': expected ISO date string, got {type(value).__name__}"

    elif field_type == FieldType.JSON:
        pass  # Any JSON value is acceptable

    return None


def _check_constraints(field_name: str, value: Any, entity_field: Any) -> list[str]:
    """Validate field constraints (length, range, pattern, enum).

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    constraints = entity_field.constraints
    if constraints is None or value is None:
        return errors

    # String length constraints
    if isinstance(value, str):
        if constraints.min_length is not None and len(value) < constraints.min_length:
            errors.append(
                f"Field '{field_name}': length {len(value)} is below "
                f"minimum {constraints.min_length}"
            )
        if constraints.max_length is not None and len(value) > constraints.max_length:
            errors.append(
                f"Field '{field_name}': length {len(value)} exceeds "
                f"maximum {constraints.max_length}"
            )
        if constraints.pattern is not None:
            if not re.fullmatch(constraints.pattern, value):
                errors.append(
                    f"Field '{field_name}': value does not match "
                    f"pattern '{constraints.pattern}'"
                )

    # Numeric range constraints
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if constraints.ge is not None and value < constraints.ge:
            errors.append(
                f"Field '{field_name}': value {value} is below "
                f"minimum {constraints.ge}"
            )
        if constraints.le is not None and value > constraints.le:
            errors.append(
                f"Field '{field_name}': value {value} exceeds "
                f"maximum {constraints.le}"
            )

    # Enum validation
    if constraints.enum_values is not None and isinstance(value, str):
        if value not in constraints.enum_values:
            errors.append(
                f"Field '{field_name}': value '{value}' is not one of "
                f"the allowed values: {constraints.enum_values}"
            )

    return errors


# ---------------------------------------------------------------------------
# Public validation API
# ---------------------------------------------------------------------------


class InputValidationError(Exception):
    """Raised when JSON scalar input fails validation against the ASD.

    Attributes
    ----------
    errors : list[str]
        Individual validation error messages.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Input validation failed: {'; '.join(errors)}")


def validate_create_input(entity: EntitySchema, data: dict[str, Any]) -> dict[str, Any]:
    """Validate a ``create`` mutation payload against the entity schema.

    Parameters
    ----------
    entity:
        The ASD entity definition.
    data:
        The JSON input dictionary from the GraphQL mutation.

    Returns
    -------
    dict[str, Any]
        The validated (and cleaned) data dictionary.

    Raises
    ------
    InputValidationError
        If the input contains unknown fields, type mismatches, or
        constraint violations.
    """
    if not isinstance(data, dict):
        raise InputValidationError(["Input must be a JSON object"])

    errors: list[str] = []
    field_map = {f.name: f for f in entity.fields}
    allowed_names = set(field_map.keys())

    # Reject unknown fields (mass assignment protection)
    unknown = set(data.keys()) - allowed_names
    if unknown:
        errors.append(f"Unknown fields: {sorted(unknown)}")

    # Check required fields (non-nullable, non-primary-key)
    for f in entity.fields:
        if f.primary_key:
            continue  # PKs are auto-generated
        if not f.nullable and f.name not in data:
            errors.append(f"Required field '{f.name}' is missing")

    # Validate each provided field
    for key, value in data.items():
        field = field_map.get(key)
        if field is None:
            continue  # Already reported as unknown

        type_err = _check_field_type(key, value, field.field_type)
        if type_err:
            errors.append(type_err)
        else:
            errors.extend(_check_constraints(key, value, field))

    if errors:
        raise InputValidationError(errors)

    return data


def validate_update_input(entity: EntitySchema, data: dict[str, Any]) -> dict[str, Any]:
    """Validate an ``update`` mutation patch payload against the entity schema.

    Similar to :func:`validate_create_input` but all fields are optional
    (patch semantics) and primary key fields are excluded from the patch.

    Parameters
    ----------
    entity:
        The ASD entity definition.
    data:
        The JSON patch dictionary from the GraphQL mutation.

    Returns
    -------
    dict[str, Any]
        The validated patch dictionary.

    Raises
    ------
    InputValidationError
        If the patch contains unknown fields, type mismatches, or
        constraint violations.
    """
    if not isinstance(data, dict):
        raise InputValidationError(["Patch must be a JSON object"])

    errors: list[str] = []
    field_map = {f.name: f for f in entity.fields}
    allowed_names = set(field_map.keys())

    # Reject unknown fields
    unknown = set(data.keys()) - allowed_names
    if unknown:
        errors.append(f"Unknown fields: {sorted(unknown)}")

    # Reject attempts to modify primary key via patch
    for f in entity.fields:
        if f.primary_key and f.name in data:
            errors.append(f"Cannot modify primary key field '{f.name}' via patch")

    # Validate each provided field
    for key, value in data.items():
        field = field_map.get(key)
        if field is None:
            continue

        if field.primary_key:
            continue  # Already reported

        type_err = _check_field_type(key, value, field.field_type)
        if type_err:
            errors.append(type_err)
        else:
            errors.extend(_check_constraints(key, value, field))

    if errors:
        raise InputValidationError(errors)

    return data
