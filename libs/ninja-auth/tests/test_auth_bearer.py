"""Tests for Bearer (JWT) strategy."""

import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from ninja_auth.config import BearerConfig
from ninja_auth.strategies.bearer import BearerStrategy
from starlette.testclient import TestClient

SECRET = "test-secret-key-that-is-at-least-32-bytes-long"

# Future expiry for valid tokens
_FUTURE_EXP = datetime.now(timezone.utc) + timedelta(hours=1)


def _make_token(payload: dict, secret: str = SECRET, algorithm: str = "HS256") -> str:
    # Auto-add a future exp if not explicitly set
    if "exp" not in payload:
        payload = {**payload, "exp": _FUTURE_EXP}
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_bearer_valid_token():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1", "email": "a@b.com", "roles": ["admin"]})
    ctx = strategy.validate_token(token)
    assert ctx is not None
    assert ctx.user_id == "user1"
    assert ctx.email == "a@b.com"
    assert "admin" in ctx.roles
    assert ctx.provider == "bearer"


def test_bearer_expired_token():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token(
        {
            "sub": "user1",
            "exp": datetime(2020, 1, 1, tzinfo=timezone.utc),
        }
    )
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_rejects_token_missing_exp():
    """JWT without an 'exp' claim must be rejected."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    # Explicitly create token without exp
    token = jwt.encode({"sub": "user1"}, SECRET, algorithm="HS256")
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_invalid_signature():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1"}, secret="wrong-secret-key-that-is-32-bytes-long!")
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_invalid_token_string():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    ctx = strategy.validate_token("not.a.valid.jwt")
    assert ctx is None


def test_bearer_with_issuer_validation():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256", issuer="https://auth.example.com")
    strategy = BearerStrategy(config)

    # Valid issuer
    token = _make_token({"sub": "u1", "iss": "https://auth.example.com"})
    ctx = strategy.validate_token(token)
    assert ctx is not None

    # Wrong issuer
    token = _make_token({"sub": "u1", "iss": "https://evil.com"})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_with_audience_validation():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256", audience="my-app")
    strategy = BearerStrategy(config)

    token = _make_token({"sub": "u1", "aud": "my-app"})
    ctx = strategy.validate_token(token)
    assert ctx is not None

    token = _make_token({"sub": "u1", "aud": "other-app"})
    ctx = strategy.validate_token(token)
    assert ctx is None


async def test_bearer_authenticate_from_header():
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)

    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def homepage(request):
        ctx = await strategy.authenticate(request)
        if ctx:
            return JSONResponse({"user_id": ctx.user_id})
        return JSONResponse({"user_id": None})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    token = _make_token({"sub": "user1"})
    resp = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["user_id"] == "user1"

    # No header
    resp = client.get("/")
    assert resp.json()["user_id"] is None


async def test_bearer_case_insensitive_prefix():
    """The 'Bearer' prefix in the Authorization header should be case-insensitive."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)

    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def homepage(request):
        ctx = await strategy.authenticate(request)
        if ctx:
            return JSONResponse({"user_id": ctx.user_id})
        return JSONResponse({"user_id": None})

    app = Starlette(routes=[Route("/", homepage)])
    client = TestClient(app)

    token = _make_token({"sub": "user1"})

    for prefix in ("Bearer", "bearer", "BEARER", "bEaReR"):
        resp = client.get("/", headers={"Authorization": f"{prefix} {token}"})
        assert resp.json()["user_id"] == "user1", f"Failed for prefix: {prefix}"


def test_bearer_rejects_token_missing_sub():
    """JWT without a 'sub' claim must be rejected (issue #81)."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"email": "a@b.com", "roles": ["admin"]})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_rejects_token_with_empty_sub():
    """JWT with an empty-string 'sub' claim must be rejected (issue #81)."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "", "email": "a@b.com"})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_rejects_token_with_whitespace_sub():
    """JWT with a whitespace-only 'sub' claim must be rejected."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "   ", "email": "a@b.com"})
    ctx = strategy.validate_token(token)
    assert ctx is None


def test_bearer_metadata_excludes_raw_payload():
    """Metadata must only contain safe standard claims, not the full JWT payload."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1", "custom_field": "value", "iss": "https://auth.example.com"})
    ctx = strategy.validate_token(token)
    assert ctx is not None
    # Raw payload must NOT be exposed
    assert "claims" not in ctx.metadata
    assert "custom_field" not in ctx.metadata
    assert "sub" not in ctx.metadata
    # Safe standard claims ARE forwarded
    assert "iss" in ctx.metadata
    assert ctx.metadata["iss"] == "https://auth.example.com"
    assert "exp" in ctx.metadata


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------

BEARER_LOGGER = "ninja_auth.strategies.bearer"


def test_bearer_expired_token_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Expired token emits WARNING with reason."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1", "exp": datetime(2020, 1, 1, tzinfo=timezone.utc)})

    with caplog.at_level(logging.WARNING, logger=BEARER_LOGGER):
        ctx = strategy.validate_token(token)

    assert ctx is None
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) >= 1
    assert "expired" in warning_records[0].message.lower()


