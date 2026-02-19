"""Read and write AgenticSchema to/from JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from ninja_core.schema.project import AgenticSchema

DEFAULT_SCHEMA_PATH = Path(".ninjastack") / "schema.json"


def save_schema(schema: AgenticSchema, path: str | Path = DEFAULT_SCHEMA_PATH) -> Path:
    """Serialize an AgenticSchema to a JSON file.

    Args:
        schema: The ASD to persist.
        path: Destination file path. Parent directories are created automatically.

    Returns:
        The resolved path that was written.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(schema.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return dest


def load_schema(path: str | Path = DEFAULT_SCHEMA_PATH) -> AgenticSchema:
    """Deserialize an AgenticSchema from a JSON file.

    Args:
        path: Source file path.

    Returns:
        The parsed AgenticSchema.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If the JSON is invalid.
    """
    src = Path(path)
    data = json.loads(src.read_text(encoding="utf-8"))
    return AgenticSchema.model_validate(data)
