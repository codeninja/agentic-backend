"""Read and validate .ninjastack/models.json configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_MODEL = "gemini/gemini-2.5-pro"
DEFAULT_FALLBACK = "gemini/gemini-2.5-flash"


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    api_key_env: str | None = None
    base_url: str | None = None


class ModelsConfig(BaseModel):
    """Top-level model configuration from .ninjastack/models.json."""

    default: str = DEFAULT_MODEL
    fallback: str | None = DEFAULT_FALLBACK
    agents: dict[str, str] = Field(default_factory=dict)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


def load_models_config(project_root: str | Path | None = None) -> ModelsConfig:
    """Load models.json from the .ninjastack directory.

    Falls back to sensible Gemini defaults when the file doesn't exist.
    """
    if project_root is None:
        project_root = Path(os.getenv("NINJASTACK_ROOT", "."))
    else:
        project_root = Path(project_root)

    config_path = project_root / ".ninjastack" / "models.json"

    if not config_path.exists():
        return ModelsConfig()

    data = json.loads(config_path.read_text())
    return ModelsConfig.model_validate(data)
