"""Main entry point — BoundaryProcessor that chains coercion -> defaults -> validation -> drift check."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ninja_core.schema.entity import EntitySchema

from ninja_boundary.audit import AuditLog
from ninja_boundary.coercion import CoercionEngine, StrictnessLevel
from ninja_boundary.defaults import DefaultResolver
from ninja_boundary.drift import DriftDetector, DriftEvent
from ninja_boundary.validators import ValidatorRegistry


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
        3. Run custom validators
        4. Detect schema drift
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

        # 3. Run custom validators
        self._validators.run(schema.name, result, audit=audit)

        # 4. Detect drift
        drift_events = self._drift.detect(result, schema, audit=audit)

        return BoundaryResult(data=result, audit=audit, drift_events=drift_events)
