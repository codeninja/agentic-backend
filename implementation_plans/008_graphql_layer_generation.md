# Implementation Plan 008: GraphQL Layer Generation

> **Milestone**: 4 — Composition & Deployment
> **Tickets**: (New)

## Objective
Auto-generate a fully typed GraphQL API (via Strawberry) from the ASD. The GQL layer is the primary programmatic interface for both the agentic chat UI and external consumers.

## Requirements
- **ASD-driven**: Every entity in the ASD produces a GQL type, query, and mutation.
- **Relationship resolution**: GQL nested queries follow ASD relationships (hard, soft, graph).
- **Agent-backed resolvers**: Complex queries are delegated to Domain Agents rather than raw DB queries.
- **Subscriptions**: Real-time updates via GQL subscriptions (WebSocket) for live data.
- **Auth-aware**: Resolvers respect RBAC from the Auth Gateway context.

## Generation Targets
- **Types**: One Strawberry type per ASD entity.
- **Queries**: `get_{entity}`, `list_{entity}`, `search_{entity}` (semantic).
- **Mutations**: `create_{entity}`, `update_{entity}`, `delete_{entity}`.
- **Subscriptions**: `on_{entity}_changed` for real-time use cases.
- **Custom Resolvers**: Extension points where users can add domain-specific queries.

## File Structure
```
libs/ninja-gql/
├── pyproject.toml
├── src/ninja_gql/
│   ├── __init__.py
│   ├── generator.py          # ASD → Strawberry types + resolvers
│   ├── schema.py             # Assembled GQL schema
│   ├── resolvers/
│   │   ├── __init__.py
│   │   ├── crud.py           # Standard CRUD resolvers
│   │   ├── semantic.py       # Semantic search resolvers
│   │   └── agent.py          # Agent-delegated resolvers
│   └── subscriptions.py      # Real-time subscription handlers
└── tests/
```

## Acceptance Criteria
- [ ] Given an ASD with 3 entities, generate a working Strawberry schema with types, queries, and mutations.
- [ ] Nested queries resolve relationships correctly (e.g., `order { customer { address } }`).
- [ ] Semantic search is exposed as a GQL query: `search_products(query: "red shoes")`.
- [ ] Auth context is enforced — unauthorized fields return errors.

## Dependencies
- Plan 002 (ASD Core Models)
- Plan 003 (Code Generation Engine — GQL is a generation target)
- Plan 004 (Unified Persistence — resolvers use the persistence layer)
- Plan 007 (Auth Gateway — for RBAC enforcement)
