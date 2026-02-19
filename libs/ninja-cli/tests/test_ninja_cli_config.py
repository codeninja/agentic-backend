"""Tests for NinjaStackConfig and related models."""

import pytest
from ninja_cli.config import AuthConfig, ConnectionProfile, ModelProvider, NinjaStackConfig
from pydantic import ValidationError


class TestConnectionProfile:
    def test_valid_connection(self):
        conn = ConnectionProfile(name="primary", engine="postgres", url="postgresql://localhost/db")
        assert conn.name == "primary"
        assert conn.engine == "postgres"
        assert conn.default is False

    def test_default_flag(self):
        conn = ConnectionProfile(name="primary", engine="postgres", url="postgresql://localhost/db", default=True)
        assert conn.default is True

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ConnectionProfile(name="", engine="postgres", url="postgresql://localhost/db")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ConnectionProfile(name="primary", engine="postgres", url="postgresql://localhost/db", extra="bad")


class TestModelProvider:
    def test_defaults(self):
        mp = ModelProvider()
        assert mp.provider == "gemini"
        assert mp.model == "gemini-2.0-flash"
        assert mp.api_key_env == "GOOGLE_API_KEY"

    def test_custom_provider(self):
        mp = ModelProvider(provider="openai", model="gpt-4o", api_key_env="OPENAI_API_KEY")
        assert mp.provider == "openai"


class TestAuthConfig:
    def test_defaults(self):
        auth = AuthConfig()
        assert auth.strategy == "none"
        assert auth.issuer is None

    def test_jwt_strategy(self):
        auth = AuthConfig(strategy="jwt", issuer="https://auth.example.com", audience="my-api")
        assert auth.strategy == "jwt"
        assert auth.audience == "my-api"


class TestNinjaStackConfig:
    def test_defaults(self):
        config = NinjaStackConfig()
        assert config.project_name == "my-ninja-project"
        assert config.connections == []
        assert config.models.provider == "gemini"
        assert config.auth.strategy == "none"

    def test_custom_project_name(self):
        config = NinjaStackConfig(project_name="my-app")
        assert config.project_name == "my-app"

    def test_with_connections(self):
        conn = ConnectionProfile(name="pg", engine="postgres", url="postgresql://localhost/db")
        config = NinjaStackConfig(connections=[conn])
        assert len(config.connections) == 1
        assert config.connections[0].name == "pg"
