"""Structured coercion audit logger — logs every transformation with before/after values."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("ninja_boundary.audit")


class CoercionAction(str, Enum):
    """Types of coercion actions."""

    TYPE_CAST = "type_cast"
    DEFAULT_APPLIED = "default_applied"
    NULL_COERCION = "null_coercion"
    VALIDATION_ERROR = "validation_error"
    DRIFT_DETECTED = "drift_detected"


@dataclass(frozen=True)
class AuditEntry:
    """A single coercion audit record."""

    entity_name: str
    field_name: str
    action: CoercionAction
    before: Any
    after: Any
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_name": self.entity_name,
            "field_name": self.field_name,
            "action": self.action.value,
            "before": repr(self.before),
            "after": repr(self.after),
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


class AuditLog:
    """Accumulates audit entries for a processing run."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        entity_name: str,
        field_name: str,
        action: CoercionAction,
        before: Any,
        after: Any,
        reason: str,
    ) -> AuditEntry:
        entry = AuditEntry(
            entity_name=entity_name,
            field_name=field_name,
            action=action,
            before=before,
            after=after,
            reason=reason,
        )
        self._entries.append(entry)
        logger.debug("Coercion: %s.%s %s %r -> %r (%s)", entity_name, field_name, action.value, before, after, reason)
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def filter_by_entity(self, entity_name: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.entity_name == entity_name]

    def filter_by_action(self, action: CoercionAction) -> list[AuditEntry]:
        return [e for e in self._entries if e.action == action]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True

    def summary(self) -> dict[str, int]:
        """Return counts by action type."""
        counts: dict[str, int] = {}
        for entry in self._entries:
            counts[entry.action.value] = counts.get(entry.action.value, 0) + 1
        return counts
