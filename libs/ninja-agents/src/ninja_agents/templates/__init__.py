"""ADK agent YAML templates for Ninja Stack agent generation."""

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_template(name: str) -> str:
    """Load a YAML template by name (without extension).

    Args:
        name: Template name consisting only of alphanumeric characters,
              hyphens, and underscores. The ``.yaml`` extension is appended
              automatically.

    Returns:
        The template file contents as a string.

    Raises:
        ValueError: If *name* contains invalid characters or the resolved
            path escapes the templates directory.
        FileNotFoundError: If the template file does not exist.
    """
    if not _VALID_NAME_RE.match(name):
        raise ValueError(f"Invalid template name: {name!r}")
    path = (TEMPLATES_DIR / f"{name}.yaml").resolve()
    if not path.is_relative_to(TEMPLATES_DIR.resolve()):
        raise ValueError(f"Template path escapes templates directory: {name!r}")
    return path.read_text()
