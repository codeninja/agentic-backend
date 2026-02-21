"""Agent & LLM safety — prompt injection prevention, input validation, error sanitization.

Provides guardrails against:
- Prompt injection via malicious ASD schema metadata (domain/entity names)
- Token exhaustion via oversized agent requests
- Information disclosure via unsanitized error messages in agent responses
- Invalid tool names bypassing scope enforcement
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Prompt-injection prevention
# ---------------------------------------------------------------------------

# Schema identifiers (domain names, entity names) must be alphanumeric with
# underscores/hyphens/spaces.  Anything else is suspicious and gets stripped.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ -]{0,127}$")

# Patterns that could manipulate LLM behavior when interpolated into prompts.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions?"),
    re.compile(r"(?i)system\s*:\s*"),
    re.compile(r"(?i)you\s+are\s+now\s+"),
    re.compile(r"(?i)<\s*/?\s*(?:system|user|assistant)\s*>"),
    re.compile(r"(?i)\b(?:forget|disregard|override)\s+.*(?:instruction|rule|prompt)"),
    re.compile(r"\{\{.*\}\}"),  # Jinja2 template injection
    re.compile(r"\{%.*%\}"),  # Jinja2 block injection
]


def sanitize_identifier(value: str) -> str:
    """Sanitize a schema identifier (domain/entity name) for safe prompt interpolation.

    Strips control characters and validates against an allowlist pattern.
    Raises ``ValueError`` if the name is empty or contains injection patterns.

    Args:
        value: The raw identifier string from the ASD schema.

    Returns:
        The sanitized identifier, stripped of leading/trailing whitespace.

    Raises:
        ValueError: If the identifier is empty, too long, or contains
            characters/patterns that could enable prompt injection.
    """
    if not isinstance(value, str):
        raise ValueError(f"Identifier must be a string, got {type(value).__name__}")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Identifier must not be empty")

    if not _SAFE_IDENTIFIER_RE.match(cleaned):
        raise ValueError(
            f"Invalid identifier: {cleaned!r}. "
            "Must start with a letter, contain only alphanumeric characters, "
            "underscores, hyphens, or spaces, and be at most 128 characters."
        )

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                f"Identifier {cleaned!r} contains a prompt-injection pattern and was rejected."
            )

    return cleaned


def sanitize_identifiers(values: list[str]) -> list[str]:
    """Sanitize a list of schema identifiers.

    Args:
        values: Raw identifier strings from the ASD schema.

    Returns:
        List of sanitized identifiers.

    Raises:
        ValueError: If any identifier fails validation.
    """
    return [sanitize_identifier(v) for v in values]


# ---------------------------------------------------------------------------
# Input size validation
# ---------------------------------------------------------------------------

# Defaults — callers can override per-agent if needed.
MAX_REQUEST_LENGTH = 10_000  # characters
MAX_TOOL_KWARGS_SIZE = 50_000  # approximate serialized size in characters


def validate_request_size(request: str, max_length: int = MAX_REQUEST_LENGTH) -> str:
    """Validate that an agent request does not exceed the size limit.

    Args:
        request: The user request string.
        max_length: Maximum allowed character count.

    Returns:
        The validated request string.

    Raises:
        ValueError: If the request exceeds the size limit.
    """
    if not isinstance(request, str):
        raise ValueError(f"Request must be a string, got {type(request).__name__}")
    if len(request) > max_length:
        raise ValueError(
            f"Request too large: {len(request)} characters exceeds "
            f"maximum of {max_length} characters."
        )
    return request


def validate_tool_kwargs_size(
    kwargs: dict[str, Any],
    max_size: int = MAX_TOOL_KWARGS_SIZE,
) -> dict[str, Any]:
    """Validate that tool keyword arguments do not exceed the size limit.

    Uses a fast approximation based on ``str(kwargs)`` length to avoid
    importing a full serialization library.

    Args:
        kwargs: The tool keyword arguments dict.
        max_size: Maximum allowed approximate serialized size.

    Returns:
        The validated kwargs dict.

    Raises:
        ValueError: If the serialized kwargs exceed the size limit.
    """
    approx_size = len(str(kwargs))
    if approx_size > max_size:
        raise ValueError(
            f"Tool arguments too large: ~{approx_size} characters exceeds "
            f"maximum of {max_size} characters."
        )
    return kwargs


# ---------------------------------------------------------------------------
# Error message sanitization
# ---------------------------------------------------------------------------

# Internal details we must never leak to callers.
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(?:password|secret|token|api[_-]?key|credential)\s*[=:]\s*\S+"),
    re.compile(r"/(?:home|root|var|etc|tmp)/\S+"),  # filesystem paths
    re.compile(r"(?i)traceback\s*\(most\s+recent\s+call\s+last\)"),
    re.compile(r'File\s+"[^"]+",\s+line\s+\d+'),  # Python stack frame
    re.compile(r"(?i)(?:sql|mongo|neo4j|redis).*(?:connection|auth).*(?:failed|error|refused)", re.DOTALL),
]

# Generic safe messages for different error categories.
_SAFE_ERROR_MESSAGES: dict[str, str] = {
    "KeyError": "The requested resource was not found.",
    "ValueError": "The provided input was invalid.",
    "TypeError": "An internal type error occurred.",
    "PermissionError": "Access denied.",
    "TimeoutError": "The operation timed out.",
    "ConnectionError": "A connectivity issue occurred.",
}


def sanitize_error(exc: Exception) -> str:
    """Produce a caller-safe error message from an exception.

    Strips filesystem paths, credentials, and stack traces. Falls back to a
    generic category-based message when the raw message contains sensitive data.

    Args:
        exc: The exception to sanitize.

    Returns:
        A safe error string suitable for inclusion in an API/agent response.
    """
    raw = str(exc)
    exc_type = type(exc).__name__

    # Check for sensitive content.
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(raw):
            return _SAFE_ERROR_MESSAGES.get(exc_type, "An internal error occurred.")

    # Even if no sensitive pattern matched, cap the message length.
    if len(raw) > 200:
        raw = raw[:200] + "..."

    return raw


# ---------------------------------------------------------------------------
# Tool name validation
# ---------------------------------------------------------------------------

# Tool names follow the pattern: <entity_lower>_<operation>
_SAFE_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def validate_tool_name(name: str) -> str:
    """Validate a tool name against the expected naming convention.

    Args:
        name: The tool name to validate.

    Returns:
        The validated tool name.

    Raises:
        ValueError: If the tool name does not match the expected pattern.
    """
    if not isinstance(name, str):
        raise ValueError(f"Tool name must be a string, got {type(name).__name__}")
    if not _SAFE_TOOL_NAME_RE.match(name):
        raise ValueError(
            f"Invalid tool name: {name!r}. "
            "Must start with a lowercase letter and contain only "
            "lowercase alphanumeric characters and underscores (max 128 chars)."
        )
    return name
