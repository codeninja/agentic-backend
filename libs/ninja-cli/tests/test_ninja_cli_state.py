"""Tests for .ninjastack/ state management."""

import json

import pytest
from ninja_cli.config import AuthConfig, ConnectionProfile, ModelProvider
from ninja_cli.state import (
    init_state,
    is_initialized,
    load_config,
    save_auth,
    save_connections,
    save_models,
)


class TestIsInitialized:
    def test_not_initialized(self, tmp_path):
        assert is_initialized(tmp_path) is False

    def test_initialized(self, tmp_path):
        state = tmp_path / ".ninjastack"
        state.mkdir()
        (state / "schema.json").write_text("{}")
        assert is_initialized(tmp_path) is True

    def test_dir_without_schema(self, tmp_path):
        (tmp_path / ".ninjastack").mkdir()
        assert is_initialized(tmp_path) is False


class TestInitState:
    def test_creates_directory_and_files(self, tmp_path):
        config = init_state("test-project", tmp_path)
        state = tmp_path / ".ninjastack"

        assert state.is_dir()
        assert (state / "schema.json").is_file()
        assert (state / "connections.json").is_file()
        assert (state / "models.json").is_file()
        assert (state / "auth.json").is_file()
        assert config.project_name == "test-project"

    def test_schema_json_content(self, tmp_path):
        init_state("test-project", tmp_path)
        data = json.loads((tmp_path / ".ninjastack" / "schema.json").read_text())
        assert data["project_name"] == "test-project"
        assert data["version"] == "1.0"
        assert data["entities"] == []

    def test_models_json_content(self, tmp_path):
        init_state("test-project", tmp_path)
        data = json.loads((tmp_path / ".ninjastack" / "models.json").read_text())
        assert data["provider"] == "gemini"

    def test_auth_json_content(self, tmp_path):
        init_state("test-project", tmp_path)
        data = json.loads((tmp_path / ".ninjastack" / "auth.json").read_text())
        assert data["strategy"] == "none"

    def test_connections_json_content(self, tmp_path):
        init_state("test-project", tmp_path)
        data = json.loads((tmp_path / ".ninjastack" / "connections.json").read_text())
        assert data == []


class TestLoadConfig:
    def test_load_after_init(self, tmp_path):
        init_state("roundtrip-test", tmp_path)
        config = load_config(tmp_path)
        assert config.project_name == "roundtrip-test"
        assert config.models.provider == "gemini"
        assert config.auth.strategy == "none"
        assert config.connections == []

    def test_load_not_initialized(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            load_config(tmp_path)


class TestSaveHelpers:
    def test_save_connections(self, tmp_path):
        init_state("test", tmp_path)
        conns = [ConnectionProfile(name="pg", engine="postgres", url="postgresql://localhost/db")]
        save_connections(conns, tmp_path)

        config = load_config(tmp_path)
        assert len(config.connections) == 1
        assert config.connections[0].name == "pg"

    def test_save_models(self, tmp_path):
        init_state("test", tmp_path)
        models = ModelProvider(provider="openai", model="gpt-4o", api_key_env="OPENAI_API_KEY")
        save_models(models, tmp_path)

        config = load_config(tmp_path)
        assert config.models.provider == "openai"

    def test_save_auth(self, tmp_path):
        init_state("test", tmp_path)
        auth = AuthConfig(strategy="jwt", issuer="https://auth.example.com")
        save_auth(auth, tmp_path)

        config = load_config(tmp_path)
        assert config.auth.strategy == "jwt"
        assert config.auth.issuer == "https://auth.example.com"
