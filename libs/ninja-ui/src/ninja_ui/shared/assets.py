"""Shared constants and helpers for UI generation."""

from __future__ import annotations

FIELD_TYPE_INPUT_MAP: dict[str, str] = {
    "string": "text",
    "text": "textarea",
    "integer": "number",
    "float": "number",
    "boolean": "checkbox",
    "datetime": "datetime-local",
    "date": "date",
    "uuid": "text",
    "json": "textarea",
    "array": "textarea",
    "binary": "file",
    "enum": "select",
}


def snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)
