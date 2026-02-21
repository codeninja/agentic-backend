"""Ninja Auth — pluggable authentication gateway with RBAC."""

from ninja_auth.agent_context import (
    clear_rbac_policy,
    clear_user_context,
    current_rbac_policy,
    current_user_context,
    require_domain_access,
    require_permission,
    require_role,
    require_user_context,
    set_rbac_policy,
    set_user_context,
)
from ninja_auth.config import AuthConfig
from ninja_auth.context import ANONYMOUS_USER, UserContext
from ninja_auth.errors import AuthenticationError
from ninja_auth.gateway import AuthGateway, get_user_context
from ninja_auth.rate_limiter import RateLimitConfig, RateLimiter
from ninja_auth.rbac import (
    BUILTIN_ROLES,
    Action,
    RBACConfig,
    RBACPolicy,
    RoleDefinition,
    permission_matches,
    require_domain_permission,
)
from ninja_auth.strategies.apikey import ApiKeyStrategy
from ninja_auth.strategies.bearer import BearerStrategy
from ninja_auth.strategies.identity import IdentityStrategy
from ninja_auth.strategies.oauth2 import OAuth2Strategy
from ninja_auth.revocation import InMemoryRevocationStore, TokenRevocationStore
from ninja_auth.user_store import InMemoryUserStore, UserStore

__all__ = [
    "ANONYMOUS_USER",
    "Action",
    "ApiKeyStrategy",
    "AuthConfig",
    "AuthenticationError",
    "AuthGateway",
    "BearerStrategy",
    "BUILTIN_ROLES",
    "IdentityStrategy",
    "InMemoryRevocationStore",
    "InMemoryUserStore",
    "OAuth2Strategy",
    "RateLimitConfig",
    "RateLimiter",
    "RBACConfig",
    "RBACPolicy",
    "RoleDefinition",
    "UserContext",
    "UserStore",
    "clear_rbac_policy",
    "clear_user_context",
    "current_rbac_policy",
    "current_user_context",
    "get_user_context",
    "permission_matches",
    "require_domain_access",
    "require_domain_permission",
    "require_permission",
    "require_role",
    "require_user_context",
    "set_rbac_policy",
    "set_user_context",
    "TokenRevocationStore",
]
