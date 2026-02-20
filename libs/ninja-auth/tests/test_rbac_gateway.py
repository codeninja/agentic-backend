"""Tests for RBAC integration in the AuthGateway middleware."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from ninja_auth.config import AuthConfig, BearerConfig
from ninja_auth.gateway import AuthGateway
from ninja_auth.rbac import RBACConfig, RoleDefinition
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

SECRET = "test-secret"


def _make_token(
    sub: str = "user-1",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "roles": roles or [],
        "permissions": permissions or [],
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


async def _me(request: Request) -> JSONResponse:
    ctx = request.state.user_context
    return JSONResponse(
        {
            "user_id": ctx.user_id,
            "roles": ctx.roles,
            "permissions": ctx.permissions,
        }
    )


def _build_app(config: AuthConfig) -> Starlette:
    app = Starlette(routes=[Route("/me", _me)])
    app.add_middleware(AuthGateway, config=config)
    return app


class TestGatewayRBACEnrichment:
    """The gateway should resolve role-based permissions and merge them into UserContext."""

    def _config(self, rbac: RBACConfig | None = None) -> AuthConfig:
        return AuthConfig(
            bearer=BearerConfig(secret_key=SECRET),
            rbac=rbac or RBACConfig(),
        )

    def test_viewer_role_gets_read_permissions(self) -> None:
        app = _build_app(self._config())
        client = TestClient(app)
        token = _make_token(roles=["viewer"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "read:*" in data["permissions"]

    def test_admin_role_gets_wildcard(self) -> None:
        app = _build_app(self._config())
        client = TestClient(app)
        token = _make_token(roles=["admin"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "*:*" in resp.json()["permissions"]

    def test_custom_role_permissions(self) -> None:
        rbac = RBACConfig(
            roles={
                "billing_reader": RoleDefinition(permissions=["read:Billing"]),
            },
        )
        app = _build_app(self._config(rbac))
        client = TestClient(app)
        token = _make_token(roles=["billing_reader"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "read:Billing" in resp.json()["permissions"]

    def test_existing_permissions_preserved(self) -> None:
        app = _build_app(self._config())
        client = TestClient(app)
        token = _make_token(roles=["viewer"], permissions=["custom:thing"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert "custom:thing" in data["permissions"]
        assert "read:*" in data["permissions"]

    def test_no_roles_no_enrichment(self) -> None:
        app = _build_app(self._config())
        client = TestClient(app)
        token = _make_token(roles=[], permissions=["read:Orders"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["permissions"] == ["read:Orders"]

    def test_rbac_disabled_no_enrichment(self) -> None:
        rbac = RBACConfig(enabled=False)
        app = _build_app(self._config(rbac))
        client = TestClient(app)
        token = _make_token(roles=["admin"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        # admin role should NOT be resolved when RBAC is disabled
        assert "*:*" not in data["permissions"]

    def test_deduplication_of_permissions(self) -> None:
        app = _build_app(self._config())
        client = TestClient(app)
        # Token already has read:* which viewer would also add
        token = _make_token(roles=["viewer"], permissions=["read:*"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        perms = resp.json()["permissions"]
        assert perms.count("read:*") == 1
