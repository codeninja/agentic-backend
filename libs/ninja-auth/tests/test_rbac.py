"""Tests for ninja_auth.rbac — RBAC roles, permissions, and enforcement."""

from __future__ import annotations

import logging

import pytest
from ninja_auth.context import UserContext
from ninja_auth.rbac import (
    Action,
    RBACConfig,
    RBACPolicy,
    RoleDefinition,
    permission_matches,
    require_domain_permission,
)

# ---------------------------------------------------------------------------
# permission_matches
# ---------------------------------------------------------------------------


class TestPermissionMatches:
    def test_exact_match(self) -> None:
        assert permission_matches("read:Orders", "read:Orders") is True

    def test_action_mismatch(self) -> None:
        assert permission_matches("read:Orders", "write:Orders") is False

    def test_scope_mismatch(self) -> None:
        assert permission_matches("read:Orders", "read:Billing") is False

    def test_wildcard_action(self) -> None:
        assert permission_matches("*:Orders", "read:Orders") is True
        assert permission_matches("*:Orders", "write:Orders") is True
        assert permission_matches("*:Orders", "delete:Orders") is True

    def test_wildcard_scope(self) -> None:
        assert permission_matches("read:*", "read:Orders") is True
        assert permission_matches("read:*", "read:Billing") is True
        assert permission_matches("read:*", "write:Billing") is False

    def test_full_wildcard(self) -> None:
        assert permission_matches("*:*", "read:Orders") is True
        assert permission_matches("*:*", "write:Billing") is True
        assert permission_matches("*:*", "delete:Users.Profile") is True

    def test_domain_covers_entity(self) -> None:
        assert permission_matches("read:Billing", "read:Billing.Invoice") is True
        assert permission_matches("write:Billing", "write:Billing.Payment") is True

    def test_domain_does_not_cover_other_domain(self) -> None:
        assert permission_matches("read:Billing", "read:Orders") is False

    def test_entity_does_not_cover_domain(self) -> None:
        assert permission_matches("read:Billing.Invoice", "read:Billing") is False

    def test_invalid_format(self) -> None:
        assert permission_matches("invalid", "read:Orders") is False
        assert permission_matches("read:Orders", "invalid") is False
        assert permission_matches("", "") is False


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------


class TestAction:
    def test_values(self) -> None:
        assert Action.READ == "read"
        assert Action.WRITE == "write"
        assert Action.DELETE == "delete"
        assert Action.WILDCARD == "*"


# ---------------------------------------------------------------------------
# RBACConfig
# ---------------------------------------------------------------------------


class TestRBACConfig:
    def test_defaults(self) -> None:
        cfg = RBACConfig()
        assert cfg.enabled is True
        assert cfg.roles == {}
        assert cfg.default_role is None

    def test_custom_roles(self) -> None:
        cfg = RBACConfig(
            roles={
                "billing_reader": RoleDefinition(
                    permissions=["read:Billing"],
                    description="Can read billing data",
                ),
            },
        )
        assert "billing_reader" in cfg.roles
        assert cfg.roles["billing_reader"].permissions == ["read:Billing"]

    def test_from_dict(self) -> None:
        data = {
            "enabled": True,
            "roles": {
                "ops": {"permissions": ["read:*", "write:Infra"]},
            },
            "default_role": "viewer",
        }
        cfg = RBACConfig.model_validate(data)
        assert cfg.default_role == "viewer"
        assert cfg.roles["ops"].permissions == ["read:*", "write:Infra"]


# ---------------------------------------------------------------------------
# RBACPolicy
# ---------------------------------------------------------------------------


