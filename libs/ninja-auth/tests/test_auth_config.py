"""Tests for AuthConfig loading."""

import json
import tempfile

import pytest
from ninja_auth.config import (
    _INSECURE_TOKEN_SECRET,
    AuthConfig,
    BearerConfig,
    IdentityConfig,
    OAuth2ProviderConfig,
)


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
        "bearer": {"algorithm": "RS256", "public_key": "test-public-key"},
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


# --- Tests for BearerConfig key validation (issue #56) ---


class TestBearerConfigValidation:
    """Verify that BearerConfig rejects empty keys for relevant algorithms."""

    def test_empty_secret_key_rejected_for_hs256(self, monkeypatch):
        monkeypatch.delenv("NINJASTACK_ENV", raising=False)
        with pytest.raises(ValueError, match="secret_key must not be empty"):
            BearerConfig(algorithm="HS256", secret_key="")

    def test_empty_secret_key_rejected_for_hs384(self, monkeypatch):
        monkeypatch.delenv("NINJASTACK_ENV", raising=False)
        with pytest.raises(ValueError, match="secret_key must not be empty"):
            BearerConfig(algorithm="HS384")

    def test_empty_secret_key_rejected_for_hs512(self, monkeypatch):
        monkeypatch.delenv("NINJASTACK_ENV", raising=False)
        with pytest.raises(ValueError, match="secret_key must not be empty"):
            BearerConfig(algorithm="HS512")

    def test_explicit_secret_key_accepted(self):
        cfg = BearerConfig(algorithm="HS256", secret_key="my-secret")
        assert cfg.secret_key == "my-secret"

    def test_empty_public_key_rejected_for_rs256(self):
        with pytest.raises(ValueError, match="public_key must not be empty"):
            BearerConfig(algorithm="RS256", public_key="")

    def test_rs256_with_public_key_accepted(self):
        cfg = BearerConfig(algorithm="RS256", public_key="some-public-key")
        assert cfg.public_key == "some-public-key"

    def test_dev_mode_auto_generates_secret(self, monkeypatch):
        monkeypatch.setenv("NINJASTACK_ENV", "dev")
        cfg = BearerConfig(algorithm="HS256")
        assert cfg.secret_key != ""
        assert len(cfg.secret_key) > 16


# --- Tests for OAuth2ProviderConfig.redirect_uri validation (issue #56) ---


class TestRedirectUriValidation:
    def test_empty_redirect_uri_accepted(self):
        cfg = OAuth2ProviderConfig(
            client_id="c",
            client_secret="s",
            authorize_url="https://a.com",
            token_url="https://t.com",
            userinfo_url="https://u.com",
            redirect_uri="",
        )
        assert cfg.redirect_uri == ""

    def test_valid_https_redirect_uri(self):
        cfg = OAuth2ProviderConfig(
            client_id="c",
            client_secret="s",
            authorize_url="https://a.com",
            token_url="https://t.com",
            userinfo_url="https://u.com",
            redirect_uri="https://myapp.com/callback",
        )
        assert cfg.redirect_uri == "https://myapp.com/callback"

    def test_valid_http_redirect_uri(self):
        cfg = OAuth2ProviderConfig(
            client_id="c",
            client_secret="s",
            authorize_url="https://a.com",
            token_url="https://t.com",
            userinfo_url="https://u.com",
            redirect_uri="http://localhost:3000/callback",
        )
        assert cfg.redirect_uri == "http://localhost:3000/callback"

    def test_invalid_scheme_rejected(self):
        with pytest.raises(ValueError, match="HTTP\\(S\\) URL"):
            OAuth2ProviderConfig(
                client_id="c",
                client_secret="s",
                authorize_url="https://a.com",
                token_url="https://t.com",
                userinfo_url="https://u.com",
                redirect_uri="ftp://evil.com/callback",
            )

    def test_missing_hostname_rejected(self):
        with pytest.raises(ValueError, match="hostname"):
            OAuth2ProviderConfig(
                client_id="c",
                client_secret="s",
                authorize_url="https://a.com",
                token_url="https://t.com",
                userinfo_url="https://u.com",
                redirect_uri="https:///callback",
            )
