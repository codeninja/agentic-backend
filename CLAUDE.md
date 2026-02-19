# CLAUDE.md

## Project Overview
Ninja Stack — a schema-first agentic backend framework. Point at a database (SQL, NoSQL, Graph, or Vector), or describe your domain in conversation, and get a full agentic backend with GraphQL API, CRUD UI, and agentic chat interface. All business logic lives in modular libraries; apps are pure composition.

## Commands

### Root (Monorepo)
```bash
uv sync                       # Install all workspace dependencies
uv run pytest                 # Run all tests across all libs
uv run ruff check .           # Lint all Python
uv run ruff format .          # Format all Python
```

### Per-Library
```bash
cd libs/ninja-core && uv run pytest tests/
cd libs/ninja-persistence && uv run pytest tests/
# etc.
```

## Architecture

```
agentic-backend/
├── .ninjastack/              # Project state (ASD, connections, model config)
│   ├── schema.json           # Agentic Schema Definition (source of truth)
│   ├── connections.json      # Polyglot DB connection profiles
│   ├── models.json           # LLM provider config (default: Gemini)
│   └── auth.json             # Auth strategy config
├── libs/                     # ALL business logic lives here
│   ├── ninja-core/           # ASD Pydantic models (the "DNA")
│   ├── ninja-persistence/    # Unified polyglot persistence (SQL/Mongo/Graph/Vector)
│   ├── ninja-agents/         # ADK agent base classes & orchestration
│   ├── ninja-codegen/        # Code generation & sync engine
│   ├── ninja-graph/          # Graph-RAG bootstrapper (Neo4j)
│   ├── ninja-boundary/       # Data tolerance & coercion layer
│   ├── ninja-auth/           # Auth gateway & strategy modules
│   ├── ninja-gql/            # GraphQL layer generator (Strawberry)
│   ├── ninja-models/         # LiteLLM integration & model routing
│   ├── ninja-deploy/         # K8s/Helm manifest generator
│   └── ninja-ui/             # UI generation (CRUD + Chat)
├── apps/                     # Thin composition shells (ZERO business logic)
│   ├── ninja-api/            # FastAPI/GraphQL entry point
│   └── ninja-setup-assistant/ # CLI agent for `ninjastack init`
├── docs/
│   └── architecture.md       # Technical blueprint with Mermaid diagrams
├── implementation_plans/     # Detailed plans (000-013) for all milestones
└── infrastructure/           # Helm charts, Dockerfiles, CI/CD
```

## Key Patterns

- **Library-first monorepo**: All logic in `libs/`, apps are composition only.
- **ASD is the DNA**: `.ninjastack/schema.json` drives all code generation. Entities, domains, relationships, agent configs.
- **Agent-at-every-level**: Data Agents (deterministic CRUD), Domain Agents (LLM reasoning), Coordinators (routing/synthesis).
- **Polyglot persistence**: SQL (SQLAlchemy), MongoDB (Motor/Beanie), Neo4j (graph), Chroma/Milvus (vector) — unified `Repository` protocol.
- **Gemini-first, LiteLLM-flexible**: Default to Google Gemini via ADK; LiteLLM bridge for OpenAI/Anthropic/Ollama.
- **Graph-RAG**: Auto-bootstrap knowledge graph from ASD relationships. Agents traverse multi-hop paths.
- **Data Tolerance**: Boundary layer handles type coercion, missing fields, schema drift from messy real-world data.
- **Auth Gateway**: Pluggable strategies (OAuth2, JWT/Auth0, API keys, built-in identity). User context injected into agent chain.

## Agent Workflow
- **Branching**: `feat/issue-{N}-{slug}`
- **Commits**: Conventional commits with `closes #{N}`
- **Testing**: All tests must pass. Each library has its own test suite.
- **Linting**: `ruff check` + `ruff format` (Python). Pyright for type checking.
- **Coverage**: Target ≥85% per library.
- **Key constraint**: Never put business logic in `apps/`. If you're writing logic, it belongs in a `libs/` package.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Contracts | Pydantic v2 |
| Agent Framework | Google ADK |
| Default LLM | Google Gemini |
| Model Bridge | LiteLLM |
| API | FastAPI + Strawberry (GraphQL) |
| SQL | SQLAlchemy 2.x (async) |
| NoSQL | Motor / Beanie (MongoDB) |
| Graph | Neo4j driver |
| Vector | Chroma / Milvus |
| Package Manager | uv (Python), pnpm (JS) |
| Linting | Ruff, Pyright |
| Testing | Pytest, pytest-asyncio |
| Deployment | Docker, Helm, GKE |

## Environment
- `.env` for local secrets (gitignored)
- `.ninjastack/connections.json` for DB connection profiles
- `.ninjastack/models.json` for LLM provider API keys (env var references)

## Deployment
- K8s/Helm via `libs/ninja-deploy` generator
- Docker multi-stage builds per app
- GitHub Actions CI/CD (affected-only testing)

## Implementation Plans
See `implementation_plans/` for detailed plans:
- 000: CLI & Setup Assistant
- 001: Polyglot Introspection
- 002: ASD Core Models
- 003: Code Generation / Sync Engine
- 004: Unified Persistence Layer
- 005: Graph-RAG Bootstrapper
- 006: Data Tolerance / Boundary Layer
- 007: Auth Gateway
- 008: GraphQL Layer Generation
- 009: UI Generation
- 010: K8s/Helm Deployment
- 011: LiteLLM & Model Integration
- 012: Monorepo Build System
- 013: Agent Orchestration & ADK
