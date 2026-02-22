"""OAuth2 strategy with support for Google, GitHub, and custom providers."""

from __future__ import annotations

import hmac
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from ninja_auth.config import OAuth2ProviderConfig
from ninja_auth.context import UserContext
from ninja_auth.errors import AuthenticationError

# Well-known provider presets
GOOGLE_PRESET = OAuth2ProviderConfig(
    client_id="",
    client_secret="",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
    scopes=["openid", "email", "profile"],
)

GITHUB_PRESET = OAuth2ProviderConfig(
    client_id="",
    client_secret="",
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    userinfo_url="https://api.github.com/user",
    scopes=["read:user", "user:email"],
)


class OAuth2Strategy:
    """Handles OAuth2 authorization code flow for external identity providers."""

    def __init__(self, provider_name: str, config: OAuth2ProviderConfig) -> None:
        self.provider_name = provider_name
        self.config = config

    def get_authorization_url(self, state: str | None = None) -> tuple[str, str]:
        """Build the URL to redirect the user to for OAuth2 authorization.

        Always generates a cryptographic ``state`` token for CSRF protection.
        If *state* is provided it is used as-is; otherwise a random token is
        generated.

        Returns:
            A ``(url, state)`` tuple. The caller must store ``state`` in the
            session so it can be verified in the callback.
        """
        if not state:
            state = secrets.token_urlsafe(32)
        params: dict[str, str] = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "state": state,
        }
        url = f"{self.config.authorize_url}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for tokens."""
        async with httpx.AsyncClient() as client:
            headers = {"Accept": "application/json"}
            resp = await client.post(
                self.config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                },
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch user profile from the provider's userinfo endpoint."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.config.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def authenticate_with_code(self, code: str, *, expected_state: str, received_state: str) -> UserContext:
        """Full OAuth2 flow: exchange code -> fetch userinfo -> return context.

        Both ``expected_state`` and ``received_state`` are **required** to
        enforce CSRF protection.  The caller must store the state token
        returned by :meth:`get_authorization_url` in the user's session and
        pass it back here alongside the value from the OAuth2 callback query
        string.

        Args:
            code: The authorization code from the provider callback.
            expected_state: The state token stored in the user's session.
            received_state: The state token returned in the callback URL.

        Raises:
            AuthenticationError: If state validation fails or state values
                are empty.
        """
        if not expected_state or not received_state:
            raise AuthenticationError(
                "OAuth2 state validation requires both expected_state and "
                "received_state. Ensure the state token from "
                "get_authorization_url() is stored in the session and "
                "forwarded on callback."
            )
        if not hmac.compare_digest(expected_state, received_state):
            raise AuthenticationError("OAuth2 state mismatch — possible CSRF attack.")

        tokens = await self.exchange_code(code)
        access_token = tokens.get("access_token", "")
        userinfo = await self.get_userinfo(access_token)

        # Normalize across providers
        user_id = str(userinfo.get("sub") or userinfo.get("id", ""))
        email = userinfo.get("email")

        return UserContext(
            user_id=user_id,
            email=email,
            roles=[],
            provider=f"oauth2:{self.provider_name}",
            metadata={"userinfo": userinfo},
            _access_token=access_token,
        )
