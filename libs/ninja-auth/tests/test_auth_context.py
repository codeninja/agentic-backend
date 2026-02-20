"""Tests for UserContext model."""

from ninja_auth.context import ANONYMOUS_USER, UserContext


def test_user_context_basic():
    ctx = UserContext(user_id="u1", email="a@b.com", roles=["admin"], provider="bearer")
    assert ctx.user_id == "u1"
    assert ctx.email == "a@b.com"
    assert ctx.provider == "bearer"


def test_user_context_is_authenticated():
    ctx = UserContext(user_id="u1")
    assert ctx.is_authenticated is True


def test_user_context_anonymous_not_authenticated():
    assert ANONYMOUS_USER.is_authenticated is False
    assert ANONYMOUS_USER.provider == "anonymous"


def test_user_context_has_role():
    ctx = UserContext(user_id="u1", roles=["admin", "editor"])
    assert ctx.has_role("admin") is True
    assert ctx.has_role("viewer") is False


def test_user_context_has_permission():
    ctx = UserContext(user_id="u1", permissions=["read:orders", "write:orders"])
    assert ctx.has_permission("read:orders") is True
    assert ctx.has_permission("delete:orders") is False


def test_user_context_defaults():
    ctx = UserContext(user_id="u1")
    assert ctx.roles == []
    assert ctx.permissions == []
    assert ctx.metadata == {}
    assert ctx.provider == "unknown"
    assert ctx.email is None
