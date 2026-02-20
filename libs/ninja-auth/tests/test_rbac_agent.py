"""Tests for RBAC enforcement in agent context (require_domain_access)."""

from __future__ import annotations

import pytest
from ninja_auth.agent_context import require_domain_access, set_user_context
from ninja_auth.context import ANONYMOUS_USER, UserContext


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
