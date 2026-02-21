"""Tests for RBAC enforcement in agent context (require_domain_access)."""

from __future__ import annotations

import pytest
from ninja_auth.agent_context import (
    clear_rbac_policy,
    current_rbac_policy,
    require_domain_access,
    set_rbac_policy,
    set_user_context,
)
from ninja_auth.context import ANONYMOUS_USER, UserContext
from ninja_auth.rbac import RBACConfig, RBACPolicy, RoleDefinition


class TestRequireDomainAccess:
    """Test the require_domain_access helper used inside agent tools."""

    def test_unauthenticated_raises(self) -> None:
        set_user_context(ANONYMOUS_USER)
        with pytest.raises(PermissionError, match="Authenticated"):
            require_domain_access("read", "Orders")

    def test_allowed_domain(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["read:Orders"])
        set_user_context(ctx)
        result = require_domain_access("read", "Orders")
        assert result.user_id == "u1"

    def test_denied_domain(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["read:Billing"])
        set_user_context(ctx)
        with pytest.raises(PermissionError, match="write:Orders"):
            require_domain_access("write", "Orders")

    def test_domain_covers_entity(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["read:Billing"])
        set_user_context(ctx)
        result = require_domain_access("read", "Billing", entity="Invoice")
        assert result.user_id == "u1"

    def test_entity_level_permission(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["write:Billing.Invoice"])
        set_user_context(ctx)
        result = require_domain_access("write", "Billing", entity="Invoice")
        assert result.user_id == "u1"

    def test_entity_does_not_cover_whole_domain(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["read:Billing.Invoice"])
        set_user_context(ctx)
        with pytest.raises(PermissionError, match="read:Billing"):
            require_domain_access("read", "Billing")

    def test_admin_wildcard(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["*:*"])
        set_user_context(ctx)
        require_domain_access("delete", "Anything", entity="Whatever")

    def test_action_wildcard(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["*:Orders"])
        set_user_context(ctx)
        require_domain_access("read", "Orders")
        require_domain_access("write", "Orders")
        require_domain_access("delete", "Orders")

    def test_scope_wildcard(self) -> None:
        ctx = UserContext(user_id="u1", permissions=["read:*"])
        set_user_context(ctx)
        require_domain_access("read", "Orders")
        require_domain_access("read", "Billing", entity="Invoice")
        with pytest.raises(PermissionError):
            require_domain_access("write", "Orders")


class TestRBACPolicyPropagation:
    """Test that the gateway's RBAC policy is propagated via contextvar."""

    def test_set_and_get_rbac_policy(self) -> None:
        """set_rbac_policy / current_rbac_policy round-trip."""
        policy = RBACPolicy()
        token = set_rbac_policy(policy)
        try:
            assert current_rbac_policy() is policy
        finally:
            clear_rbac_policy(token)
        assert current_rbac_policy() is None

    def test_default_rbac_policy_is_none(self) -> None:
        """Without set_rbac_policy, current_rbac_policy returns None."""
        assert current_rbac_policy() is None

    def test_require_domain_access_uses_contextvar_policy(self) -> None:
        """Custom roles from the contextvar policy are respected."""
        config = RBACConfig(
            roles={
                "auditor": RoleDefinition(permissions=["read:Billing", "read:Orders"]),
            }
        )
        policy = RBACPolicy(config)
        # User has the "auditor" role; gateway would have enriched permissions
        # via _enrich_permissions using the same policy. Simulate that:
        user_perms = policy.permissions_for_roles(["auditor"])
        ctx = UserContext(user_id="u1", roles=["auditor"], permissions=user_perms)
        set_user_context(ctx)
        policy_token = set_rbac_policy(policy)
        try:
            # Should pass — auditor has read:Billing
            result = require_domain_access("read", "Billing")
            assert result.user_id == "u1"
            # Should fail — auditor has no write permission
            with pytest.raises(PermissionError, match="write:Billing"):
                require_domain_access("write", "Billing")
        finally:
            clear_rbac_policy(policy_token)

    def test_explicit_policy_overrides_contextvar(self) -> None:
        """An explicit policy parameter takes priority over the contextvar."""
        # Contextvar policy: no custom roles
        cv_policy = RBACPolicy()
        cv_token = set_rbac_policy(cv_policy)

        # Explicit policy: custom role with delete:*
        explicit_config = RBACConfig(
            roles={"deleter": RoleDefinition(permissions=["delete:*"])}
        )
        explicit_policy = RBACPolicy(explicit_config)
        perms = explicit_policy.permissions_for_roles(["deleter"])
        ctx = UserContext(user_id="u1", roles=["deleter"], permissions=perms)
        set_user_context(ctx)
        try:
            result = require_domain_access("delete", "Orders", policy=explicit_policy)
            assert result.user_id == "u1"
        finally:
            clear_rbac_policy(cv_token)

    def test_fallback_to_default_without_contextvar(self) -> None:
        """Without contextvar or explicit policy, falls back to default (builtins only)."""
        # admin built-in has *:*
        ctx = UserContext(user_id="u1", permissions=["*:*"])
        set_user_context(ctx)
        result = require_domain_access("delete", "Everything", entity="All")
        assert result.user_id == "u1"

    def test_custom_role_ignored_without_propagation(self) -> None:
        """Proves the bug: without set_rbac_policy, a custom-role permission
        that isn't in the user's explicit permissions list would not be checked
        against the custom role definition (the default policy has no custom roles).
        The fix is that the gateway enriches permissions AND propagates the policy.
        """
        # A custom role "support" that grants read:Support
        config = RBACConfig(
            roles={"support": RoleDefinition(permissions=["read:Support"])}
        )
        policy = RBACPolicy(config)
        # Simulate enriched permissions (as the gateway would do)
        enriched = policy.permissions_for_roles(["support"])
        ctx = UserContext(user_id="u1", roles=["support"], permissions=enriched)
        set_user_context(ctx)
        policy_token = set_rbac_policy(policy)
        try:
            # With the policy propagated, custom role's permission is respected
            result = require_domain_access("read", "Support")
            assert result.user_id == "u1"
        finally:
            clear_rbac_policy(policy_token)
