"""Sanitization and escaping utilities for safe UI template rendering.

Provides context-aware escaping for HTML attributes, JavaScript string
literals, CSS class names, and GraphQL identifiers to prevent XSS and
injection attacks in generated UI code.
"""

from __future__ import annotations

import re

from markupsafe import Markup

# Only allow safe identifier characters: alphanumeric, underscore, hyphen.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def safe_identifier(value: str) -> str:
    """Validate and return a safe identifier for use in CSS classes, JS vars, and GraphQL names.

    Strips any characters that are not alphanumeric, underscore, or hyphen.
    Raises ValueError if the result is empty after sanitization.

    Args:
        value: The raw identifier string (entity name, field name, slug, etc.).

    Returns:
        A sanitized identifier string safe for interpolation into JS, CSS, and GraphQL contexts.

    Raises:
        ValueError: If the sanitized result is empty.
    """
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", str(value))
    if not sanitized:
        raise ValueError(f"Identifier is empty after sanitization: {value!r}")
    return sanitized


def sanitize_for_js_string(value: str) -> Markup:
    """Escape a value for safe embedding inside a JavaScript string literal.

    Escapes backslashes, quotes, newlines, and HTML-significant characters
    (angle brackets, ampersands) to prevent both JS breakout and inline
    script injection.

    Args:
        value: The raw string to embed in a JS string literal.

    Returns:
        A Markup-safe string that can be placed inside JS quotes.
    """
    s = str(value)
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("<", "\\x3c")
    s = s.replace(">", "\\x3e")
    s = s.replace("&", "\\x26")
    # Mark as safe so Jinja2 autoescape doesn't double-escape
    return Markup(s)


def safe_slug(value: str) -> str:
    """Sanitize a slug for use in filenames and URL paths.

    Same rules as safe_identifier but also lowercases the result.

    Args:
        value: The raw slug string.

    Returns:
        A sanitized, lowercase slug safe for filenames and URLs.

    Raises:
        ValueError: If the sanitized result is empty.
    """
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", str(value)).lower()
    if not sanitized:
        raise ValueError(f"Slug is empty after sanitization: {value!r}")
    return sanitized


def is_safe_identifier(value: str) -> bool:
    """Check whether a string is a safe identifier without modifying it.

    Args:
        value: The string to check.

    Returns:
        True if the value matches the safe identifier pattern.
    """
    return bool(_SAFE_IDENTIFIER_RE.match(str(value)))
