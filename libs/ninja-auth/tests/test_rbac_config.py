"""Tests for RBAC configuration loading via AuthConfig."""

from __future__ import annotations

import json
from pathlib import Path

from ninja_auth.config import AuthConfig
from ninja_auth.rbac import RBACConfig, RBACPolicy, RoleDefinition


class TestAuthConfigRBAC:
    """Ensure the rbac section is loaded from auth.json."""

    def test_default_rbac_config(self) -> None:
        cfg = AuthConfig()
        assert cfg.rbac.enabled is True
        assert cfg.rbac.roles == {}

    def test_rbac_from_dict(self) -> None:
        data = {
            "rbac": {
                "enabled": True,
                "roles": {
                    "billing_admin": {
                        "permissions": ["read:Billing", "write:Billing", "delete:Billing"],
                        "description": "Full billing access",
                    },
                },
                "default_role": "viewer",
            },
        }
        cfg = AuthConfig.model_validate(data)
        assert cfg.rbac.enabled is True
        assert "billing_admin" in cfg.rbac.roles
        assert cfg.rbac.default_role == "viewer"

    def test_rbac_from_file(self, tmp_path: Path) -> None:
        auth_json = tmp_path / "auth.json"
        auth_json.write_text(
            json.dumps(
                {
                    "default_strategy": "bearer",
                    "rbac": {
                        "enabled": True,
                        "roles": {
                            "ops": {"permissions": ["read:*", "write:Infra"]},
                        },
                    },
                }
            )
        )
        cfg = AuthConfig.from_file(auth_json)
        assert cfg.rbac.roles["ops"].permissions == ["read:*", "write:Infra"]

    def test_rbac_disabled_from_file(self, tmp_path: Path) -> None:
        auth_json = tmp_path / "auth.json"
        auth_json.write_text(json.dumps({"rbac": {"enabled": False}}))
        cfg = AuthConfig.from_file(auth_json)
        assert cfg.rbac.enabled is False

    def test_policy_from_config(self) -> None:
        cfg = RBACConfig(
            roles={
                "support": RoleDefinition(
                    permissions=["read:Orders", "read:Users"],
                ),
            },
        )
        policy = RBACPolicy(cfg)
        perms = policy.permissions_for_roles(["support"])
        assert policy.is_allowed(perms, "read", "Orders")
        assert policy.is_allowed(perms, "read", "Users")
        assert not policy.is_allowed(perms, "write", "Orders")
