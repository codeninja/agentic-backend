"""FastAPI router factory for OAuth2 authorization flows."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from ninja_auth.config import AuthConfig
from ninja_auth.errors import AuthenticationError
from ninja_auth.state_store import InMemoryOAuthStateStore, OAuthStateStore
from ninja_auth.strategies.identity import IdentityStrategy
from ninja_auth.strategies.oauth2 import OAuth2Strategy

logger = logging.getLogger(__name__)


def create_auth_router(
    config: AuthConfig,
    *,
    state_store: OAuthStateStore | None = None,
    identity_strategy: IdentityStrategy | None = None,
    prefix: str = "/auth",
    state_ttl_seconds: int = 300,
) -> APIRouter:
    """Create a FastAPI router that exposes OAuth2 authorization endpoints.

    The returned router provides two endpoints per configured OAuth2 provider:

    - ``GET /auth/{provider}/authorize`` — Generates the authorization URL,
      stores a CSRF state token, and redirects the user to the provider.
    - ``GET /auth/{provider}/callback`` — Validates the state token, exchanges
      the authorization code for tokens, issues a JWT, and returns it.

    The app mounting this router should ensure that ``/auth/*`` paths are in
    :attr:`AuthConfig.public_paths` so the ``AuthGateway`` middleware does not
    require authentication on these routes.

    Args:
        config: The auth configuration containing OAuth2 provider definitions
            and identity settings.
        state_store: An :class:`OAuthStateStore` implementation for persisting
            CSRF state tokens. Defaults to :class:`InMemoryOAuthStateStore`.
        identity_strategy: An :class:`IdentityStrategy` instance used to issue
            JWTs after successful OAuth2 authentication. If ``None``, one is
            created from ``config.identity``.
        prefix: URL prefix for the router (default ``/auth``).
        state_ttl_seconds: TTL for CSRF state tokens in seconds (default 300).

    Returns:
        A configured :class:`fastapi.APIRouter`.
    """
    router = APIRouter(prefix=prefix, tags=["auth"])

    _state_store = state_store or InMemoryOAuthStateStore()
    _identity = identity_strategy or IdentityStrategy(config.identity)

    # Build OAuth2Strategy instances for each configured provider
    _strategies: dict[str, OAuth2Strategy] = {
        name: OAuth2Strategy(name, provider_config) for name, provider_config in config.oauth2_providers.items()
    }

    def _get_strategy(provider: str) -> OAuth2Strategy:
        """Look up an OAuth2 strategy by provider name or raise 404."""
        strategy = _strategies.get(provider)
        if strategy is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown OAuth2 provider: {provider}",
            )
        return strategy

    @router.get("/{provider}/authorize")
    async def authorize(provider: str) -> RedirectResponse:
        """Generate an authorization URL and redirect the user to the OAuth2 provider.

        Stores a cryptographic state token in the state store for CSRF validation
        on callback.
        """
        strategy = _get_strategy(provider)
        url, state = strategy.get_authorization_url()

        await _state_store.save_state(
            state,
            {"provider": provider},
            ttl_seconds=state_ttl_seconds,
        )

        logger.info("OAuth2 authorize: redirecting to provider=%s", provider)
        return RedirectResponse(url=url, status_code=302)

    @router.get("/{provider}/callback")
    async def callback(
        provider: str,
        code: str = Query(..., description="Authorization code from the OAuth2 provider"),
        state: str = Query(..., description="CSRF state token from the authorization request"),
    ) -> JSONResponse:
        """Handle the OAuth2 provider callback after user authorization.

        Validates the CSRF state token, exchanges the authorization code for
        user information, issues a JWT, and returns it as a JSON response.
        """
        strategy = _get_strategy(provider)

        # Retrieve and validate state
        stored_metadata = await _state_store.get_state(state)
        if stored_metadata is None:
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired OAuth2 state token",
            )

        # Delete state to prevent replay
        await _state_store.delete_state(state)

        # Exchange code for user context
        try:
            user_ctx = await strategy.authenticate_with_code(
                code,
                expected_state=state,
                received_state=state,
            )
        except AuthenticationError as exc:
            logger.error(
                "OAuth2 code exchange failed: provider=%s error=%s",
                provider,
                str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            logger.error(
                "OAuth2 code exchange unexpected error: provider=%s error=%s",
                provider,
                str(exc),
            )
            raise HTTPException(
                status_code=502,
                detail="Failed to complete OAuth2 code exchange",
            ) from exc

        # Issue JWT so subsequent requests use bearer auth
        token = _identity.issue_token(user_ctx)

        logger.info(
            "OAuth2 callback success: provider=%s user_id=%s email=%s",
            provider,
            user_ctx.user_id,
            user_ctx.email,
        )
        return JSONResponse(
            content={
                "access_token": token,
                "token_type": "bearer",
                "user_id": user_ctx.user_id,
                "email": user_ctx.email,
            }
        )

    return router