class TestRBACPolicy:
    def test_builtin_roles(self) -> None:
        policy = RBACPolicy()
        assert "admin" in policy.roles()
        assert "editor" in policy.roles()
        assert "viewer" in policy.roles()

    def test_admin_has_full_access(self) -> None:
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["admin"])
        assert policy.is_allowed(perms, "read", "Orders")
        assert policy.is_allowed(perms, "write", "Billing")
        assert policy.is_allowed(perms, "delete", "Users", "Profile")

    def test_viewer_read_only(self) -> None:
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["viewer"])
        assert policy.is_allowed(perms, "read", "Orders")
        assert policy.is_allowed(perms, "read", "Billing", "Invoice")
        assert not policy.is_allowed(perms, "write", "Orders")
        assert not policy.is_allowed(perms, "delete", "Orders")

    def test_editor_read_write(self) -> None:
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["editor"])
        assert policy.is_allowed(perms, "read", "Orders")
        assert policy.is_allowed(perms, "write", "Orders")
        assert not policy.is_allowed(perms, "delete", "Orders")

    def test_custom_role(self) -> None:
        cfg = RBACConfig(
            roles={
                "billing_admin": RoleDefinition(
                    permissions=["read:Billing", "write:Billing", "delete:Billing"],
                ),
            },
        )
        policy = RBACPolicy(cfg)
        perms = policy.permissions_for_roles(["billing_admin"])
        assert policy.is_allowed(perms, "read", "Billing")
        assert policy.is_allowed(perms, "write", "Billing", "Invoice")
        assert policy.is_allowed(perms, "delete", "Billing")
        assert not policy.is_allowed(perms, "read", "Orders")

    def test_custom_role_overrides_builtin(self) -> None:
        cfg = RBACConfig(
            roles={
                "viewer": RoleDefinition(permissions=["read:Orders"]),
            },
        )
        policy = RBACPolicy(cfg)
        perms = policy.permissions_for_roles(["viewer"])
        assert policy.is_allowed(perms, "read", "Orders")
        assert not policy.is_allowed(perms, "read", "Billing")

    def test_multiple_roles_merge(self) -> None:
        cfg = RBACConfig(
            roles={
                "orders_reader": RoleDefinition(permissions=["read:Orders"]),
                "billing_writer": RoleDefinition(permissions=["write:Billing"]),
            },
        )
        policy = RBACPolicy(cfg)
        perms = policy.permissions_for_roles(["orders_reader", "billing_writer"])
        assert policy.is_allowed(perms, "read", "Orders")
        assert policy.is_allowed(perms, "write", "Billing")
        assert not policy.is_allowed(perms, "write", "Orders")

    def test_check_raises(self) -> None:
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["viewer"])
        with pytest.raises(PermissionError, match="write:Orders"):
            policy.check(perms, "write", "Orders")

    def test_check_passes(self) -> None:
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["viewer"])
        policy.check(perms, "read", "Orders")  # should not raise

    def test_disabled_policy(self) -> None:
        cfg = RBACConfig(enabled=False)
        policy = RBACPolicy(cfg)
        assert policy.enabled is False

    def test_unknown_role(self) -> None:
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["nonexistent"])
        assert perms == []
        assert not policy.is_allowed(perms, "read", "Orders")

    def test_permissions_deduplication(self) -> None:
        cfg = RBACConfig(
            roles={
                "a": RoleDefinition(permissions=["read:Orders"]),
                "b": RoleDefinition(permissions=["read:Orders", "write:Orders"]),
            },
        )
        policy = RBACPolicy(cfg)
        perms = policy.permissions_for_roles(["a", "b"])
        assert perms.count("read:Orders") == 1
        assert "write:Orders" in perms


# ---------------------------------------------------------------------------
# require_domain_permission (contextvar-based)
# ---------------------------------------------------------------------------


class TestRequireDomainPermission:
    def test_unauthenticated_raises(self) -> None:
        from ninja_auth.agent_context import set_user_context
        from ninja_auth.context import ANONYMOUS_USER

        set_user_context(ANONYMOUS_USER)
        with pytest.raises(PermissionError, match="Authenticated"):
            require_domain_permission("read", "Orders")

    def test_missing_permission_raises(self) -> None:
        from ninja_auth.agent_context import set_user_context

        ctx = UserContext(user_id="u1", permissions=["read:Billing"])
        set_user_context(ctx)
        with pytest.raises(PermissionError, match="write:Orders"):
            require_domain_permission("write", "Orders")

    def test_granted_permission(self) -> None:
        from ninja_auth.agent_context import set_user_context

        ctx = UserContext(user_id="u1", permissions=["read:Orders"])
        set_user_context(ctx)
        require_domain_permission("read", "Orders")  # should not raise

    def test_domain_covers_entity(self) -> None:
        from ninja_auth.agent_context import set_user_context

        ctx = UserContext(user_id="u1", permissions=["read:Billing"])
        set_user_context(ctx)
        require_domain_permission("read", "Billing", entity="Invoice")  # should not raise


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------

RBAC_LOGGER = "ninja_auth.rbac"


class TestRBACLogging:
    def test_permission_denied_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Permission denial emits WARNING with action and domain."""
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["viewer"])

        with caplog.at_level(logging.WARNING, logger=RBAC_LOGGER):
            result = policy.is_allowed(perms, "write", "Orders")

        assert result is False
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and "Permission denied" in r.message]
        assert len(warning_records) == 1
        assert "write" in warning_records[0].message
        assert "Orders" in warning_records[0].message

    def test_permission_granted_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Permission grant does NOT emit WARNING (only DEBUG)."""
        policy = RBACPolicy()
        perms = policy.permissions_for_roles(["viewer"])

        with caplog.at_level(logging.WARNING, logger=RBAC_LOGGER):
            result = policy.is_allowed(perms, "read", "Orders")

        assert result is True
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 0
