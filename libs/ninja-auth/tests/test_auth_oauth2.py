"""Tests for OAuth2 strategy."""

from unittest.mock import AsyncMock, patch

from ninja_auth.config import OAuth2ProviderConfig
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


def test_oauth2_authorization_url():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)
    url = strategy.get_authorization_url(state="abc123")
    assert "client_id=test-client-id" in url
    assert "state=abc123" in url
    assert "response_type=code" in url
    assert url.startswith("https://provider.example.com/auth?")


def test_oauth2_authorization_url_no_state():
    config = _make_config()
    strategy = OAuth2Strategy("test", config)
    url = strategy.get_authorization_url()
    assert "state" not in url


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

        ctx = await strategy.authenticate_with_code("code-abc")
        assert ctx.user_id == "u1"
        assert ctx.email == "user@gmail.com"
        assert ctx.provider == "oauth2:google"
        assert ctx.metadata["access_token"] == "at-123"


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

        ctx = await strategy.authenticate_with_code("gh-code")
        assert ctx.user_id == "99999"
        assert ctx.email == "dev@github.com"
        assert ctx.provider == "oauth2:github"


def test_google_preset_urls():
    assert "google" in GOOGLE_PRESET.authorize_url
    assert "google" in GOOGLE_PRESET.token_url


def test_github_preset_urls():
    assert "github" in GITHUB_PRESET.authorize_url
    assert "github" in GITHUB_PRESET.token_url
