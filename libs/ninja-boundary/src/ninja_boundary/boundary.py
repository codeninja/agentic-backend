"""Main entry point — BoundaryProcessor that chains coercion -> defaults -> validation -> drift check."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ninja_core.schema.entity import EntitySchema, FieldSchema

from ninja_boundary.audit import AuditLog, CoercionAction
from ninja_boundary.coercion import CoercionEngine, StrictnessLevel
from ninja_boundary.defaults import DefaultResolver
from ninja_boundary.drift import DriftDetector, DriftEvent
from ninja_boundary.validators import ValidationError, ValidatorRegistry


@dataclass
class BoundaryResult:
    """Result of processing data through the boundary layer."""

    data: dict[str, Any]
    audit: AuditLog
    drift_events: list[DriftEvent] = field(default_factory=list)


class BoundaryProcessor:
    """Chains coercion -> defaults -> validation -> drift check.

    This is the main entry point for the boundary layer.
    """

    def __init__(
        self,
        strictness: StrictnessLevel = StrictnessLevel.PERMISSIVE,
        custom_defaults: dict[str, Any] | None = None,
        validator_registry: ValidatorRegistry | None = None,
        warn_on_extra_fields: bool = True,
        warn_on_missing_fields: bool = True,
    ) -> None:
        self._coercion = CoercionEngine(strictness=strictness)
        self._defaults = DefaultResolver(custom_defaults=custom_defaults)
        self._drift = DriftDetector(
            warn_on_extra=warn_on_extra_fields,
            warn_on_missing=warn_on_missing_fields,
        )
        self._validators = validator_registry or ValidatorRegistry()

    def process(self, data: dict[str, Any], schema: EntitySchema) -> BoundaryResult:
        """Process raw data through the full boundary pipeline.

        Pipeline:
        1. Coerce field values to expected types
        2. Apply defaults for missing fields
        3. Validate field constraints (pattern, length, range, enum)
        4. Run custom validators
        5. Detect schema drift
        """
        audit = AuditLog()
        result = dict(data)  # shallow copy

        # 1. Coerce existing fields
        schema_field_map = {f.name: f for f in schema.fields}
        for key in list(result.keys()):
            if key in schema_field_map:
                fs = schema_field_map[key]
                result[key] = self._coercion.coerce(
                    value=result[key],
                    target_type=fs.field_type,
                    field_name=fs.name,
                    entity_name=schema.name,
                    nullable=fs.nullable,
                    audit=audit,
                )

        # 2. Apply defaults for missing fields
        for fs in schema.fields:
            self._defaults.resolve(result, fs, schema.name, audit=audit)

        # 3. Validate field constraints (pattern, length, range, enum)
        for fs in schema.fields:
            if fs.name in result and result[fs.name] is not None:
                _validate_field_constraints(
                    result[fs.name],
                    fs,
                    schema.name,
                    audit,
                )

        # 4. Run custom validators
        self._validators.run(schema.name, result, audit=audit)

        # 5. Detect drift
        drift_events = self._drift.detect(result, schema, audit=audit)

        return BoundaryResult(data=result, audit=audit, drift_events=drift_events)


def _validate_field_constraints(
    value: Any,
    field_schema: FieldSchema,
    entity_name: str,
    audit: AuditLog,
) -> None:
    """Apply field-level constraints from the schema to a runtime value.

    Validates pattern, min_length, max_length, ge, le, and enum_values
    constraints.  Raises :class:`ValidationError` on mismatch.
    """
    constraints = field_schema.constraints
    if constraints is None:
        return

    field_name = field_schema.name

    # Pattern constraint — only applies to string values
    if constraints.pattern is not None and isinstance(value, str):
        compiled = re.compile(constraints.pattern)
        if not compiled.fullmatch(value):
            audit.record(
                entity_name,
                field_name,
                CoercionAction.VALIDATION_ERROR,
                value,
                None,
                f"value does not match pattern '{constraints.pattern}'",
            )
            raise ValidationError(
                entity_name,
                field_name,
                f"Value {value!r} does not match pattern '{constraints.pattern}'",
            )

    # String length constraints
    if constraints.min_length is not None and isinstance(value, str):
        if len(value) < constraints.min_length:
            audit.record(
                entity_name,
                field_name,
                CoercionAction.VALIDATION_ERROR,
                value,
                None,
                f"length {len(value)} < min_length {constraints.min_length}",
            )
            raise ValidationError(
                entity_name,
                field_name,
                f"Value length {len(value)} is less than min_length {constraints.min_length}",
            )

    if constraints.max_length is not None and isinstance(value, str):
        if len(value) > constraints.max_length:
            audit.record(
                entity_name,
                field_name,
                CoercionAction.VALIDATION_ERROR,
                value,
                None,
                f"length {len(value)} > max_length {constraints.max_length}",
            )
            raise ValidationError(
                entity_name,
                field_name,
                f"Value length {len(value)} exceeds max_length {constraints.max_length}",
            )

    # Numeric range constraints
    if constraints.ge is not None and isinstance(value, (int, float)):
        if value < constraints.ge:
            audit.record(
                entity_name,
                field_name,
                CoercionAction.VALIDATION_ERROR,
                value,
                None,
                f"value {value} < ge {constraints.ge}",
            )
            raise ValidationError(
                entity_name,
                field_name,
                f"Value {value} is less than minimum {constraints.ge}",
            )

    if constraints.le is not None and isinstance(value, (int, float)):
        if value > constraints.le:
            audit.record(
                entity_name,
                field_name,
                CoercionAction.VALIDATION_ERROR,
                value,
                None,
                f"value {value} > le {constraints.le}",
            )
            raise ValidationError(
                entity_name,
                field_name,
                f"Value {value} exceeds maximum {constraints.le}",
            )

    # Enum constraints
    if constraints.enum_values is not None:
        if value not in constraints.enum_values:
            audit.record(
                entity_name,
                field_name,
                CoercionAction.VALIDATION_ERROR,
                value,
                None,
                f"value {value!r} not in enum_values {constraints.enum_values}",
            )
            raise ValidationError(
                entity_name,
                field_name,
                f"Value {value!r} is not one of the allowed values: {constraints.enum_values}",
            )
