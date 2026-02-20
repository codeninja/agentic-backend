"""Tests that all public API symbols are importable."""


def test_ninja_auth_imports():
    import ninja_auth

    assert ninja_auth is not None


def test_public_api_exports():
    from ninja_auth import (
        ANONYMOUS_USER,
        ApiKeyStrategy,
        AuthConfig,
        AuthGateway,
        BearerStrategy,
        IdentityStrategy,
        OAuth2Strategy,
        UserContext,
        get_user_context,
    )

    assert all(
        [
            ANONYMOUS_USER,
            ApiKeyStrategy,
            AuthConfig,
            AuthGateway,
            BearerStrategy,
            IdentityStrategy,
            OAuth2Strategy,
            UserContext,
            get_user_context,
        ]
    )
