# Implementation Plan 002: ASD Core Models (`libs/ninja-core`)

> **Milestone**: 1 — The Foundation
> **Tickets**: 1.1

## Objective
Define the **Agentic Schema Definition (ASD)** as a set of Pydantic models in `libs/ninja-core`. This is the "DNA" of every Ninja Stack project — the intermediate representation that all generators, agents, and persistence layers consume.

## Requirements
- The ASD must represent entities from any engine (SQL tables, Mongo collections, Graph nodes, Vector collections).
- Relationships must be type-agnostic: Hard (FK), Soft (semantic/vector similarity), Graph (edges).
- Each entity must declare its **storage provenance** (which DB engine owns it).
- Each entity must optionally declare an **embedding strategy** (which fields to vectorize, which model to use).
- Domain groupings must be explicit — which entities belong to which Expert Domain.
- Agent configuration must be declarable per-domain (model, tools, permissions).

## Key Models
- `FieldSchema`: Name, type, constraints, nullable, default, embedding config.
- `EntitySchema`: Collection of fields + storage provenance + relationships.
- `RelationshipSchema`: Source entity, target entity, type (hard/soft/graph), cardinality.
- `DomainSchema`: Logical grouping of entities under one Expert Agent.
- `AgentConfig`: Model provider, LiteLLM config, tool permissions, reasoning level.
- `AgenticSchema`: Top-level container — the full project definition.

## File Structure
```
libs/ninja-core/
├── pyproject.toml
├── src/ninja_core/
│   ├── __init__.py
│   ├── schema/
│   │   ├── __init__.py
│   │   ├── entity.py        # EntitySchema, FieldSchema
│   │   ├── relationship.py  # RelationshipSchema
│   │   ├── domain.py        # DomainSchema
│   │   ├── agent.py         # AgentConfig
│   │   └── project.py       # AgenticSchema (top-level)
│   └── serialization/
│       ├── __init__.py
│       └── io.py             # Read/write .ninjastack/schema.json
└── tests/
    ├── test_entity.py
    ├── test_relationship.py
    └── test_serialization.py
```

## Acceptance Criteria
- [ ] All models are Pydantic v2 with strict validation.
- [ ] An ASD can be serialized to / deserialized from `.ninjastack/schema.json`.
- [ ] Round-trip test: create ASD programmatically → serialize → deserialize → assert equality.
- [ ] Models support SQL, NoSQL, Graph, and Vector entity types.
- [ ] Domain groupings correctly associate entities with agent configs.

## Dependencies
- None (this is the foundational library).

## Open Questions
- Should the ASD support versioning/migrations (schema evolution over time)?
- How granular should embedding config be — per-field or per-entity?
