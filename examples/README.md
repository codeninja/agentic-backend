# NinjaStack Examples

Hands-on examples demonstrating NinjaStack's core concepts using a simple **Online Bookstore** domain.

## The Bookstore

A small online bookstore with:
- **Books** — catalog with titles, authors, prices
- **Customers** — registered users who buy books
- **Orders** — purchase records linking customers to books
- **Reviews** — customer reviews with ratings and text (semantic-searchable)

This single domain is enough to demonstrate every layer of the stack.

## Examples

| # | Example | What It Demonstrates |
|---|---------|---------------------|
| 1 | [Schema Definition](01_schema_definition.py) | Define entities, fields, relationships, and domains using the ASD |
| 2 | [Code Generation](02_code_generation.py) | Generate Pydantic models, ADK agents, and GraphQL types from a schema |
| 3 | [Data Agents](03_data_agents.py) | Create deterministic CRUD agents for each entity (no LLM) |
| 4 | [Domain & Coordinator Agents](04_domain_agents.py) | Wire up LLM-powered domain agents with sub-agent delegation |
| 5 | [Auth & RBAC](05_auth_rbac.py) | Protect agents with authentication and role-based permissions |
| 6 | [End-to-End](06_end_to_end.py) | Full pipeline: schema → codegen → agents → auth → query |

## Running

```bash
# From repo root
uv run python examples/bookstore/01_schema_definition.py
uv run python examples/bookstore/02_code_generation.py
# ... etc.
```

Each example is self-contained and prints its output to stdout.
No API keys required except for Example 6 (optional LLM integration).
