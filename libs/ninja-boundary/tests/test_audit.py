"""Tests for the audit log."""

from ninja_boundary.audit import AuditLog, CoercionAction


class TestAuditLog:
    def test_record_and_retrieve(self):
        audit = AuditLog()
        entry = audit.record("User", "age", CoercionAction.TYPE_CAST, "123", 123, "str to int")
        assert len(audit) == 1
        assert entry.entity_name == "User"
        assert entry.field_name == "age"
        assert entry.before == "123"
        assert entry.after == 123
        assert entry.action == CoercionAction.TYPE_CAST

    def test_filter_by_entity(self):
        audit = AuditLog()
        audit.record("User", "age", CoercionAction.TYPE_CAST, "1", 1, "cast")
        audit.record("Product", "price", CoercionAction.TYPE_CAST, "9.99", 9.99, "cast")
        audit.record("User", "name", CoercionAction.DEFAULT_APPLIED, None, "", "default")
        assert len(audit.filter_by_entity("User")) == 2
        assert len(audit.filter_by_entity("Product")) == 1

    def test_filter_by_action(self):
        audit = AuditLog()
        audit.record("User", "age", CoercionAction.TYPE_CAST, "1", 1, "cast")
        audit.record("User", "name", CoercionAction.DEFAULT_APPLIED, None, "", "default")
        assert len(audit.filter_by_action(CoercionAction.TYPE_CAST)) == 1
        assert len(audit.filter_by_action(CoercionAction.DEFAULT_APPLIED)) == 1

    def test_summary(self):
        audit = AuditLog()
        audit.record("User", "a", CoercionAction.TYPE_CAST, "1", 1, "cast")
        audit.record("User", "b", CoercionAction.TYPE_CAST, "2", 2, "cast")
        audit.record("User", "c", CoercionAction.DEFAULT_APPLIED, None, "", "default")
        summary = audit.summary()
        assert summary["type_cast"] == 2
        assert summary["default_applied"] == 1

    def test_to_dict(self):
        audit = AuditLog()
        entry = audit.record("User", "age", CoercionAction.TYPE_CAST, "123", 123, "str to int")
        d = entry.to_dict()
        assert d["entity_name"] == "User"
        assert d["field_name"] == "age"
        assert d["action"] == "type_cast"
        assert "timestamp" in d

    def test_clear(self):
        audit = AuditLog()
        audit.record("User", "age", CoercionAction.TYPE_CAST, "1", 1, "cast")
        assert len(audit) == 1
        audit.clear()
        assert len(audit) == 0
