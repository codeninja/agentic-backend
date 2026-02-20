"""Tests for agent context injection via contextvars."""

import pytest
from ninja_auth.agent_context import (
    clear_user_context,
    current_user_context,
    require_permission,
    require_role,
    require_user_context,
    set_user_context,
)
from ninja_auth.context import ANONYMOUS_USER, UserContext


def test_default_is_anonymous():
    ctx = current_user_context()
    assert not ctx.is_authenticated
    assert ctx.provider == "anonymous"


def test_set_and_get_user_context():
    user = UserContext(user_id="u1", email="a@b.com", provider="bearer")
    token = set_user_context(user)
    try:
        ctx = current_user_context()
        assert ctx.user_id == "u1"
        assert ctx.email == "a@b.com"
    finally:
        clear_user_context(token)

    # After clearing, should be back to anonymous
    assert not current_user_context().is_authenticated


def test_require_user_context_raises_when_anonymous():
    token = set_user_context(ANONYMOUS_USER)
    try:
        with pytest.raises(PermissionError, match="Authenticated user context required"):
            require_user_context()
    finally:
        clear_user_context(token)


def test_require_user_context_returns_authenticated():
    user = UserContext(user_id="u1", provider="identity")
    token = set_user_context(user)
    try:
        ctx = require_user_context()
        assert ctx.user_id == "u1"
    finally:
        clear_user_context(token)


def test_require_role_passes():
    user = UserContext(user_id="u1", roles=["admin", "editor"])
    token = set_user_context(user)
    try:
        ctx = require_role("admin")
        assert ctx.user_id == "u1"
    finally:
        clear_user_context(token)


def test_require_role_raises_when_missing():
    user = UserContext(user_id="u1", roles=["viewer"])
    token = set_user_context(user)
    try:
        with pytest.raises(PermissionError, match="Role required: admin"):
            require_role("admin")
    finally:
        clear_user_context(token)


def test_require_permission_passes():
    user = UserContext(user_id="u1", permissions=["read:orders"])
    token = set_user_context(user)
    try:
        ctx = require_permission("read:orders")
        assert ctx.user_id == "u1"
    finally:
        clear_user_context(token)


def test_require_permission_raises_when_missing():
    user = UserContext(user_id="u1", permissions=[])
    token = set_user_context(user)
    try:
        with pytest.raises(PermissionError, match="Permission required: delete:orders"):
            require_permission("delete:orders")
    finally:
        clear_user_context(token)


async def test_agent_tool_can_access_context():
    """Simulate an agent tool accessing user context from the contextvar."""

    def simulated_agent_tool() -> dict:
        """A tool function that would run inside ADK agent execution."""
        user = require_user_context()
        return {"user_id": user.user_id, "roles": user.roles}

    user = UserContext(user_id="agent-user", roles=["admin"], provider="bearer")
    token = set_user_context(user)
    try:
        result = simulated_agent_tool()
        assert result["user_id"] == "agent-user"
        assert result["roles"] == ["admin"]
    finally:
        clear_user_context(token)


async def test_gateway_sets_contextvar():
    """Verify AuthGateway sets the contextvar for downstream agent tools."""
    import jwt
    from ninja_auth.config import AuthConfig, BearerConfig
    from ninja_auth.gateway import AuthGateway
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    secret = "gateway-contextvar-test-key-32-bytes!!"

    async def endpoint(request: Request) -> JSONResponse:
        # Access via contextvar (as an agent tool would)
        ctx = current_user_context()
        return JSONResponse({"user_id": ctx.user_id, "via": "contextvar"})

    config = AuthConfig(bearer=BearerConfig(secret_key=secret))
    app = Starlette(routes=[Route("/agent", endpoint)])
    app.add_middleware(AuthGateway, config=config)
    client = TestClient(app)

    token = jwt.encode({"sub": "cv-user"}, secret, algorithm="HS256")
    resp = client.get("/agent", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "cv-user"
    assert resp.json()["via"] == "contextvar"
