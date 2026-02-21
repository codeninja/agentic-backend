"""Tests for UserContext model."""

import json

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


# --- Tests for UserContext serialization redaction (issue #56) ---


class TestUserContextRedaction:
    def test_access_token_not_in_dict(self):
        ctx = UserContext(
            user_id="u1",
            metadata={"userinfo": {"name": "Test"}},
            _access_token="secret-token",
        )
        d = ctx.model_dump()
        assert "access_token" not in d
        assert "_access_token" not in d

    def test_access_token_accessible_via_property(self):
        ctx = UserContext(user_id="u1", _access_token="secret-token")
        assert ctx.access_token == "secret-token"

    def test_access_token_not_in_json(self):
        ctx = UserContext(
            user_id="u1",
            metadata={"access_token": "should-be-redacted"},
            _access_token="also-secret",
        )
        j = ctx.model_dump_json()
        data = json.loads(j)
        assert data["metadata"]["access_token"] == "***REDACTED***"
        assert "also-secret" not in j

    def test_access_token_not_in_repr(self):
        ctx = UserContext(
            user_id="u1",
            metadata={"access_token": "secret123"},
            _access_token="secret456",
        )
        r = repr(ctx)
        assert "secret123" not in r
        assert "secret456" not in r

    def test_sensitive_metadata_keys_redacted(self):
        ctx = UserContext(
            user_id="u1",
            metadata={
                "password": "mysecretpassword",
                "api_key": "key123",
                "token": "tok456",
                "name": "visible",
            },
        )
        d = ctx.model_dump()
        assert d["metadata"]["password"] == "***REDACTED***"
        assert d["metadata"]["api_key"] == "***REDACTED***"
        assert d["metadata"]["token"] == "***REDACTED***"
        assert d["metadata"]["name"] == "visible"

    def test_nested_sensitive_metadata_redacted(self):
        ctx = UserContext(
            user_id="u1",
            metadata={"oauth": {"access_token": "secret", "scope": "openid"}},
        )
        d = ctx.model_dump()
        assert d["metadata"]["oauth"]["access_token"] == "***REDACTED***"
        assert d["metadata"]["oauth"]["scope"] == "openid"