def test_bearer_invalid_signature_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    """Invalid signature emits ERROR with reason."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)
    token = _make_token({"sub": "user1"}, secret="wrong-secret-key-that-is-32-bytes-long!")

    with caplog.at_level(logging.ERROR, logger=BEARER_LOGGER):
        ctx = strategy.validate_token(token)

    assert ctx is None
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) >= 1


def test_bearer_malformed_token_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    """Malformed token emits ERROR."""
    config = BearerConfig(secret_key=SECRET, algorithm="HS256")
    strategy = BearerStrategy(config)

    with caplog.at_level(logging.ERROR, logger=BEARER_LOGGER):
        ctx = strategy.validate_token("not.a.valid.jwt")

    assert ctx is None
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) >= 1


# ---------------------------------------------------------------------------
# Claims validation tests (issue #148)
# ---------------------------------------------------------------------------


class TestEmailValidation:
    """Validate that the email claim is checked for format."""

    def _strategy(self) -> BearerStrategy:
        return BearerStrategy(BearerConfig(secret_key=SECRET, algorithm="HS256"))

    def test_valid_email(self):
        token = _make_token({"sub": "u1", "email": "user@example.com"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.email == "user@example.com"

    def test_email_none_when_absent(self):
        token = _make_token({"sub": "u1"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.email is None

    @pytest.mark.parametrize(
        "bad_email",
        [
            "not-an-email",
            "missing@tld",
            "@no-local.com",
            "spaces in@email.com",
            "",
            123,
            True,
        ],
    )
    def test_invalid_email_becomes_none(self, bad_email):
        token = _make_token({"sub": "u1", "email": bad_email})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.email is None


class TestRolesValidation:
    """Validate that the roles claim is a list of non-empty strings."""

    def _strategy(self) -> BearerStrategy:
        return BearerStrategy(BearerConfig(secret_key=SECRET, algorithm="HS256"))

    def test_valid_roles(self):
        token = _make_token({"sub": "u1", "roles": ["admin", "editor"]})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.roles == ["admin", "editor"]

    def test_empty_roles_list(self):
        token = _make_token({"sub": "u1", "roles": []})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.roles == []

    def test_roles_absent_defaults_to_empty(self):
        token = _make_token({"sub": "u1"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.roles == []

    def test_non_list_roles_ignored(self):
        token = _make_token({"sub": "u1", "roles": "admin"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.roles == []

    def test_non_string_entries_dropped(self):
        token = _make_token({"sub": "u1", "roles": ["admin", 42, None, "viewer"]})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.roles == ["admin", "viewer"]

    def test_empty_string_entries_dropped(self):
        token = _make_token({"sub": "u1", "roles": ["admin", "", "  "]})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.roles == ["admin"]


class TestPermissionsValidation:
    """Validate that permissions follow the action:scope format."""

    def _strategy(self) -> BearerStrategy:
        return BearerStrategy(BearerConfig(secret_key=SECRET, algorithm="HS256"))

    def test_valid_permissions(self):
        token = _make_token({"sub": "u1", "permissions": ["read:Orders", "write:Billing.Invoice", "*:*"]})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.permissions == ["read:Orders", "write:Billing.Invoice", "*:*"]

    def test_permissions_absent_defaults_to_empty(self):
        token = _make_token({"sub": "u1"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.permissions == []

    def test_non_list_permissions_ignored(self):
        token = _make_token({"sub": "u1", "permissions": "read:Orders"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.permissions == []

    @pytest.mark.parametrize(
        "bad_perm",
        [
            "no-colon",
            "read:",
            ":scope",
            "",
            "read:scope with spaces",
            123,
            None,
        ],
    )
    def test_invalid_permission_entries_dropped(self, bad_perm):
        token = _make_token({"sub": "u1", "permissions": ["read:Orders", bad_perm]})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.permissions == ["read:Orders"]


class TestAlgorithmConfusion:
    """Verify that algorithm confusion attacks are blocked at config time (issue #172)."""

    def test_cannot_create_hmac_config_with_public_key(self):
        """An attacker cannot configure HS256 + public_key to forge tokens."""
        with pytest.raises(ValueError, match="algorithm confusion"):
            BearerConfig(algorithm="HS256", secret_key="secret", public_key="rsa-pub-key")

    def test_cannot_create_asymmetric_config_with_secret_key(self):
        """Asymmetric algorithms must not accept secret_key."""
        with pytest.raises(ValueError, match="secret_key.*also set"):
            BearerConfig(algorithm="RS256", secret_key="secret", public_key="rsa-pub-key")


class TestMetadataSafety:
    """Ensure raw JWT payload is not leaked through metadata."""

    def _strategy(self) -> BearerStrategy:
        return BearerStrategy(BearerConfig(secret_key=SECRET, algorithm="HS256"))

    def test_sensitive_claims_excluded(self):
        token = _make_token(
            {
                "sub": "u1",
                "email": "a@b.com",
                "roles": ["admin"],
                "permissions": ["read:*"],
                "secret_data": "s3cret",
            }
        )
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert "secret_data" not in ctx.metadata
        assert "sub" not in ctx.metadata
        assert "email" not in ctx.metadata
        assert "roles" not in ctx.metadata
        assert "permissions" not in ctx.metadata

    def test_safe_standard_claims_forwarded(self):
        token = _make_token({"sub": "u1", "iss": "https://auth.test", "jti": "abc-123"})
        ctx = self._strategy().validate_token(token)
        assert ctx is not None
        assert ctx.metadata.get("iss") == "https://auth.test"
        assert ctx.metadata.get("jti") == "abc-123"
        assert "exp" in ctx.metadata
