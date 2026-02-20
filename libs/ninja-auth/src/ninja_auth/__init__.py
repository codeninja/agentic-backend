"""Ninja Auth — pluggable authentication gateway."""

from ninja_auth.agent_context import (
    clear_user_context,
    current_user_context,
    require_permission,
    require_role,
    require_user_context,
    set_user_context,
)
from ninja_auth.config import AuthConfig
from ninja_auth.context import ANONYMOUS_USER, UserContext
from ninja_auth.gateway import AuthGateway, get_user_context
from ninja_auth.strategies.apikey import ApiKeyStrategy
from ninja_auth.strategies.bearer import BearerStrategy
from ninja_auth.strategies.identity import IdentityStrategy
from ninja_auth.strategies.oauth2 import OAuth2Strategy

__all__ = [
    "ANONYMOUS_USER",
    "ApiKeyStrategy",
    "AuthConfig",
    "AuthGateway",
    "BearerStrategy",
    "IdentityStrategy",
    "OAuth2Strategy",
    "UserContext",
    "clear_user_context",
    "current_user_context",
    "get_user_context",
    "require_permission",
    "require_role",
    "require_user_context",
    "set_user_context",
]
