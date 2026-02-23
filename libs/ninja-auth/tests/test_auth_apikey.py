"""Tests for API key strategy."""

import logging

import pytest
from ninja_auth.config import ApiKeyConfig
from ninja_auth.strategies.apikey import ApiKeyStrategy
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Legacy plaintext keys (backward compat)
# ---------------------------------------------------------------------------


def test_apikey_valid_key():
    config = ApiKeyConfig(keys={"service1": "secret-key-123"})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key("secret-key-123")
    assert ctx is not None
    assert ctx.user_id == "apikey:service1"
    assert "service" in ctx.roles
    assert ctx.provider == "apikey"


def test_apikey_invalid_key():
    config = ApiKeyConfig(keys={"service1": "secret-key-123"})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key("wrong-key")
    assert ctx is None


def test_apikey_empty_key():
    config = ApiKeyConfig(keys={"service1": "secret-key-123"})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key("")
    assert ctx is None


def test_apikey_multiple_keys():
    config = ApiKeyConfig(keys={"svc1": "key-a", "svc2": "key-b"})
    strategy = ApiKeyStrategy(config)

    ctx = strategy.validate_key("key-b")
    assert ctx is not None
    assert ctx.user_id == "apikey:svc2"


def test_apikey_metadata_contains_key_name():
    config = ApiKeyConfig(keys={"myservice": "the-key"})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key("the-key")
    assert ctx is not None
    assert ctx.metadata["key_name"] == "myservice"


# ---------------------------------------------------------------------------
# Pre-hashed keys (sha256: prefix)
# ---------------------------------------------------------------------------


def test_apikey_prehashed_valid():
    raw = "super-secret"
    hashed = ApiKeyConfig.hash_key(raw)
    assert hashed.startswith("sha256:")

    config = ApiKeyConfig(keys={"svc": hashed})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key(raw)
    assert ctx is not None
    assert ctx.user_id == "apikey:svc"


def test_apikey_prehashed_invalid():
    hashed = ApiKeyConfig.hash_key("real-key")
    config = ApiKeyConfig(keys={"svc": hashed})
    strategy = ApiKeyStrategy(config)
    assert strategy.validate_key("wrong-key") is None


def test_apikey_prehashed_empty_input():
    hashed = ApiKeyConfig.hash_key("real-key")
    config = ApiKeyConfig(keys={"svc": hashed})
    strategy = ApiKeyStrategy(config)
    assert strategy.validate_key("") is None


# ---------------------------------------------------------------------------
# Env var references ($env: prefix)
# ---------------------------------------------------------------------------


def test_apikey_env_var_valid(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "env-secret")
    config = ApiKeyConfig(keys={"svc": "$env:TEST_API_KEY"})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key("env-secret")
    assert ctx is not None
    assert ctx.user_id == "apikey:svc"


def test_apikey_env_var_invalid_input(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "env-secret")
    config = ApiKeyConfig(keys={"svc": "$env:TEST_API_KEY"})
    strategy = ApiKeyStrategy(config)
    assert strategy.validate_key("wrong") is None


def test_apikey_env_var_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    config = ApiKeyConfig(keys={"svc": "$env:MISSING_KEY"})
    strategy = ApiKeyStrategy(config)
    assert strategy.validate_key("anything") is None


# ---------------------------------------------------------------------------
# hash_key helper
# ---------------------------------------------------------------------------


def test_hash_key_deterministic():
    assert ApiKeyConfig.hash_key("abc") == ApiKeyConfig.hash_key("abc")


def test_hash_key_different_inputs():
    assert ApiKeyConfig.hash_key("a") != ApiKeyConfig.hash_key("b")


# ---------------------------------------------------------------------------
# resolve_key
# ---------------------------------------------------------------------------


def test_resolve_key_prehashed():
    config = ApiKeyConfig()
    h = ApiKeyConfig.hash_key("x")
    assert config.resolve_key(h) == h


def test_resolve_key_env(monkeypatch):
    monkeypatch.setenv("RK_VAR", "raw-value")
    config = ApiKeyConfig()
    resolved = config.resolve_key("$env:RK_VAR")
    assert resolved == ApiKeyConfig.hash_key("raw-value")


