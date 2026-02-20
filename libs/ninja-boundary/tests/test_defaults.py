"""Tests for the default resolver."""

from datetime import datetime

from ninja_boundary.audit import AuditLog, CoercionAction
from ninja_boundary.defaults import DefaultResolver
from ninja_core.schema.entity import FieldSchema, FieldType


def _field(name: str, field_type: FieldType, nullable: bool = False, default=None) -> FieldSchema:
    return FieldSchema(name=name, field_type=field_type, nullable=nullable, default=default)


class TestDefaultResolver:
    def test_missing_created_at_gets_datetime(self):
        resolver = DefaultResolver()
        audit = AuditLog()
        data: dict = {}
        field = _field("created_at", FieldType.DATETIME)
        resolver.resolve(data, field, "User", audit=audit)
        assert "created_at" in data
        assert isinstance(data["created_at"], datetime)
        assert len(audit) == 1
        assert audit.entries[0].action == CoercionAction.DEFAULT_APPLIED

    def test_missing_bool_gets_false(self):
        resolver = DefaultResolver()
        data: dict = {}
        field = _field("active", FieldType.BOOLEAN)
        resolver.resolve(data, field, "User")
        assert data["active"] is False

    def test_missing_int_gets_zero(self):
        resolver = DefaultResolver()
        data: dict = {}
        field = _field("count", FieldType.INTEGER)
        resolver.resolve(data, field, "User")
        assert data["count"] == 0

    def test_missing_string_gets_empty(self):
        resolver = DefaultResolver()
        data: dict = {}
        field = _field("name", FieldType.STRING)
        resolver.resolve(data, field, "User")
        assert data["name"] == ""

    def test_existing_field_not_overwritten(self):
        resolver = DefaultResolver()
        data = {"name": "Alice"}
        field = _field("name", FieldType.STRING)
        resolver.resolve(data, field, "User")
        assert data["name"] == "Alice"

    def test_nullable_field_stays_absent(self):
        resolver = DefaultResolver()
        data: dict = {}
        field = _field("middle_name", FieldType.STRING, nullable=True)
        resolver.resolve(data, field, "User")
        assert "middle_name" not in data

    def test_field_with_explicit_default(self):
        resolver = DefaultResolver()
        data: dict = {}
        field = _field("status", FieldType.STRING, default="active")
        resolver.resolve(data, field, "User")
        assert data["status"] == "active"

    def test_custom_defaults(self):
        resolver = DefaultResolver(custom_defaults={"role": "user"})
        data: dict = {}
        field = _field("role", FieldType.STRING)
        resolver.resolve(data, field, "User")
        assert data["role"] == "user"

    def test_entity_specific_custom_default(self):
        resolver = DefaultResolver(custom_defaults={"Admin.role": "admin", "role": "user"})
        data: dict = {}
        field = _field("role", FieldType.STRING)
        resolver.resolve(data, field, "Admin")
        assert data["role"] == "admin"

    def test_updated_at_gets_datetime(self):
        resolver = DefaultResolver()
        data: dict = {}
        field = _field("updated_at", FieldType.DATETIME)
        resolver.resolve(data, field, "User")
        assert isinstance(data["updated_at"], datetime)
