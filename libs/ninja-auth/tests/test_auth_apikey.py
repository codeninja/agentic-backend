"""Tests for API key strategy."""

from ninja_auth.config import ApiKeyConfig
from ninja_auth.strategies.apikey import ApiKeyStrategy
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


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


async def test_apikey_authenticate_from_header():
    config = ApiKeyConfig(header_name="X-API-Key", keys={"svc": "my-key"})
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


async def test_apikey_authenticate_from_query_param():
    config = ApiKeyConfig(keys={"svc": "qkey"})
    strategy = ApiKeyStrategy(config)

    async def homepage(request):
        ctx = await strategy.authenticate(request)
        if ctx:
            return JSONResponse({"user_id": ctx.user_id})
        return JSONResponse({"user_id": None})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    resp = client.get("/?api_key=qkey")
    assert resp.json()["user_id"] == "apikey:svc"


def test_apikey_metadata_contains_key_name():
    config = ApiKeyConfig(keys={"myservice": "the-key"})
    strategy = ApiKeyStrategy(config)
    ctx = strategy.validate_key("the-key")
    assert ctx is not None
    assert ctx.metadata["key_name"] == "myservice"
