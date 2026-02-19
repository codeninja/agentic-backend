# Implementation Plan 009: UI Generation (CRUD Viewer + Agentic Chat)

> **Milestone**: 4 — Composition & Deployment
> **Tickets**: (New)

## Objective
Auto-generate two frontend interfaces from the ASD:
1. **CRUD Data Viewer**: An admin-style data browser for inspecting and editing entities across all engines.
2. **Agentic Chat UI**: A conversational interface connected to the Coordinator Agent.

## Requirements
- **ASD-driven**: UI components are generated from entity definitions — no manual form building.
- **Polyglot-aware**: The CRUD viewer handles SQL rows, Mongo documents, graph nodes, and vector entries.
- **Agent-connected**: The chat UI routes to the Coordinator Agent via the GQL layer.
- **Embeddable**: Both UIs should be embeddable in existing apps or served standalone.
- **Responsive**: Standard responsive layout (works on desktop and mobile).

## CRUD Data Viewer
- Auto-generated table/list views per entity.
- Inline editing with boundary layer validation.
- Relationship navigation (click FK to jump to related entity).
- Semantic search bar on every entity.
- Filterable, sortable, paginated.

## Agentic Chat UI
- Conversational interface (message bubbles).
- Streams responses from the Coordinator Agent.
- Shows tool usage transparency (which agents were consulted).
- File upload support (for document ingestion).
- Auth-aware: User identity flows through to the agent.

## Tech Stack (TBD)
- **Option A**: React + Vite (generated components).
- **Option B**: HTMX + Jinja2 (server-rendered, simpler).
- **Option C**: Streamlit/Gradio (rapid prototyping).

## File Structure
```
libs/ninja-ui/
├── pyproject.toml (or package.json)
├── src/
│   ├── crud/                 # CRUD data viewer components
│   ├── chat/                 # Agentic chat interface
│   └── shared/               # Common UI primitives
└── tests/
```

## Acceptance Criteria
- [ ] Given an ASD, generate a CRUD viewer with one table/list per entity.
- [ ] CRUD viewer supports inline editing with validation feedback.
- [ ] Chat UI connects to the Coordinator Agent and streams responses.
- [ ] Both UIs are servable via `ninjastack serve ui`.

## Dependencies
- Plan 008 (GraphQL Layer — UIs consume the GQL API)
- Plan 007 (Auth Gateway — for user identity)
- Plan 003 (Code Generation — UI is a generation target)
