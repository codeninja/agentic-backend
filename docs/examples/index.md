# Examples

Walk through a complete **Online Bookstore** to learn every layer of NinjaStack.

## The Bookstore

A simple bookstore with Books, Customers, Orders, and Reviews — enough to demonstrate the full stack.

| # | Example | What You'll Learn |
|---|---------|-------------------|
| 1 | [Schema Definition](01-schema.md) | Define entities, relationships, domains |
| 2 | [Code Generation](02-codegen.md) | Generate models, agents, GraphQL from schema |
| 3 | [Data Agents](03-data-agents.md) | Deterministic CRUD, tool scoping, tracing |
| 4 | [Domain Agents](04-domain-agents.md) | LLM-powered orchestration, delegation |
| 5 | [Auth & RBAC](05-auth-rbac.md) | Identity, tokens, role-based permissions |
| 6 | [End-to-End](06-end-to-end.md) | Full pipeline: schema → agents → auth → query |

## Running the Examples

```bash
cd ninja-stack
PYTHONPATH=examples/bookstore uv run python examples/bookstore/01_schema_definition.py
```

All examples run without API keys (deterministic mode).
