#!/usr/bin/env python3
"""Example 6: End-to-End — Full pipeline from schema to authenticated agent query.

Demonstrates the complete NinjaStack flow:
1. Define schema (ASD)
2. Generate code (models, agents, GraphQL)
3. Wire up agent hierarchy (Data → Domain → Coordinator)
4. Apply auth + RBAC
5. Process an authenticated request through the full stack

No API key required — runs entirely locally with deterministic agents.
"""

import tempfile
from pathlib import Path

from ninja_agents.base import CoordinatorAgent, DataAgent, DomainAgent
from ninja_agents.tracing import TraceContext
from ninja_auth.context import UserContext
from ninja_auth.rbac import RBACConfig, RBACPolicy, RoleDefinition
from ninja_codegen.generators.agents import generate_agents
from ninja_codegen.generators.graphql import generate_graphql
from ninja_codegen.generators.models import generate_models
from ninja_core.serialization.io import save_schema

from _bookstore_schema import (
    SCHEMA, ENTITIES, DOMAINS,
    BOOK, CUSTOMER, ORDER, REVIEW,
    CATALOG_DOMAIN, COMMERCE_DOMAIN,
)

print("=" * 60)
print("  NinjaStack End-to-End: Online Bookstore")
print("=" * 60)

# ---------------------------------------------------------------------------
# Step 1: Schema → Disk
# ---------------------------------------------------------------------------

schema_dir = Path(tempfile.mkdtemp(prefix="ninjastack-e2e-"))
schema_path = schema_dir / ".ninjastack" / "schema.json"
save_schema(SCHEMA, schema_path)
print(f"\n✅ Step 1: Schema saved to {schema_path}")
print(f"   {len(ENTITIES)} entities, {len(SCHEMA.relationships)} relationships, {len(DOMAINS)} domains")

# ---------------------------------------------------------------------------
# Step 2: Code Generation
# ---------------------------------------------------------------------------

output_dir = schema_dir / "generated"
model_paths = generate_models(ENTITIES, output_dir)
agent_paths = generate_agents(ENTITIES, DOMAINS, output_dir)
gql_paths = generate_graphql(ENTITIES, output_dir)

total = len(model_paths) + len(agent_paths) + len(gql_paths)
print(f"\n✅ Step 2: Generated {total} files")
print(f"   {len(model_paths)} models, {len(agent_paths)} agents, {len(gql_paths)} GraphQL types")

# ---------------------------------------------------------------------------
# Step 3: Wire Agent Hierarchy
# ---------------------------------------------------------------------------

# Data agents
book_da = DataAgent(entity=BOOK)
review_da = DataAgent(entity=REVIEW)
customer_da = DataAgent(entity=CUSTOMER)
order_da = DataAgent(entity=ORDER)

# Domain agents
catalog = DomainAgent(domain=CATALOG_DOMAIN, data_agents=[book_da, review_da])
commerce = DomainAgent(domain=COMMERCE_DOMAIN, data_agents=[customer_da, order_da])

# Coordinator
coordinator = CoordinatorAgent(domain_agents=[catalog, commerce])

print(f"\n✅ Step 3: Agent hierarchy wired")
print(f"   Coordinator → {coordinator.domain_names}")

# ---------------------------------------------------------------------------
# Step 4: Auth + RBAC
# ---------------------------------------------------------------------------

rbac_config = RBACConfig(
    enabled=True,
    roles={
        "customer": RoleDefinition(permissions=[
            "read:Catalog", "write:Catalog.Review",
            "read:Commerce.Order", "read:Commerce.Customer",
        ]),
    },
)
policy = RBACPolicy(config=rbac_config)

admin = UserContext(user_id="admin-1", roles=["admin"])
customer_user = UserContext(user_id="customer-42", roles=["customer"])

print(f"\n✅ Step 4: RBAC configured")
print(f"   Admin:    full access")
print(f"   Customer: read catalog, read/write reviews, read own orders")

# ---------------------------------------------------------------------------
# Step 5: Process Requests
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("  Simulated Request Processing")
print(f"{'=' * 60}")

trace = TraceContext()


def process_request(user: UserContext, domain_name: str, entity_name: str,
                    tool_name: str, **kwargs):
    """Simulate a full authenticated request through the stack."""
    # 1. Determine action from tool name
    if tool_name.endswith(("_get", "_list", "_search_semantic")):
        action = "read"
    elif tool_name.endswith("_delete"):
        action = "delete"
    else:
        action = "write"

    # 2. RBAC check
    perms = policy.permissions_for_roles(user.roles)
    if not policy.is_allowed(perms, action, domain_name, entity_name):
        return {"status": "DENIED", "user": user.user_id, "action": action, "entity": entity_name}

    # 3. Route through coordinator → domain → data agent
    domain_agent = coordinator.get_domain_agent(domain_name)
    if domain_agent is None:
        return {"status": "NOT_FOUND", "domain": domain_name}

    result = domain_agent.delegate(entity_name, tool_name, trace=trace, **kwargs)
    return {"status": "OK", "user": user.user_id, "result": result}


# --- Customer browses books ---
print("\n📖 Customer browses books:")
r = process_request(customer_user, "Catalog", "Book", "book_list", genre="sci-fi")
print(f"   {r}")

# --- Customer searches reviews ---
print("\n🔍 Customer searches reviews:")
r = process_request(customer_user, "Catalog", "Review", "review_search_semantic",
                    query="best mystery novels this year")
print(f"   {r}")

# --- Customer writes a review ---
print("\n✍️  Customer writes a review:")
r = process_request(customer_user, "Catalog", "Review", "review_create",
                    book_id="book-001", rating=5, text="Absolutely loved it!")
print(f"   {r}")

# --- Customer tries to delete a book (DENIED) ---
print("\n🚫 Customer tries to delete a book:")
r = process_request(customer_user, "Catalog", "Book", "book_delete", id="book-001")
print(f"   {r}")

# --- Customer tries to create an order (DENIED - write on Order) ---
print("\n🚫 Customer tries to create an order:")
r = process_request(customer_user, "Commerce", "Order", "order_create",
                    customer_id="customer-42", total=29.99)
print(f"   {r}")

# --- Admin creates an order (OK) ---
print("\n✅ Admin creates an order:")
r = process_request(admin, "Commerce", "Order", "order_create",
                    customer_id="customer-42", total=29.99)
print(f"   {r}")

# --- Admin deletes a book (OK) ---
print("\n✅ Admin deletes a book:")
r = process_request(admin, "Catalog", "Book", "book_delete", id="book-obsolete")
print(f"   {r}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("  Summary")
print(f"{'=' * 60}")
print(f"  Schema:    {len(ENTITIES)} entities, {len(SCHEMA.relationships)} relationships")
print(f"  Generated: {total} files (models + agents + GraphQL)")
print(f"  Agents:    {len(coordinator.domain_names)} domains, 4 data agents")
print(f"  Auth:      {len(policy.roles())} roles, RBAC enforced")
print(f"  Trace:     {len(trace.spans)} spans recorded")
print(f"\n💡 Add GOOGLE_API_KEY to enable real LLM-powered agent conversations.")
print(f"   The coordinator will use Gemini to classify intent and delegate.")
