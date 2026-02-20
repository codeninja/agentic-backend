"""Tests for the coercion engine."""

from datetime import date, datetime, timezone

import pytest
from ninja_boundary.audit import AuditLog, CoercionAction
from ninja_boundary.coercion import CoercionEngine, CoercionError, StrictnessLevel
from ninja_core.schema.entity import FieldType


@pytest.fixture
def engine():
    return CoercionEngine(StrictnessLevel.PERMISSIVE)


@pytest.fixture
def audit():
    return AuditLog()


class TestIntegerCoercion:
    def test_string_to_int(self, engine, audit):
        result = engine.coerce("123", FieldType.INTEGER, "age", "User", audit=audit)
        assert result == 123
        assert isinstance(result, int)
        assert len(audit) == 1
        assert audit.entries[0].action == CoercionAction.TYPE_CAST

    def test_float_string_to_int(self, engine):
        assert engine.coerce("123.0", FieldType.INTEGER, "age", "User") == 123

    def test_float_to_int(self, engine):
        assert engine.coerce(123.0, FieldType.INTEGER, "age", "User") == 123

    def test_int_passthrough(self, engine, audit):
        assert engine.coerce(42, FieldType.INTEGER, "age", "User", audit=audit) == 42
        assert len(audit) == 0  # No coercion needed

    def test_bool_to_int_permissive(self, engine):
        assert engine.coerce(True, FieldType.INTEGER, "flag", "User") == 1

    def test_strict_rejects_string(self):
        engine = CoercionEngine(StrictnessLevel.STRICT)
        with pytest.raises(CoercionError):
            engine.coerce("123", FieldType.INTEGER, "age", "User")

    def test_moderate_rejects_lossy_float(self):
        engine = CoercionEngine(StrictnessLevel.MODERATE)
        with pytest.raises(CoercionError):
            engine.coerce(12.7, FieldType.INTEGER, "age", "User")

    def test_invalid_string_raises(self, engine):
        with pytest.raises(CoercionError):
            engine.coerce("abc", FieldType.INTEGER, "age", "User")


class TestStringCoercion:
    def test_int_to_string(self, engine, audit):
        result = engine.coerce(123, FieldType.STRING, "name", "User", audit=audit)
        assert result == "123"
        assert len(audit) == 1

    def test_string_passthrough(self, engine, audit):
        result = engine.coerce("hello", FieldType.STRING, "name", "User", audit=audit)
        assert result == "hello"
        assert len(audit) == 0

    def test_strict_rejects_int(self):
        engine = CoercionEngine(StrictnessLevel.STRICT)
        with pytest.raises(CoercionError):
            engine.coerce(123, FieldType.STRING, "name", "User")


class TestBooleanCoercion:
    def test_string_true_variants(self, engine):
        for val in ["true", "True", "1", "yes", "on", "t", "y"]:
            assert engine.coerce(val, FieldType.BOOLEAN, "active", "User") is True

    def test_string_false_variants(self, engine):
        for val in ["false", "False", "0", "no", "off", "f", "n"]:
            assert engine.coerce(val, FieldType.BOOLEAN, "active", "User") is False

    def test_int_to_bool(self, engine):
        assert engine.coerce(1, FieldType.BOOLEAN, "active", "User") is True
        assert engine.coerce(0, FieldType.BOOLEAN, "active", "User") is False

    def test_ambiguous_string_raises(self, engine):
        with pytest.raises(CoercionError):
            engine.coerce("maybe", FieldType.BOOLEAN, "active", "User")

    def test_bool_passthrough(self, engine, audit):
        assert engine.coerce(True, FieldType.BOOLEAN, "active", "User", audit=audit) is True
        assert len(audit) == 0


class TestDatetimeCoercion:
    def test_iso_string(self, engine, audit):
        result = engine.coerce("2024-01-15T10:30:00", FieldType.DATETIME, "created_at", "User", audit=audit)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert len(audit) == 1

    def test_iso_with_timezone(self, engine):
        result = engine.coerce("2024-01-15T10:30:00Z", FieldType.DATETIME, "created_at", "User")
        assert isinstance(result, datetime)

    def test_date_string(self, engine):
        result = engine.coerce("2024-01-15", FieldType.DATETIME, "created_at", "User")
        assert isinstance(result, datetime)

    def test_unix_timestamp(self, engine):
        result = engine.coerce(1705312200, FieldType.DATETIME, "created_at", "User")
        assert isinstance(result, datetime)

    def test_date_to_datetime(self, engine):
        d = date(2024, 1, 15)
        result = engine.coerce(d, FieldType.DATETIME, "created_at", "User")
        assert isinstance(result, datetime)

    def test_datetime_passthrough(self, engine, audit):
        dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = engine.coerce(dt, FieldType.DATETIME, "created_at", "User", audit=audit)
        assert result is dt
        assert len(audit) == 0

    def test_invalid_string_raises(self, engine):
        with pytest.raises(CoercionError):
            engine.coerce("not-a-date", FieldType.DATETIME, "created_at", "User")


class TestDateCoercion:
    def test_string_to_date(self, engine):
        result = engine.coerce("2024-01-15", FieldType.DATE, "birth_date", "User")
        assert isinstance(result, date)
        assert result == date(2024, 1, 15)

    def test_datetime_to_date(self, engine):
        dt = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        result = engine.coerce(dt, FieldType.DATE, "birth_date", "User")
        assert result == date(2024, 1, 15)


class TestFloatCoercion:
    def test_string_to_float(self, engine):
        assert engine.coerce("3.14", FieldType.FLOAT, "price", "Product") == 3.14

    def test_int_to_float(self, engine):
        result = engine.coerce(42, FieldType.FLOAT, "price", "Product")
        assert result == 42.0
        assert isinstance(result, float)


class TestUUIDCoercion:
    def test_valid_uuid_string(self, engine):
        val = "550e8400-e29b-41d4-a716-446655440000"
        result = engine.coerce(val, FieldType.UUID, "id", "User")
        assert result == val

    def test_invalid_uuid_raises(self, engine):
        with pytest.raises(CoercionError):
            engine.coerce("not-a-uuid", FieldType.UUID, "id", "User")


class TestNullHandling:
    def test_none_passthrough(self, engine):
        assert engine.coerce(None, FieldType.INTEGER, "age", "User") is None

    def test_empty_string_to_null_for_nullable(self, engine, audit):
        result = engine.coerce("", FieldType.INTEGER, "age", "User", nullable=True, audit=audit)
        assert result is None
        assert len(audit) == 1
        assert audit.entries[0].action == CoercionAction.NULL_COERCION

    def test_empty_string_stays_for_string_type(self, engine, audit):
        result = engine.coerce("", FieldType.STRING, "name", "User", nullable=True, audit=audit)
        assert result == ""
        assert len(audit) == 0
