"""Tests for schema drift detection."""

from ninja_boundary.audit import AuditLog, CoercionAction
from ninja_boundary.drift import DriftDetector, DriftType
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine


def _user_schema() -> EntitySchema:
    return EntitySchema(
        name="User",
        storage_engine=StorageEngine.MONGO,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="age", field_type=FieldType.INTEGER),
            FieldSchema(name="email", field_type=FieldType.STRING, nullable=True),
        ],
    )


class TestDriftDetector:
    def test_extra_field_detected(self):
        detector = DriftDetector()
        audit = AuditLog()
        data = {"id": "abc", "name": "Alice", "age": 30, "email": "a@b.com", "phone": "555-1234"}
        events = detector.detect(data, _user_schema(), audit=audit)
        extra = [e for e in events if e.drift_type == DriftType.EXTRA_FIELD]
        assert len(extra) == 1
        assert extra[0].field_name == "phone"
        # Drift should also be in audit
        drift_audits = audit.filter_by_action(CoercionAction.DRIFT_DETECTED)
        assert len(drift_audits) == 1

    def test_missing_required_field_detected(self):
        detector = DriftDetector()
        data = {"id": "abc", "name": "Alice"}
        events = detector.detect(data, _user_schema())
        missing = [e for e in events if e.drift_type == DriftType.MISSING_FIELD]
        assert len(missing) == 1  # age is required; email is nullable
        assert missing[0].field_name == "age"

    def test_no_drift_when_data_matches(self):
        detector = DriftDetector()
        data = {"id": "abc", "name": "Alice", "age": 30, "email": "a@b.com"}
        events = detector.detect(data, _user_schema())
        assert len(events) == 0

    def test_extra_field_warning_disabled(self):
        detector = DriftDetector(warn_on_extra=False)
        data = {"id": "abc", "name": "Alice", "age": 30, "phone": "555"}
        events = detector.detect(data, _user_schema())
        extra = [e for e in events if e.drift_type == DriftType.EXTRA_FIELD]
        assert len(extra) == 0

    def test_missing_field_warning_disabled(self):
        detector = DriftDetector(warn_on_missing=False)
        data = {"id": "abc"}
        events = detector.detect(data, _user_schema())
        missing = [e for e in events if e.drift_type == DriftType.MISSING_FIELD]
        assert len(missing) == 0
