#!/usr/bin/env python3
"""Example 5: Auth & RBAC — Protect agents with authentication and permissions.

Demonstrates:
- Built-in identity: user registration, login, JWT tokens
- RBAC policy with string-based permissions (action:scope)
- Permission checking at domain/entity level
- Protecting agent tool execution with role checks

Permission format: "action:scope"
  - read:Catalog         — read any entity in Catalog domain
  - write:Catalog.Review — write only Review entity in Catalog
  - delete:*             — delete anything
  - *:*                  — superuser
"""

from ninja_auth.config import IdentityConfig
from ninja_auth.context import UserContext
from ninja_auth.rbac import RBACConfig, RBACPolicy, RoleDefinition
from ninja_auth.strategies.identity import IdentityStrategy

# ---------------------------------------------------------------------------
# 1. Built-in Identity (Registration + Login + Tokens)
# ---------------------------------------------------------------------------

JWT_SECRET = "bookstore-example-secret-key-32bytes!"
identity_config = IdentityConfig(token_secret=JWT_SECRET)
identity = IdentityStrategy(config=identity_config)

print("--- User Registration & Login ---")

# Register users (returns UserContext)
admin_ctx = identity.register(email="admin@bookstore.com", password="s3cur3!", roles=["admin"])
editor_ctx = identity.register(email="editor@bookstore.com", password="wr1t3r!", roles=["editor"])
customer_ctx = identity.register(email="alice@example.com", password="r3ad3r!", roles=["customer"])

print(f"  Registered: {admin_ctx.email} (roles={admin_ctx.roles})")
print(f"  Registered: {editor_ctx.email} (roles={editor_ctx.roles})")
print(f"  Registered: {customer_ctx.email} (roles={customer_ctx.roles})")

# Issue JWT tokens
admin_token = identity.issue_token(admin_ctx)
customer_token = identity.issue_token(customer_ctx)
print(f"\n  Admin JWT:    {admin_token[:50]}...")
print(f"  Customer JWT: {customer_token[:50]}...")

# Validate token → get context back
validated = identity.validate_token(admin_token)
print(f"\n  Validated: user_id={validated.user_id}, roles={validated.roles}")

# Login flow
logged_in = identity.login(email="alice@example.com", password="r3ad3r!")
print(f"  Login OK:  user_id={logged_in.user_id}, email={logged_in.email}")

bad_login = identity.login(email="alice@example.com", password="wrong!")
print(f"  Bad login: {bad_login}")  # None

# ---------------------------------------------------------------------------
# 2. RBAC Policy
# ---------------------------------------------------------------------------

print("\n--- RBAC Policy ---")

# Built-in roles (from ninja_auth.rbac):
#   admin  → *:*
#   editor → read:*, write:*
#   viewer → read:*
#
# We add a custom "customer" role with scoped permissions:
rbac_config = RBACConfig(
    enabled=True,
    roles={
        "customer": RoleDefinition(
            permissions=[
                "read:Catalog",             # Read all Catalog entities (Book, Review)
                "write:Catalog.Review",     # Write reviews only
                "read:Commerce.Order",      # Read own orders
                "read:Commerce.Customer",   # Read own profile
            ],
            description="Registered bookstore customer",
        ),
    },
)

policy = RBACPolicy(config=rbac_config)

print(f"  Known roles: {policy.roles()}")
print(f"  Admin perms:    {policy.permissions_for_roles(['admin'])}")
print(f"  Editor perms:   {policy.permissions_for_roles(['editor'])}")
print(f"  Customer perms: {policy.permissions_for_roles(['customer'])}")

# ---------------------------------------------------------------------------
# 3. Permission Checks
# ---------------------------------------------------------------------------

print("\n--- Permission Checks ---")


def can(roles: list[str], action: str, domain: str, entity: str | None = None) -> bool:
    perms = policy.permissions_for_roles(roles)
    return policy.is_allowed(perms, action, domain, entity)


