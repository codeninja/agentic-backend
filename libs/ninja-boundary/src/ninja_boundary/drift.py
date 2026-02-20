"""Schema drift detection — compare incoming data shape against EntitySchema expectations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ninja_core.schema.entity import EntitySchema

from ninja_boundary.audit import AuditLog, CoercionAction

logger = logging.getLogger("ninja_boundary.drift")


class DriftType(str, Enum):
    """Types of schema drift."""

    EXTRA_FIELD = "extra_field"  # Field in data but not in schema
    MISSING_FIELD = "missing_field"  # Field in schema but not in data
    TYPE_MISMATCH = "type_mismatch"  # Value type doesn't match schema


@dataclass(frozen=True)
class DriftEvent:
    """A single drift detection event."""

    entity_name: str
    drift_type: DriftType
    field_name: str
    detail: str


class DriftDetector:
    """Detects schema drift between incoming data and the EntitySchema."""

    def __init__(self, warn_on_extra: bool = True, warn_on_missing: bool = True) -> None:
        self.warn_on_extra = warn_on_extra
        self.warn_on_missing = warn_on_missing

    def detect(
        self,
        data: dict[str, Any],
        schema: EntitySchema,
        audit: AuditLog | None = None,
    ) -> list[DriftEvent]:
        """Compare data keys against schema fields and return drift events."""
        events: list[DriftEvent] = []
        schema_fields = {f.name for f in schema.fields}
        data_keys = set(data.keys())

        if self.warn_on_extra:
            for key in sorted(data_keys - schema_fields):
                event = DriftEvent(
                    entity_name=schema.name,
                    drift_type=DriftType.EXTRA_FIELD,
                    field_name=key,
                    detail=f"unexpected field '{key}' not in schema",
                )
                events.append(event)
                logger.warning("Drift: %s — %s", schema.name, event.detail)
                if audit:
                    audit.record(
                        schema.name,
                        key,
                        CoercionAction.DRIFT_DETECTED,
                        data.get(key),
                        None,
                        event.detail,
                    )

        if self.warn_on_missing:
            for field_name in sorted(schema_fields - data_keys):
                field_schema = next(f for f in schema.fields if f.name == field_name)
                if not field_schema.nullable and field_schema.default is None:
                    event = DriftEvent(
                        entity_name=schema.name,
                        drift_type=DriftType.MISSING_FIELD,
                        field_name=field_name,
                        detail=f"required field '{field_name}' missing from data",
                    )
                    events.append(event)
                    logger.warning("Drift: %s — %s", schema.name, event.detail)

        return events
