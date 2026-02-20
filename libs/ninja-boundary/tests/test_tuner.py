"""Tests for the strictness tuner."""

from ninja_boundary.audit import AuditLog, CoercionAction
from ninja_boundary.coercion import StrictnessLevel
from ninja_boundary.tuner import StrictnessTuner


class TestStrictnessTuner:
    def test_recommends_upgrade_over_threshold(self):
        audit = AuditLog()
        for i in range(15):
            audit.record("User", "age", CoercionAction.TYPE_CAST, str(i), i, "str to int")
        tuner = StrictnessTuner(threshold=10, current_level=StrictnessLevel.PERMISSIVE)
        recs = tuner.analyze(audit)
        assert len(recs) == 1
        assert recs[0].entity_name == "User"
        assert recs[0].field_name == "age"
        assert recs[0].recommended_level == StrictnessLevel.MODERATE
        assert recs[0].coercion_count == 15

    def test_no_recommendation_below_threshold(self):
        audit = AuditLog()
        for i in range(5):
            audit.record("User", "age", CoercionAction.TYPE_CAST, str(i), i, "cast")
        tuner = StrictnessTuner(threshold=10)
        assert len(tuner.analyze(audit)) == 0

    def test_moderate_to_strict(self):
        audit = AuditLog()
        for i in range(10):
            audit.record("User", "age", CoercionAction.TYPE_CAST, str(i), i, "cast")
        tuner = StrictnessTuner(threshold=10, current_level=StrictnessLevel.MODERATE)
        recs = tuner.analyze(audit)
        assert len(recs) == 1
        assert recs[0].recommended_level == StrictnessLevel.STRICT

    def test_strict_has_no_upgrade(self):
        audit = AuditLog()
        for i in range(20):
            audit.record("User", "age", CoercionAction.TYPE_CAST, str(i), i, "cast")
        tuner = StrictnessTuner(threshold=10, current_level=StrictnessLevel.STRICT)
        assert len(tuner.analyze(audit)) == 0

    def test_ignores_non_type_cast(self):
        audit = AuditLog()
        for i in range(20):
            audit.record("User", "age", CoercionAction.DEFAULT_APPLIED, None, 0, "default")
        tuner = StrictnessTuner(threshold=10)
        assert len(tuner.analyze(audit)) == 0

    def test_multiple_fields(self):
        audit = AuditLog()
        for i in range(12):
            audit.record("User", "age", CoercionAction.TYPE_CAST, str(i), i, "cast")
        for i in range(15):
            audit.record("User", "score", CoercionAction.TYPE_CAST, str(i), float(i), "cast")
        tuner = StrictnessTuner(threshold=10)
        recs = tuner.analyze(audit)
        assert len(recs) == 2
