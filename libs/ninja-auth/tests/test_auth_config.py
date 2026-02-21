"""Tests for AuthConfig loading."""

import json
import os
import tempfile

import pytest

from ninja_auth.config import AuthConfig, IdentityConfig, _INSECURE_TOKEN_SECRET


def test_auth_config_defaults():
    cfg = AuthConfig()
    assert cfg.default_strategy == "bearer"
    assert "/health" in cfg.public_paths
    assert cfg.bearer.algorithm == "HS256"
    assert cfg.api_key.header_name == "X-API-Key"
    assert cfg.identity.enabled is True


def test_auth_config_from_file():
    data = {
        "default_strategy": "apikey",
        "public_paths": ["/health", "/custom"],
        "bearer": {"algorithm": "RS256", "secret_key": "test-key"},
        "api_key": {"header_name": "X-Custom-Key", "keys": {"svc1": "key123"}},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        cfg = AuthConfig.from_file(f.name)

    assert cfg.default_strategy == "apikey"
    assert "/custom" in cfg.public_paths
    assert cfg.bearer.algorithm == "RS256"
    assert cfg.api_key.keys["svc1"] == "key123"


def test_auth_config_from_missing_file():
    cfg = AuthConfig.from_file("/nonexistent/auth.json")
    assert cfg.default_strategy == "bearer"


def test_auth_config_identity_defaults():
    cfg = AuthConfig()
    assert cfg.identity.hash_algorithm == "bcrypt"
    assert cfg.identity.token_expiry_minutes == 60


def test_auth_config_oauth2_providers():
    data = {
        "oauth2_providers": {
            "google": {
                "client_id": "gid",
                "client_secret": "gsecret",
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        cfg = AuthConfig.from_file(f.name)

    assert "google" in cfg.oauth2_providers
    assert cfg.oauth2_providers["google"].client_id == "gid"


# --- Tests for IdentityConfig.token_secret validation (issue #50) ---


class TestTokenSecretValidation:
    """Verify that the insecure default token_secret is rejected outside dev/test."""

    def test_insecure_default_rejected_in_production(self, monkeypatch):
        monkeypatch.delenv("NINJASTACK_ENV", raising=False)
        with pytest.raises(ValueError, match="insecure default"):
            IdentityConfig()

    def test_insecure_default_rejected_with_prod_env(self, monkeypatch):
        monkeypatch.setenv("NINJASTACK_ENV", "production")
        with pytest.raises(ValueError, match="insecure default"):
            IdentityConfig()

    def test_insecure_default_allowed_in_dev(self, monkeypatch):
        monkeypatch.setenv("NINJASTACK_ENV", "dev")
        cfg = IdentityConfig()
        assert cfg.token_secret != _INSECURE_TOKEN_SECRET
        assert len(cfg.token_secret) > 16

    def test_insecure_default_allowed_in_test(self, monkeypatch):
        monkeypatch.setenv("NINJASTACK_ENV", "test")
        cfg = IdentityConfig()
        assert cfg.token_secret != _INSECURE_TOKEN_SECRET

    def test_explicit_secret_always_accepted(self, monkeypatch):
        monkeypatch.delenv("NINJASTACK_ENV", raising=False)
        cfg = IdentityConfig(token_secret="my-super-secret-key-123")
        assert cfg.token_secret == "my-super-secret-key-123"

    def test_explicit_secret_accepted_in_production(self, monkeypatch):
        monkeypatch.setenv("NINJASTACK_ENV", "production")
        cfg = IdentityConfig(token_secret="prod-secret-abc")
        assert cfg.token_secret == "prod-secret-abc"

    def test_dev_mode_generates_unique_secrets(self, monkeypatch):
        monkeypatch.setenv("NINJASTACK_ENV", "dev")
        cfg1 = IdentityConfig()
        cfg2 = IdentityConfig()
        assert cfg1.token_secret != cfg2.token_secret
