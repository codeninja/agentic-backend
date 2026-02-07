# Agentic Backend

Schema-first agentic backend framework. Point at a database, get a full agentic backend + UI.

## Vision

Replace or migrate traditional backends to an agentic architecture through automated introspection:

1. **Connect to existing database** — introspect schema
2. **Auto-generate the stack** — models, agents, GQL layer, prompts
3. **Spin up UIs** — CRUD data viewer + agentic chat interface
4. **Migrate legacy code** — extract business logic from existing source into agents

## Architecture

```
┌─────────────────────────────────────────────────────┐
│         Use Case Router (Agentic/Deterministic)     │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│              Use Case Coordinators                   │
│  ┌─────────────┬─────────────┬─────────────┐        │
│  │   Domain    │   Domain    │   Domain    │        │
│  │   Agent     │   Agent     │   Agent     │        │
│  └─────────────┴─────────────┴─────────────┘        │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                   Data Agents                        │
│  ┌─────────────┬─────────────┬─────────────┐        │
│  │    User     │   Address   │   Product   │        │
│  │   Agent     │   Agent     │   Agent     │        │
│  └─────────────┴─────────────┴─────────────┘        │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                   GQL Data Layer                     │
└─────────────────────────────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │    DB     │
                    └───────────┘
```

## Agent Hierarchy

### Use Case Coordinators
- Top-level orchestration for complex workflows
- Parallel delegation to domain agents
- Primary interface for conversational users
- Example: Shopping cart coordinator (check inventory, process payment, fulfill order)

### Domain Agents
- Understand cross-entity relationships within a domain
- Compose multiple data agents
- Example: User Domain Agent contains User + Address agents, knows users have addresses

### Data Agents
- Single-entity experts
- CRUD operations + entity-specific business logic
- Interface with GQL layer
- Not all agents need LLM — many are deterministic data fetchers

## Design Principles

- **Schema-first** — data model is source of truth, everything derives from it
- **Explicit > implicit** — clear ownership, typed contracts
- **Composition > inheritance** — agents compose up the hierarchy
- **LLM where it matters** — reserve reasoning for ambiguity, keep hot paths deterministic
- **Tolerance for dirty data** — boundary layer handles schema drift, coercion, missing fields

## Data Tolerance

Real-world data is messy. The boundary layer handles:

- **Missing fields** — convention-based defaults
- **Type coercion** — int↔string, flexible timestamps
- **Schema drift** — especially for schemaless databases (MongoDB)
- **Progressive strictness** — log coercions, tighten rules based on observed patterns

## Generation Pipeline

```
DB Schema Introspection
        ↓
Pydantic Models (per table)
        ↓
Data Agents (per entity)
        ↓
Domain Agents (inferred from FK relationships)
        ↓
Use Case Coordinators (common patterns)
        ↓
GQL Layer (auto-generated)
        ↓
UIs: CRUD Viewer + Agentic Chat
```

## Migration Path

For existing systems:

1. Generate agentic layer from schema
2. Introspect existing source code for business logic
3. Extract validation, workflows, edge cases into agents
4. Surface unknowns for human review
5. Shadow mode alongside old system, flag divergences
6. Progressive cutover

## Two Interfaces

- **CRUD UI** — traditional data viewer, familiar, "human last resort"
- **Chat UI** — conversational interface to any agent, domain, or coordinator

## Status

Early development. Concepts drawn from production systems at Tractian, Trust Radius, and ninja-adk.

## Tech Stack

TBD — likely Python, Pydantic, Google ADK, GraphQL

## License

TBD
