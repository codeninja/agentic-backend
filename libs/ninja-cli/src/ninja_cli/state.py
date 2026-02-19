""".ninjastack/ directory state management — read/write config files."""

from __future__ import annotations

import json
from pathlib import Path

from ninja_core import AgenticSchema

from ninja_cli.config import AuthConfig, ConnectionProfile, ModelProvider, NinjaStackConfig

NINJASTACK_DIR = ".ninjastack"
SCHEMA_FILE = "schema.json"
CONNECTIONS_FILE = "connections.json"
MODELS_FILE = "models.json"
AUTH_FILE = "auth.json"


def _state_dir(root: Path) -> Path:
    return root / NINJASTACK_DIR


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]


def is_initialized(root: Path = Path(".")) -> bool:
    """Check whether .ninjastack/ exists and contains a schema.json."""
    return (_state_dir(root) / SCHEMA_FILE).is_file()


def init_state(project_name: str, root: Path = Path(".")) -> NinjaStackConfig:
    """Create .ninjastack/ with default config files.

    Returns the NinjaStackConfig that was written.
    """
    state = _state_dir(root)
    state.mkdir(parents=True, exist_ok=True)

    # Default ASD schema
    schema = AgenticSchema(project_name=project_name)
    _write_json(state / SCHEMA_FILE, schema.model_dump())

    # Default config
    config = NinjaStackConfig(project_name=project_name)
    _write_json(state / CONNECTIONS_FILE, [c.model_dump() for c in config.connections])
    _write_json(state / MODELS_FILE, config.models.model_dump())
    _write_json(state / AUTH_FILE, config.auth.model_dump())

    return config


def load_config(root: Path = Path(".")) -> NinjaStackConfig:
    """Load the full NinjaStackConfig from .ninjastack/ files.

    Raises FileNotFoundError if .ninjastack/ is not initialized.
    """
    state = _state_dir(root)
    if not state.is_dir():
        raise FileNotFoundError(f"{state} does not exist. Run 'ninjastack init' first.")

    schema_data = _read_json(state / SCHEMA_FILE)
    project_name = schema_data.get("project_name", "my-ninja-project")

    connections_path = state / CONNECTIONS_FILE
    connections: list[ConnectionProfile] = []
    if connections_path.is_file():
        connections = [ConnectionProfile.model_validate(c) for c in _read_json(connections_path)]  # type: ignore[union-attr]

    models_path = state / MODELS_FILE
    models = ModelProvider()
    if models_path.is_file():
        models = ModelProvider.model_validate(_read_json(models_path))

    auth_path = state / AUTH_FILE
    auth = AuthConfig()
    if auth_path.is_file():
        auth = AuthConfig.model_validate(_read_json(auth_path))

    return NinjaStackConfig(
        project_name=project_name,
        connections=connections,
        models=models,
        auth=auth,
    )


def save_connections(connections: list[ConnectionProfile], root: Path = Path(".")) -> None:
    """Persist connection profiles to .ninjastack/connections.json."""
    _write_json(_state_dir(root) / CONNECTIONS_FILE, [c.model_dump() for c in connections])


def save_models(models: ModelProvider, root: Path = Path(".")) -> None:
    """Persist model provider config to .ninjastack/models.json."""
    _write_json(_state_dir(root) / MODELS_FILE, models.model_dump())


def save_auth(auth: AuthConfig, root: Path = Path(".")) -> None:
    """Persist auth config to .ninjastack/auth.json."""
    _write_json(_state_dir(root) / AUTH_FILE, auth.model_dump())
