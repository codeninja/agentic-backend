#!/usr/bin/env python3
"""Example 4: Domain & Coordinator Agents — LLM-powered orchestration.

Demonstrates:
- Creating DomainAgents that wrap DataAgent sub-agents
- CoordinatorAgent for cross-domain routing
- Delegation: domain agent → data agent tool execution
- The full agent hierarchy: Coordinator → Domain → Data
- How reasoning levels map to models

NOTE: This example works without an API key — it exercises the agent wiring
and delegation layer. Actual LLM calls require GOOGLE_API_KEY.
"""

from ninja_agents.base import CoordinatorAgent, DataAgent, DomainAgent
from ninja_agents.tracing import TraceContext
from ninja_core.schema.agent import ReasoningLevel

from _bookstore_schema import (
    BOOK, CUSTOMER, ORDER, REVIEW,
    CATALOG_DOMAIN, COMMERCE_DOMAIN,
)

# ---------------------------------------------------------------------------
# 1. Build the Agent Hierarchy
# ---------------------------------------------------------------------------

# Data agents (deterministic CRUD)
book_da = DataAgent(entity=BOOK)
review_da = DataAgent(entity=REVIEW)
customer_da = DataAgent(entity=CUSTOMER)
order_da = DataAgent(entity=ORDER)

# Domain agents (LLM-powered, wrapping data agents)
catalog_agent = DomainAgent(
    domain=CATALOG_DOMAIN,
    data_agents=[book_da, review_da],
)
commerce_agent = DomainAgent(
    domain=COMMERCE_DOMAIN,
    data_agents=[customer_da, order_da],
)

# Coordinator (top-level router)
coordinator = CoordinatorAgent(
    domain_agents=[catalog_agent, commerce_agent],
)

print("✅ Agent Hierarchy:")
print(f"   Coordinator: {coordinator.name}")
print(f"     ├── {catalog_agent.name} (model: {catalog_agent.agent.model})")
print(f"     │   ├── {book_da.name}")
print(f"     │   └── {review_da.name}")
print(f"     └── {commerce_agent.name} (model: {commerce_agent.agent.model})")
print(f"         ├── {customer_da.name}")
print(f"         └── {order_da.name}")

# ---------------------------------------------------------------------------
# 2. Domain Agent Delegation
# ---------------------------------------------------------------------------

print("\n--- Domain Agent Delegation ---")

# The domain agent delegates to its data agents
trace = TraceContext()

# Catalog domain: get a book
result = catalog_agent.delegate("Book", "book_get", trace=trace, id="book-001")
print(f"\n📖 catalog.delegate('Book', 'book_get'):")
print(f"   {result}")

# Catalog domain: search reviews semantically
result = catalog_agent.delegate("Review", "review_search_semantic", trace=trace, query="mind-bending sci-fi")
print(f"\n🔍 catalog.delegate('Review', 'review_search_semantic'):")
print(f"   {result}")

# Commerce domain: create an order
result = commerce_agent.delegate("Order", "order_create", trace=trace,
                                  customer_id="cust-001", total=42.50, status="pending")
print(f"\n🛒 commerce.delegate('Order', 'order_create'):")
print(f"   {result}")

# ---------------------------------------------------------------------------
# 3. Cross-Domain Routing via Coordinator
# ---------------------------------------------------------------------------

print("\n--- Coordinator Routing ---")

# Route a request to specific domains
results = coordinator.route(
    request="Show me sci-fi books and the customer's order history",
    target_domains=["Catalog", "Commerce"],
    trace=trace,
)

print(f"\n🎯 coordinator.route(target_domains=['Catalog', 'Commerce']):")
for domain_name, result in results.items():
    print(f"   {domain_name}: {result}")

# ---------------------------------------------------------------------------
# 4. Scope Enforcement
# ---------------------------------------------------------------------------

print("\n--- Scope Enforcement ---")

# Domain agents only know about their own entities
try:
    catalog_agent.delegate("Order", "order_get", id="123")
except KeyError as e:
    print(f"✅ Catalog can't access Order: {e}")

try:
    coordinator.route("test", target_domains=["Shipping"])
except Exception:
    print("✅ Coordinator rejects unknown domains")

# Check the routing result
result = coordinator.route("test", target_domains=["Shipping"])
if "Shipping" in result and "error" in result["Shipping"]:
    print(f"   → {result['Shipping']}")

# ---------------------------------------------------------------------------
# 5. Reasoning Level → Model Mapping
# ---------------------------------------------------------------------------

print("\n--- Reasoning Levels ---")

levels = {
    ReasoningLevel.NONE: "No LLM (deterministic only)",
    ReasoningLevel.LOW: "gemini-2.0-flash",
    ReasoningLevel.MEDIUM: "gemini-2.5-flash",
    ReasoningLevel.HIGH: "gemini-2.5-pro",
}

for level, desc in levels.items():
    print(f"   {level.value:8s} → {desc}")

print(f"\n   Catalog agent reasoning:  {catalog_agent.config.reasoning_level.value} → {catalog_agent.agent.model}")
print(f"   Commerce agent reasoning: {commerce_agent.config.reasoning_level.value} → {commerce_agent.agent.model}")

# ---------------------------------------------------------------------------
# 6. Trace Summary
# ---------------------------------------------------------------------------

print(f"\n--- Trace Summary ({len(trace.spans)} spans) ---")
for span in trace.spans:
    print(f"   [{span.agent_name}] {len(span.tool_calls)} tool calls, {span.duration_ms:.1f}ms")
