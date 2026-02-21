"""Role-based access control: roles, permissions, and enforcement.

Permission format: ``action:scope`` where scope is a domain name or
``domain.entity`` pair.  The wildcard ``*`` matches everything.

Examples:
    - ``read:Orders``        — read any entity in the Orders domain
    - ``write:Billing.Invoice`` — write the Invoice entity in Billing
    - ``delete:*``           — delete anything
    - ``*:*``                — superuser (all actions, all scopes)

Built-in roles:
    - **admin**  — ``*:*``
    - **editor** — ``read:*``, ``write:*``
    - **viewer** — ``read:*``
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class Action(str, Enum):
    """Permission actions."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    WILDCARD = "*"


BUILTIN_ROLES: dict[str, list[str]] = {
    "admin": ["*:*"],
    "editor": ["read:*", "write:*"],
    "viewer": ["read:*"],
}


# ---------------------------------------------------------------------------
# Config models (embedded in AuthConfig)
# ---------------------------------------------------------------------------


class RoleDefinition(BaseModel):
    """A named role with a list of permission strings."""

    permissions: list[str] = Field(default_factory=list)
    description: str | None = None


class RBACConfig(BaseModel):
    """Declarative RBAC configuration (lives under ``rbac`` in auth.json)."""

    enabled: bool = True
    roles: dict[str, RoleDefinition] = Field(default_factory=dict)
    default_role: str | None = None

    model_config: dict[str, Any] = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Permission matching
# ---------------------------------------------------------------------------


def _parse_permission(perm: str) -> tuple[str, str]:
    """Split ``action:scope`` into (action, scope).  Returns ("", "") on bad input."""
    parts = perm.split(":", 1)
    if len(parts) != 2:
        return ("", "")
    return (parts[0], parts[1])


def permission_matches(grant: str, required: str) -> bool:
    """Return True if *grant* satisfies *required*.

    Wildcards:
        - ``*`` in the action position matches any action.
        - ``*`` in the scope position matches any scope.
        - ``DomainName`` in grant scope matches ``DomainName.AnyEntity``.
    """
    g_action, g_scope = _parse_permission(grant)
    r_action, r_scope = _parse_permission(required)

    if not g_action or not r_action:
        return False

    # Action match
    if g_action != "*" and g_action != r_action:
        return False

    # Scope match
    if g_scope == "*":
        return True
    if g_scope == r_scope:
        return True
    # Domain-level grant covers domain.entity
    if "." not in g_scope and r_scope.startswith(f"{g_scope}."):
        return True

    return False


# ---------------------------------------------------------------------------
# Policy (resolves roles → permissions)
# ---------------------------------------------------------------------------


class RBACPolicy:
    """Resolves roles to permissions and checks access.

    Merges built-in roles with any custom roles from config.  Custom roles
    with the same name as a built-in role **override** the built-in.
    """

    def __init__(self, config: RBACConfig | None = None) -> None:
        self.config = config or RBACConfig()
        self._role_permissions: dict[str, list[str]] = {}
        self._build_role_map()

    def _build_role_map(self) -> None:
        # Start with built-ins
        for role, perms in BUILTIN_ROLES.items():
            self._role_permissions[role] = list(perms)
        # Overlay custom roles from config
        for role, defn in self.config.roles.items():
            self._role_permissions[role] = list(defn.permissions)

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def roles(self) -> list[str]:
        """Return all known role names."""
        return list(self._role_permissions.keys())

    def permissions_for_roles(self, roles: list[str]) -> list[str]:
        """Return the union of permissions granted by *roles*."""
        seen: set[str] = set()
        result: list[str] = []
        for role in roles:
            for perm in self._role_permissions.get(role, []):
                if perm not in seen:
                    seen.add(perm)
                    result.append(perm)
        return result

    def is_allowed(self, permissions: list[str], action: str, domain: str, entity: str | None = None) -> bool:
        """Check whether *permissions* grant *action* on *domain* (optionally *entity*)."""
        scope = f"{domain}.{entity}" if entity else domain
        required = f"{action}:{scope}"
        return any(permission_matches(grant, required) for grant in permissions)

    def check(self, permissions: list[str], action: str, domain: str, entity: str | None = None) -> None:
        """Like :meth:`is_allowed` but raises :class:`PermissionError` on denial."""
        if not self.is_allowed(permissions, action, domain, entity):
            scope = f"{domain}.{entity}" if entity else domain
            raise PermissionError(f"Permission denied: {action}:{scope}")


# ---------------------------------------------------------------------------
# Enforcement helpers (work with agent_context)
# ---------------------------------------------------------------------------


def require_domain_permission(
    action: str,
    domain: str,
    entity: str | None = None,
    *,
    policy: RBACPolicy | None = None,
) -> None:
    """Raise :class:`PermissionError` if the current user lacks the permission.

    The RBAC policy is resolved in the following order:
    1. Explicit *policy* parameter (for direct caller control).
    2. The contextvar set by ``AuthGateway`` via ``set_rbac_policy``.
    3. A default ``RBACPolicy()`` with only built-in roles (fallback).

    Imports ``current_user_context`` lazily to avoid circular imports.
    """
    from ninja_auth.agent_context import current_rbac_policy, current_user_context

    ctx = current_user_context()
    if not ctx.is_authenticated:
        raise PermissionError("Authenticated user context required")

    resolved = policy or current_rbac_policy() or RBACPolicy()
    resolved.check(ctx.permissions, action, domain, entity)