# Admin — full access via *:*
print(f"  Admin delete Book?       {can(['admin'], 'delete', 'Catalog', 'Book')}")      # True
print(f"  Admin write Order?       {can(['admin'], 'write', 'Commerce', 'Order')}")      # True

# Editor — built-in read:* + write:*, but no delete
print(f"  Editor write Book?       {can(['editor'], 'write', 'Catalog', 'Book')}")       # True
print(f"  Editor delete Book?      {can(['editor'], 'delete', 'Catalog', 'Book')}")      # False

# Customer — custom scoped permissions
print(f"  Customer read Book?      {can(['customer'], 'read', 'Catalog', 'Book')}")      # True
print(f"  Customer write Review?   {can(['customer'], 'write', 'Catalog', 'Review')}")   # True
print(f"  Customer write Book?     {can(['customer'], 'write', 'Catalog', 'Book')}")     # False
print(f"  Customer read Order?     {can(['customer'], 'read', 'Commerce', 'Order')}")    # True
print(f"  Customer write Order?    {can(['customer'], 'write', 'Commerce', 'Order')}")   # False
print(f"  Customer delete Review?  {can(['customer'], 'delete', 'Catalog', 'Review')}")  # False

# ---------------------------------------------------------------------------
# 4. Enforcement (raises PermissionError)
# ---------------------------------------------------------------------------

print("\n--- Enforcement ---")

admin_perms = policy.permissions_for_roles(["admin"])
customer_perms = policy.permissions_for_roles(["customer"])

try:
    policy.check(admin_perms, "delete", "Catalog", "Book")
    print("  ✅ Admin delete Book: ALLOWED")
except PermissionError as e:
    print(f"  🚫 {e}")

try:
    policy.check(customer_perms, "write", "Commerce", "Order")
    print("  ✅ Customer write Order: ALLOWED")
except PermissionError as e:
    print(f"  🚫 Customer write Order: {e}")

try:
    policy.check(customer_perms, "delete", "Catalog", "Review")
    print("  ✅ Customer delete Review: ALLOWED")
except PermissionError as e:
    print(f"  🚫 Customer delete Review: {e}")

# ---------------------------------------------------------------------------
# 5. Protecting Agent Tool Execution
# ---------------------------------------------------------------------------

print("\n--- Protected Agent Execution ---")

from ninja_agents.base import DataAgent
from _bookstore_schema import BOOK, REVIEW

book_agent = DataAgent(entity=BOOK)
review_agent = DataAgent(entity=REVIEW)


def protected_execute(agent, tool_name, user_roles, domain, **kwargs):
    """Execute a tool only if the user's roles grant permission."""
    if tool_name.endswith(("_get", "_list", "_search_semantic")):
        action = "read"
    elif tool_name.endswith("_delete"):
        action = "delete"
    else:
        action = "write"

    perms = policy.permissions_for_roles(user_roles)
    if not policy.is_allowed(perms, action, domain, agent.entity.name):
        return f"🚫 DENIED: {user_roles} cannot {action} {domain}.{agent.entity.name}"

    result = agent.execute(tool_name, **kwargs)
    return f"✅ {result}"


print(f"  {protected_execute(book_agent, 'book_list', ['customer'], 'Catalog', genre='sci-fi')}")
print(f"  {protected_execute(review_agent, 'review_create', ['customer'], 'Catalog', book_id='b1', rating=5)}")
print(f"  {protected_execute(book_agent, 'book_create', ['customer'], 'Catalog', title='Hacked')}")
print(f"  {protected_execute(review_agent, 'review_delete', ['customer'], 'Catalog', id='r1')}")
print(f"  {protected_execute(book_agent, 'book_delete', ['admin'], 'Catalog', id='b-old')}")

print("\n💡 In production, the gateway middleware resolves JWT → roles → permissions")
print("   and injects them into the request context before agents execute.")
