"""Tests for OAuth2 strategy."""

import pytest
from unittest.mock import AsyncMock, patch

from ninja_auth.config import OAuth2ProviderConfig
from ninja_auth.errors import AuthenticationError
from ninja_auth.strategies.oauth2 import GITHUB_PRESET, GOOGLE_PRESET, OAuth2Strategy


def _make_config(**kwargs) -> OAuth2ProviderConfig:
    defaults = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "authorize_url": "https://provider.example.com/auth",
        "token_url": "https://provider.example.com/token",
        "userinfo_url": "https://provider.example.com/userinfo",
        "redirect_uri": "https://myapp.com/callback",
    }
    defaults.update(kwargs)
    return OAuth2ProviderConfig(**defaults)


def test_oauth2_authorization_url_with_explicit_state():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)
    url, state = strategy.get_authorization_url(state="abc123")
    assert "client_id=test-client-id" in url
    assert "state=abc123" in url
    assert "response_type=code" in url
    assert state == "abc123"
    assert url.startswith("https://provider.example.com/auth?")


def test_oauth2_authorization_url_always_has_state():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)
    url, state = strategy.get_authorization_url()
    assert "state=" in url
    assert len(state) > 16


def test_oauth2_authorization_url_generates_unique_states():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)
    _, state1 = strategy.get_authorization_url()
    _, state2 = strategy.get_authorization_url()
    assert state1 != state2


async def test_oauth2_exchange_code():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    mock_response = AsyncMock()
    mock_response.json = lambda: {"access_token": "at-123", "token_type": "bearer"}
    mock_response.raise_for_status = lambda: None

    with patch("ninja_auth.strategies.oauth2.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        tokens = await strategy.exchange_code("auth-code-xyz")
        assert tokens["access_token"] == "at-123"
        mock_client.post.assert_called_once()


async def test_oauth2_get_userinfo():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    mock_response = AsyncMock()
    mock_response.json = lambda: {"sub": "12345", "email": "user@example.com"}
    mock_response.raise_for_status = lambda: None

    with patch("ninja_auth.strategies.oauth2.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        userinfo = await strategy.get_userinfo("at-123")
        assert userinfo["sub"] == "12345"
        assert userinfo["email"] == "user@example.com"


async def test_oauth2_authenticate_with_code():
    config = _make_config()
    strategy = OAuth2Strategy("google", config)

    with (
        patch.object(strategy, "exchange_code", new_callable=AsyncMock) as mock_exchange,
        patch.object(strategy, "get_userinfo", new_callable=AsyncMock) as mock_userinfo,
    ):
        mock_exchange.return_value = {"access_token": "at-123"}
        mock_userinfo.return_value = {"sub": "u1", "email": "user@gmail.com"}

        ctx = await strategy.authenticate_with_code(
            "code-abc", expected_state="state-tok", received_state="state-tok"
        )
        assert ctx.user_id == "u1"
        assert ctx.email == "user@gmail.com"
        assert ctx.provider == "oauth2:google"
        assert ctx.access_token == "at-123"
        # access_token should NOT be in metadata
        assert "access_token" not in ctx.metadata


async def test_oauth2_state_mismatch_raises():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    with (
        patch.object(strategy, "exchange_code", new_callable=AsyncMock),
        patch.object(strategy, "get_userinfo", new_callable=AsyncMock),
    ):
        with pytest.raises(AuthenticationError, match="state mismatch"):
            await strategy.authenticate_with_code(
                "code-abc",
                expected_state="correct-state",
                received_state="wrong-state",
            )


async def test_oauth2_state_validation_passes():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    with (
        patch.object(strategy, "exchange_code", new_callable=AsyncMock) as mock_exchange,
        patch.object(strategy, "get_userinfo", new_callable=AsyncMock) as mock_userinfo,
    ):
        mock_exchange.return_value = {"access_token": "at-123"}
        mock_userinfo.return_value = {"sub": "u1", "email": "a@b.com"}

        ctx = await strategy.authenticate_with_code(
            "code-abc",
            expected_state="my-state",
            received_state="my-state",
        )
        assert ctx.user_id == "u1"


async def test_oauth2_github_id_fallback():
    """GitHub uses 'id' instead of 'sub' in userinfo."""
    config = _make_config()
    strategy = OAuth2Strategy("github", config)

    with (
        patch.object(strategy, "exchange_code", new_callable=AsyncMock) as mock_exchange,
        patch.object(strategy, "get_userinfo", new_callable=AsyncMock) as mock_userinfo,
    ):
        mock_exchange.return_value = {"access_token": "gh-token"}
        mock_userinfo.return_value = {"id": 99999, "email": "dev@github.com"}

        ctx = await strategy.authenticate_with_code(
            "gh-code", expected_state="s1", received_state="s1"
        )
        assert ctx.user_id == "99999"
        assert ctx.email == "dev@github.com"
        assert ctx.provider == "oauth2:github"


async def test_oauth2_empty_expected_state_raises():
    """Empty expected_state must be rejected."""
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    with pytest.raises(AuthenticationError, match="expected_state"):
        await strategy.authenticate_with_code(
            "code-abc", expected_state="", received_state="some-state"
        )


async def test_oauth2_empty_received_state_raises():
    """Empty received_state must be rejected."""
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    with pytest.raises(AuthenticationError, match="received_state"):
        await strategy.authenticate_with_code(
            "code-abc", expected_state="some-state", received_state=""
        )


async def test_oauth2_both_states_empty_raises():
    """Both states empty must be rejected."""
    config = _make_config()
    strategy = OAuth2Strategy("test", config)

    with pytest.raises(AuthenticationError):
        await strategy.authenticate_with_code(
            "code-abc", expected_state="", received_state=""
        )


def test_google_preset_urls():
    assert "google" in GOOGLE_PRESET.authorize_url
    assert "google" in GOOGLE_PRESET.token_url


def test_github_preset_urls():
    assert "github" in GITHUB_PRESET.authorize_url
    assert "github" in GITHUB_PRESET.token_url