def test_resolve_key_env_missing(monkeypatch):
    monkeypatch.delenv("NOVAR", raising=False)
    config = ApiKeyConfig()
    assert config.resolve_key("$env:NOVAR") is None


def test_resolve_key_legacy_plaintext():
    config = ApiKeyConfig()
    assert config.resolve_key("plain") == ApiKeyConfig.hash_key("plain")


# ---------------------------------------------------------------------------
# Mixed key types
# ---------------------------------------------------------------------------


def test_apikey_mixed_key_types(monkeypatch):
    monkeypatch.setenv("MIX_KEY", "env-key")
    hashed = ApiKeyConfig.hash_key("hashed-key")
    config = ApiKeyConfig(
        keys={
            "plain_svc": "plain-key",
            "hashed_svc": hashed,
            "env_svc": "$env:MIX_KEY",
        }
    )
    strategy = ApiKeyStrategy(config)

    assert strategy.validate_key("plain-key") is not None
    assert strategy.validate_key("hashed-key") is not None
    assert strategy.validate_key("env-key") is not None
    assert strategy.validate_key("unknown") is None


# ---------------------------------------------------------------------------
# HTTP integration (authenticate via header / query param)
# ---------------------------------------------------------------------------


async def test_apikey_authenticate_from_header():
    hashed = ApiKeyConfig.hash_key("my-key")
    config = ApiKeyConfig(header_name="X-API-Key", keys={"svc": hashed})
    strategy = ApiKeyStrategy(config)

    async def homepage(request):
        ctx = await strategy.authenticate(request)
        if ctx:
            return JSONResponse({"user_id": ctx.user_id})
        return JSONResponse({"user_id": None})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    resp = client.get("/", headers={"X-API-Key": "my-key"})
    assert resp.json()["user_id"] == "apikey:svc"

    resp = client.get("/")
    assert resp.json()["user_id"] is None


async def test_apikey_query_param_rejected():
    """API keys in query parameters must be rejected to prevent credential leakage."""
    hashed = ApiKeyConfig.hash_key("qkey")
    config = ApiKeyConfig(keys={"svc": hashed})
    strategy = ApiKeyStrategy(config)

    async def homepage(request):
        ctx = await strategy.authenticate(request)
        if ctx:
            return JSONResponse({"user_id": ctx.user_id})
        return JSONResponse({"user_id": None})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    resp = client.get("/?api_key=qkey")
    assert resp.json()["user_id"] is None


async def test_apikey_query_param_logs_warning(caplog):
    """A deprecation warning must be logged when a query param key is attempted."""
    import logging

    hashed = ApiKeyConfig.hash_key("qkey")
    config = ApiKeyConfig(keys={"svc": hashed})
    strategy = ApiKeyStrategy(config)

    async def homepage(request):
        await strategy.authenticate(request)
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    with caplog.at_level(logging.WARNING, logger="ninja_auth.strategies.apikey"):
        client.get("/?api_key=qkey")

    assert any("query parameter" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------

APIKEY_LOGGER = "ninja_auth.strategies.apikey"


def test_apikey_valid_key_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    """Validated API key emits INFO with key_name but NOT the raw key."""
    config = ApiKeyConfig(keys={"myservice": "secret-key-123"})
    strategy = ApiKeyStrategy(config)

    with caplog.at_level(logging.INFO, logger=APIKEY_LOGGER):
        ctx = strategy.validate_key("secret-key-123")

    assert ctx is not None
    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "validated" in r.message.lower()]
    assert len(info_records) == 1
    assert "myservice" in info_records[0].message
    # Raw key must NEVER appear in logs
    full_output = " ".join(r.message for r in caplog.records)
    assert "secret-key-123" not in full_output


def test_apikey_invalid_key_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Invalid API key emits WARNING with key prefix, NOT the full key."""
    config = ApiKeyConfig(keys={"svc": "real-secret-key"})
    strategy = ApiKeyStrategy(config)

    with caplog.at_level(logging.WARNING, logger=APIKEY_LOGGER):
        ctx = strategy.validate_key("wrong-key-that-is-invalid")

    assert ctx is None
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and "Invalid API key" in r.message]
    assert len(warning_records) == 1
    # Should contain a prefix, not the full key
    assert "wrong-ke" in warning_records[0].message  # first 8 chars
    assert "wrong-key-that-is-invalid" not in warning_records[0].message
