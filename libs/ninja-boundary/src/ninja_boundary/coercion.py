"""Type-aware casting engine with configurable strictness levels."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from ninja_core.schema.entity import FieldType

from ninja_boundary.audit import AuditLog, CoercionAction


class StrictnessLevel(str, Enum):
    """How aggressively the coercion engine casts values."""

    PERMISSIVE = "permissive"  # Cast everything possible
    MODERATE = "moderate"  # Cast obvious cases, reject ambiguous
    STRICT = "strict"  # Only accept exact types


class CoercionError(Exception):
    """Raised when a value cannot be coerced to the target type."""

    def __init__(self, field_name: str, value: Any, target_type: FieldType, reason: str) -> None:
        self.field_name = field_name
        self.value = value
        self.target_type = target_type
        self.reason = reason
        super().__init__(f"Cannot coerce {field_name}={value!r} to {target_type.value}: {reason}")


_TRUTHY = {"true", "1", "yes", "on", "t", "y"}
_FALSY = {"false", "0", "no", "off", "f", "n"}

_TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
]


class CoercionEngine:
    """Type-aware casting with configurable strictness."""

    def __init__(self, strictness: StrictnessLevel = StrictnessLevel.PERMISSIVE) -> None:
        self.strictness = strictness

    def coerce(
        self,
        value: Any,
        target_type: FieldType,
        field_name: str,
        entity_name: str,
        nullable: bool = False,
        audit: AuditLog | None = None,
    ) -> Any:
        """Coerce a value to the target FieldType.

        Returns the coerced value. Logs to audit when a transformation occurs.
        """
        if value is None:
            return None

        # Handle empty string -> None for nullable fields
        if isinstance(value, str) and value.strip() == "" and nullable and target_type != FieldType.STRING:
            if audit:
                audit.record(entity_name, field_name, CoercionAction.NULL_COERCION, value, None, "empty string to null")
            return None

        coercer = _COERCERS.get(target_type)
        if coercer is None:
            return value

        try:
            result = coercer(value, self.strictness)
        except (ValueError, TypeError, OverflowError) as exc:
            raise CoercionError(field_name, value, target_type, str(exc)) from exc

        if result is not value and result != value:
            if audit:
                audit.record(
                    entity_name,
                    field_name,
                    CoercionAction.TYPE_CAST,
                    value,
                    result,
                    f"coerced {type(value).__name__} to {target_type.value}",
                )

        return result


def _coerce_string(value: Any, strictness: StrictnessLevel) -> str:
    if isinstance(value, str):
        return value
    if strictness == StrictnessLevel.STRICT:
        raise ValueError(f"expected str, got {type(value).__name__}")
    return str(value)


def _coerce_integer(value: Any, strictness: StrictnessLevel) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, bool):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("bool is not int in strict mode")
        return int(value)
    if isinstance(value, float):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("float is not int in strict mode")
        if value != int(value):
            if strictness == StrictnessLevel.MODERATE:
                raise ValueError(f"lossy float-to-int: {value}")
        return int(value)
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected int, got str '{value}'")
        stripped = value.strip()
        # Handle float strings like "123.0"
        if "." in stripped:
            f = float(stripped)
            if strictness == StrictnessLevel.MODERATE and f != int(f):
                raise ValueError(f"lossy str-float-to-int: {stripped}")
            return int(f)
        return int(stripped)
    raise ValueError(f"cannot coerce {type(value).__name__} to int")


def _coerce_float(value: Any, strictness: StrictnessLevel) -> float:
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected float, got str '{value}'")
        return float(value.strip())
    raise ValueError(f"cannot coerce {type(value).__name__} to float")


def _coerce_boolean(value: Any, strictness: StrictnessLevel) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected bool, got int {value}")
        return bool(value)
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected bool, got str '{value}'")
        lower = value.strip().lower()
        if lower in _TRUTHY:
            return True
        if lower in _FALSY:
            return False
        raise ValueError(f"ambiguous boolean string: '{value}'")
    raise ValueError(f"cannot coerce {type(value).__name__} to bool")


def _coerce_datetime(value: Any, strictness: StrictnessLevel) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("date is not datetime in strict mode")
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected datetime, got {type(value).__name__}")
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected datetime, got str '{value}'")
        for fmt in _TIMESTAMP_FORMATS:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        raise ValueError(f"cannot parse datetime from '{value}'")
    raise ValueError(f"cannot coerce {type(value).__name__} to datetime")


def _coerce_date(value: Any, strictness: StrictnessLevel) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected date, got str '{value}'")
        # Try ISO date first
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
        # Try parsing as datetime and extracting date
        dt = _coerce_datetime(value, StrictnessLevel.PERMISSIVE)
        return dt.date()
    raise ValueError(f"cannot coerce {type(value).__name__} to date")


def _coerce_uuid(value: Any, strictness: StrictnessLevel) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        # Validate it's a proper UUID
        uuid.UUID(value.strip())
        return value.strip()
    raise ValueError(f"cannot coerce {type(value).__name__} to uuid")


def _coerce_text(value: Any, strictness: StrictnessLevel) -> str:
    return _coerce_string(value, strictness)


def _coerce_json(value: Any, strictness: StrictnessLevel) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("expected dict or list, got str")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON string: {exc}") from exc
        if not isinstance(parsed, (dict, list)):
            raise ValueError(f"JSON must parse to dict or list, got {type(parsed).__name__}")
        return parsed
    raise ValueError(f"cannot coerce {type(value).__name__} to json")


def _coerce_array(value: Any, strictness: StrictnessLevel) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("expected list, got tuple")
        return list(value)
    if isinstance(value, set | frozenset):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError(f"expected list, got {type(value).__name__}")
        return sorted(value, key=str)
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("expected list, got str")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON array string: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"expected JSON array, got {type(parsed).__name__}")
        return parsed
    raise ValueError(f"cannot coerce {type(value).__name__} to array")


def _coerce_binary(value: Any, strictness: StrictnessLevel) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("expected bytes, got bytearray")
        return bytes(value)
    if isinstance(value, str):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("expected bytes, got str")
        try:
            return base64.b64decode(value, validate=True)
        except Exception:
            pass
        try:
            if value.startswith(("0x", "0X")):
                return bytes.fromhex(value[2:])
            return bytes.fromhex(value)
        except ValueError:
            pass
        raise ValueError("cannot decode str to bytes (expected base64 or hex)")
    raise ValueError(f"cannot coerce {type(value).__name__} to binary")


def _coerce_enum(value: Any, strictness: StrictnessLevel) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        if strictness == StrictnessLevel.STRICT:
            raise ValueError("expected str for enum, got int")
        return str(value)
    raise ValueError(f"cannot coerce {type(value).__name__} to enum")


_COERCERS: dict[FieldType, Any] = {
    FieldType.STRING: _coerce_string,
    FieldType.TEXT: _coerce_text,
    FieldType.INTEGER: _coerce_integer,
    FieldType.FLOAT: _coerce_float,
    FieldType.BOOLEAN: _coerce_boolean,
    FieldType.DATETIME: _coerce_datetime,
    FieldType.DATE: _coerce_date,
    FieldType.UUID: _coerce_uuid,
    FieldType.JSON: _coerce_json,
    FieldType.ARRAY: _coerce_array,
    FieldType.BINARY: _coerce_binary,
    FieldType.ENUM: _coerce_enum,
}
