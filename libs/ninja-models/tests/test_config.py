"""Tests for ninja_models.config."""

import json
from pathlib import Path

from ninja_models.config import DEFAULT_FALLBACK, DEFAULT_MODEL, ModelsConfig, ProviderConfig, load_models_config


class TestModelsConfig:
    def test_defaults(self):
        config = ModelsConfig()
        assert config.default == DEFAULT_MODEL
        assert config.fallback == DEFAULT_FALLBACK
        assert config.agents == {}
        assert config.providers == {}

    def test_custom_values(self):
        config = ModelsConfig(
            default="openai/gpt-4o",
            fallback="openai/gpt-4o-mini",
            agents={"billing": "openai/gpt-4o"},
            providers={"openai": ProviderConfig(api_key_env="OPENAI_API_KEY")},
        )
        assert config.default == "openai/gpt-4o"
        assert config.agents["billing"] == "openai/gpt-4o"
        assert config.providers["openai"].api_key_env == "OPENAI_API_KEY"

    def test_no_fallback(self):
        config = ModelsConfig(fallback=None)
        assert config.fallback is None


class TestProviderConfig:
    def test_empty(self):
        p = ProviderConfig()
        assert p.api_key_env is None
        assert p.base_url is None

    def test_ollama(self):
        p = ProviderConfig(base_url="http://localhost:11434")
        assert p.base_url == "http://localhost:11434"


class TestLoadModelsConfig:
    def test_missing_file_returns_defaults(self, tmp_path: Path):
        config = load_models_config(tmp_path)
        assert config.default == DEFAULT_MODEL
        assert config.fallback == DEFAULT_FALLBACK

    def test_reads_json_file(self, tmp_path: Path):
        ninjastack = tmp_path / ".ninjastack"
        ninjastack.mkdir()
        (ninjastack / "models.json").write_text(
            json.dumps(
                {
                    "default": "openai/gpt-4o",
                    "fallback": "openai/gpt-4o-mini",
                    "agents": {"data-user": "gemini/gemini-2.5-flash"},
                    "providers": {"openai": {"api_key_env": "OPENAI_API_KEY"}},
                }
            )
        )

        config = load_models_config(tmp_path)
        assert config.default == "openai/gpt-4o"
        assert config.fallback == "openai/gpt-4o-mini"
        assert config.agents["data-user"] == "gemini/gemini-2.5-flash"
        assert config.providers["openai"].api_key_env == "OPENAI_API_KEY"

    def test_partial_json(self, tmp_path: Path):
        ninjastack = tmp_path / ".ninjastack"
        ninjastack.mkdir()
        (ninjastack / "models.json").write_text(json.dumps({"default": "ollama/llama3"}))

        config = load_models_config(tmp_path)
        assert config.default == "ollama/llama3"
        assert config.fallback == DEFAULT_FALLBACK
        assert config.agents == {}
