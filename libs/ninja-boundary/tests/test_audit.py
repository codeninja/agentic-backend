"""Tests for the audit log."""

import logging

from ninja_boundary.audit import AuditLog, CoercionAction, _REDACTED


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


# --- Tests for sensitive field redaction in audit logging (issue #56) ---


class TestAuditLogRedaction:
    def test_sensitive_field_password_redacted_in_log(self, caplog):
        audit = AuditLog()
        with caplog.at_level(logging.DEBUG, logger="ninja_boundary.audit"):
            audit.record("User", "password", CoercionAction.TYPE_CAST, "plain123", "hashed", "hash")
        assert _REDACTED in caplog.text
        assert "plain123" not in caplog.text
        assert "hashed" not in caplog.text

    def test_sensitive_field_api_key_redacted_in_log(self, caplog):
        audit = AuditLog()
        with caplog.at_level(logging.DEBUG, logger="ninja_boundary.audit"):
            audit.record("Service", "api_key", CoercionAction.TYPE_CAST, "key-abc", "key-xyz", "rotate")
        assert _REDACTED in caplog.text
        assert "key-abc" not in caplog.text

    def test_sensitive_field_token_redacted_in_log(self, caplog):
        audit = AuditLog()
        with caplog.at_level(logging.DEBUG, logger="ninja_boundary.audit"):
            audit.record("Session", "access_token", CoercionAction.TYPE_CAST, "tok-old", "tok-new", "refresh")
        assert _REDACTED in caplog.text
        assert "tok-old" not in caplog.text

    def test_sensitive_field_secret_redacted_in_log(self, caplog):
        audit = AuditLog()
        with caplog.at_level(logging.DEBUG, logger="ninja_boundary.audit"):
            audit.record("Config", "client_secret", CoercionAction.TYPE_CAST, "s1", "s2", "rotate")
        assert _REDACTED in caplog.text
        assert "s1" not in caplog.text

    def test_non_sensitive_field_not_redacted_in_log(self, caplog):
        audit = AuditLog()
        with caplog.at_level(logging.DEBUG, logger="ninja_boundary.audit"):
            audit.record("User", "age", CoercionAction.TYPE_CAST, "25", 25, "str to int")
        assert "'25'" in caplog.text
        assert _REDACTED not in caplog.text

    def test_sensitive_field_values_still_stored_in_entry(self):
        """Redaction only applies to logging — the AuditEntry itself keeps original values."""
        audit = AuditLog()
        entry = audit.record("User", "password", CoercionAction.TYPE_CAST, "plain", "hashed", "hash")
        assert entry.before == "plain"
        assert entry.after == "hashed"
