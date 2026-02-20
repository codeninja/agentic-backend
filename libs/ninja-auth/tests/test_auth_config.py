"""Tests for AuthConfig loading."""

import json
import tempfile

from ninja_auth.config import AuthConfig


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
