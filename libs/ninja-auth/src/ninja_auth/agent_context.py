"""Bridge for injecting authenticated UserContext into ADK agent tool execution.

Uses contextvars so that UserContext set at the request level is accessible
anywhere in the same async call stack — including deep inside agent tool functions.

Usage at the request boundary (FastAPI middleware/endpoint):

    from ninja_auth.agent_context import set_user_context, clear_user_context

    user_ctx = get_user_context(request)
    token = set_user_context(user_ctx)
    try:
        await run_agent(...)
    finally:
        clear_user_context(token)

Usage inside an ADK agent tool:

    from ninja_auth.agent_context import current_user_context, require_user_context

    def my_tool(**kwargs):
        user = require_user_context()  # raises if not authenticated
        # ... use user.user_id, user.roles, etc.

RBAC-aware domain/entity checks inside agent tools:

    from ninja_auth.agent_context import require_domain_access

    def list_orders(**kwargs):
        require_domain_access("read", "Orders")  # raises PermissionError if denied
        ...

    def delete_invoice(**kwargs):
        require_domain_access("delete", "Billing", entity="Invoice")
        ...

RBAC policy propagation (set by AuthGateway middleware):

    from ninja_auth.agent_context import set_rbac_policy, clear_rbac_policy

    policy = RBACPolicy(config)
    token = set_rbac_policy(policy)
    try:
        await run_agent(...)
    finally:
        clear_rbac_policy(token)
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

from ninja_auth.context import ANONYMOUS_USER, UserContext

if TYPE_CHECKING:
    from ninja_auth.rbac import RBACPolicy

_user_context_var: ContextVar[UserContext] = ContextVar("user_context", default=ANONYMOUS_USER)
_rbac_policy_var: ContextVar[RBACPolicy | None] = ContextVar("rbac_policy", default=None)


def set_user_context(ctx: UserContext) -> Token[UserContext]:
    """Set the authenticated user context for the current async task.

    Returns a token that can be passed to ``clear_user_context`` to restore
    the previous value.
    """
    return _user_context_var.set(ctx)


def clear_user_context(token: Token[UserContext]) -> None:
    """Restore the previous user context (typically ANONYMOUS_USER)."""
    _user_context_var.reset(token)


def current_user_context() -> UserContext:
    """Return the current user context (may be ANONYMOUS_USER)."""
    return _user_context_var.get()


def require_user_context() -> UserContext:
    """Return the current user context or raise if not authenticated.

    Use this inside agent tools that require authentication.

    Raises:
        PermissionError: If no authenticated user context is set.
    """
    ctx = _user_context_var.get()
    if not ctx.is_authenticated:
        raise PermissionError("Authenticated user context required")
    return ctx


def set_rbac_policy(policy: RBACPolicy) -> Token[RBACPolicy | None]:
    """Set the RBAC policy for the current async task.

    Called by ``AuthGateway`` so that agent tools use the gateway's configured
    policy (with custom roles) instead of a bare default.

    Returns a token that can be passed to ``clear_rbac_policy`` to restore
    the previous value.
    """
    return _rbac_policy_var.set(policy)


def clear_rbac_policy(token: Token[RBACPolicy | None]) -> None:
    """Restore the previous RBAC policy (typically None)."""
    _rbac_policy_var.reset(token)


def current_rbac_policy() -> RBACPolicy | None:
    """Return the current RBAC policy, or None if none has been set."""
    return _rbac_policy_var.get()


def require_role(role: str) -> UserContext:
    """Return the current user context or raise if the user lacks the given role.

    Raises:
        PermissionError: If not authenticated or missing the role.
    """
    ctx = require_user_context()
    if not ctx.has_role(role):
        raise PermissionError(f"Role required: {role}")
    return ctx


def require_permission(permission: str) -> UserContext:
    """Return the current user context or raise if the user lacks the permission.

    Raises:
        PermissionError: If not authenticated or missing the permission.
    """
    ctx = require_user_context()
    if not ctx.has_permission(permission):
        raise PermissionError(f"Permission required: {permission}")
    return ctx


def require_domain_access(
    action: str,
    domain: str,
    *,
    entity: str | None = None,
    policy: RBACPolicy | None = None,
) -> UserContext:
    """Raise :class:`PermissionError` if the current user cannot perform *action* on *domain*/*entity*.

    Uses RBAC permission-matching (wildcards, domain-covers-entity).

    The RBAC policy is resolved in the following order:
    1. Explicit *policy* parameter (for direct caller control).
    2. The contextvar set by ``AuthGateway`` via ``set_rbac_policy``.
    3. A default ``RBACPolicy()`` with only built-in roles (fallback).

    Raises:
        PermissionError: If not authenticated or lacking the required permission.
    """
    from ninja_auth.rbac import RBACPolicy

    ctx = require_user_context()
    resolved = policy or _rbac_policy_var.get() or RBACPolicy()
    resolved.check(ctx.permissions, action, domain, entity)
    return ctx
