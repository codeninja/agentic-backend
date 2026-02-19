# Implementation Plan 003: Code Generation & Sync Engine (`ninjastack sync`)

> **Milestone**: 2 — The Generator
> **Tickets**: 2.2, 2.3

## Objective
Build the engine behind `ninjastack sync`. Given an ASD (`.ninjastack/schema.json`), generate the full library-first monorepo: Pydantic models, Data Agents, Domain Agents, GQL resolvers, and app shells.

## Requirements
- **Idempotent**: Running `sync` multiple times must not clobber user modifications. Generated code must be clearly separated from user code (e.g., `_generated/` directories or code markers).
- **Incremental**: Detect ASD changes and only regenerate affected libraries.
- **Extensible**: Template-based generation (Jinja2 or similar) so users can customize output.

## Generation Targets
1. **Pydantic Models** — One model per entity, with field types, validators, and optional embedding annotations.
2. **Persistence Layer** — Per-entity CRUD operations targeting the declared storage engine.
3. **Data Agent Stubs** — ADK-compatible agent definitions with auto-generated tools (CRUD + search).
4. **Domain Agent Stubs** — Higher-level agents that compose Data Agents for a domain.
5. **GQL Schema** — Strawberry types and resolvers mapped from the ASD.
6. **App Shell** — Thin FastAPI entrypoint that wires everything together.

## Key Decisions
- **User code vs generated code**: How do we prevent `sync` from overwriting custom business logic?
- **Template engine**: Jinja2 for Python code generation? AST-based?
- **Diff detection**: Hash-based change detection on ASD sections?

## File Structure
```
libs/ninja-codegen/
├── pyproject.toml
├── src/ninja_codegen/
│   ├── __init__.py
│   ├── engine.py            # Orchestrates the full sync pipeline
│   ├── differ.py            # ASD change detection
│   ├── templates/           # Jinja2 templates for all targets
│   │   ├── model.py.j2
│   │   ├── data_agent.py.j2
│   │   ├── domain_agent.py.j2
│   │   ├── gql_type.py.j2
│   │   └── app_shell.py.j2
│   └── generators/
│       ├── models.py
│       ├── agents.py
│       ├── graphql.py
│       └── apps.py
└── tests/
```

## Acceptance Criteria
- [ ] Given a sample ASD with 3 entities across 2 domains, `sync` generates a complete library structure.
- [ ] Running `sync` twice produces no diff.
- [ ] User-added code in designated extension points survives a `sync`.
- [ ] Generated agents are valid ADK definitions (importable, runnable).

## Dependencies
- Plan 002 (ASD Core Models)
- Plan 001 (Polyglot Introspection — for bolt-on mode feeding the ASD)
