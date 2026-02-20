"""Progressive strictness — analyze coercion logs and recommend stricter rules."""

from __future__ import annotations

from dataclasses import dataclass

from ninja_boundary.audit import AuditLog, CoercionAction
from ninja_boundary.coercion import StrictnessLevel


@dataclass(frozen=True)
class StrictnessRecommendation:
    """A recommendation to tighten strictness for a specific field."""

    entity_name: str
    field_name: str
    current_level: StrictnessLevel
    recommended_level: StrictnessLevel
    reason: str
    coercion_count: int


class StrictnessTuner:
    """Analyzes coercion audit logs and recommends stricter rules."""

    def __init__(
        self,
        threshold: int = 10,
        current_level: StrictnessLevel = StrictnessLevel.PERMISSIVE,
    ) -> None:
        self.threshold = threshold
        self.current_level = current_level

    def analyze(self, audit: AuditLog) -> list[StrictnessRecommendation]:
        """Analyze the audit log and produce recommendations.

        If a field has been coerced more than `threshold` times,
        recommend tightening strictness.
        """
        recommendations: list[StrictnessRecommendation] = []
        type_cast_entries = audit.filter_by_action(CoercionAction.TYPE_CAST)

        # Group by (entity, field)
        field_counts: dict[tuple[str, str], int] = {}
        for entry in type_cast_entries:
            key = (entry.entity_name, entry.field_name)
            field_counts[key] = field_counts.get(key, 0) + 1

        next_level = _NEXT_LEVEL.get(self.current_level)
        if next_level is None:
            return recommendations

        for (entity, field), count in sorted(field_counts.items()):
            if count >= self.threshold:
                recommendations.append(
                    StrictnessRecommendation(
                        entity_name=entity,
                        field_name=field,
                        current_level=self.current_level,
                        recommended_level=next_level,
                        reason=f"field coerced {count} times (threshold: {self.threshold})",
                        coercion_count=count,
                    )
                )

        return recommendations


_NEXT_LEVEL: dict[StrictnessLevel, StrictnessLevel] = {
    StrictnessLevel.PERMISSIVE: StrictnessLevel.MODERATE,
    StrictnessLevel.MODERATE: StrictnessLevel.STRICT,
}
