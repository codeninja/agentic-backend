"""ADK agent YAML templates for Ninja Stack agent generation."""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent


def get_template(name: str) -> str:
    """Load a YAML template by name (without extension)."""
    path = TEMPLATES_DIR / f"{name}.yaml"
    return path.read_text()
