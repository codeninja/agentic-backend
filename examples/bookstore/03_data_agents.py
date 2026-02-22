#!/usr/bin/env python3
"""Example 3: Data Agents — Deterministic CRUD agents (no LLM required).

Demonstrates:
- Creating a DataAgent for an entity (extends ADK BaseAgent)
- Auto-generated CRUD + semantic search tools
- Executing tools directly (deterministic, no LLM call)
- Tool scoping — agents only see their own entity's tools
- Tracing tool execution
"""

from _bookstore_schema import BOOK, CUSTOMER, ORDER, REVIEW
from ninja_agents.base import DataAgent
from ninja_agents.tools import generate_crud_tools
from ninja_agents.tracing import TraceContext

# ---------------------------------------------------------------------------
# 1. Create Data Agents
# ---------------------------------------------------------------------------

book_agent = DataAgent(entity=BOOK)
customer_agent = DataAgent(entity=CUSTOMER)
order_agent = DataAgent(entity=ORDER)
review_agent = DataAgent(entity=REVIEW)

print("✅ Data Agents created:")
for agent in [book_agent, customer_agent, order_agent, review_agent]:
    print(f"   {agent.name} — tools: {agent.tool_names}")
    print(f"     uses_llm: {agent.uses_llm}")

# ---------------------------------------------------------------------------
# 2. Execute Tools Directly (No LLM)
# ---------------------------------------------------------------------------

print("\n--- Direct Tool Execution ---")

# Get a book by ID
result = book_agent.execute("book_get", id="abc-123")
print("\n📖 book_get(id='abc-123'):")
print(f"   {result}")

# List customers with a filter
result = customer_agent.execute("customer_list", email_contains="@example.com")
print("\n👤 customer_list(email_contains='@example.com'):")
print(f"   {result}")

# Create an order
result = order_agent.execute(
    "order_create",
    customer_id="cust-456",
    total=29.99,
    status="pending",
)
print("\n🛒 order_create(...):")
print(f"   {result}")

# Semantic search on reviews
result = review_agent.execute(
    "review_search_semantic",
    query="great character development and plot twists",
)
print("\n🔍 review_search_semantic(query='great character development...'):")
print(f"   {result}")

# ---------------------------------------------------------------------------
# 3. Tool Scoping — Agents Can't Access Other Entity's Tools
# ---------------------------------------------------------------------------

print("\n--- Tool Scoping ---")

try:
    book_agent.execute("customer_get", id="123")
except KeyError as e:
    print(f"✅ Scope enforced: {e}")

# ---------------------------------------------------------------------------
# 4. Tracing
# ---------------------------------------------------------------------------

print("\n--- Tracing ---")

trace = TraceContext()
book_agent.execute("book_list", trace=trace, genre="sci-fi")
order_agent.execute("order_get", trace=trace, id="ord-789")

print(f"   Trace spans: {len(trace.spans)}")
for span in trace.spans:
    print(f"   [{span.agent_name}] tools called: {len(span.tool_calls)}, duration: {span.duration_ms:.1f}ms")

# ---------------------------------------------------------------------------
# 5. Inspect Auto-Generated Tools
# ---------------------------------------------------------------------------

print("\n--- Auto-Generated Tool Details ---")

tools = generate_crud_tools(BOOK)
for tool in tools:
    print(f"   {tool.__name__}: {tool.__doc__}")
