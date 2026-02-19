# Implementation Plan 004: Unified Persistence Layer (`libs/ninja-persistence`)

> **Milestone**: 3 — Polyglot Persistence & Graph-RAG
> **Tickets**: 3.1, 3.2

## Objective
Build a unified persistence abstraction that allows Data Agents to perform CRUD, search, and semantic operations without knowing the underlying engine. A `UserAgent` should call `repo.find_by_id()` or `repo.search_semantic("loyal customers")` identically whether the backend is Postgres, Mongo, or Milvus.

## Requirements
- **Engine-agnostic interface**: A single `Repository` protocol that all engines implement.
- **Polyglot routing**: An entity's storage provenance (from ASD) determines which engine adapter is used.
- **First-class vector operations**: `search_semantic()`, `upsert_embedding()` available on every repository.
- **Transaction support**: Where the engine supports it (SQL), expose transaction boundaries.
- **Connection pooling**: Managed centrally, configured via `.ninjastack/connections.json`.

## Engine Adapters
| Engine | Library | Adapter |
|--------|---------|---------|
| PostgreSQL/MySQL | SQLAlchemy (async) | `SQLAdapter` |
| MongoDB | Motor / Beanie | `MongoAdapter` |
| Neo4j | neo4j-driver | `GraphAdapter` |
| Chroma | chromadb | `ChromaVectorAdapter` |
| Milvus | pymilvus | `MilvusVectorAdapter` |

## Core Interfaces
```python
class Repository(Protocol[T]):
    async def find_by_id(self, id: str) -> T | None: ...
    async def find_many(self, filters: dict) -> list[T]: ...
    async def create(self, entity: T) -> T: ...
    async def update(self, id: str, patch: dict) -> T: ...
    async def delete(self, id: str) -> bool: ...
    async def search_semantic(self, query: str, limit: int = 10) -> list[T]: ...
    async def upsert_embedding(self, id: str, embedding: list[float]) -> None: ...
```

## File Structure
```
libs/ninja-persistence/
├── pyproject.toml
├── src/ninja_persistence/
│   ├── __init__.py
│   ├── protocols.py          # Repository protocol
│   ├── registry.py           # Engine routing based on ASD provenance
│   ├── connections.py        # Connection pool management
│   ├── adapters/
│   │   ├── sql.py
│   │   ├── mongo.py
│   │   ├── graph.py
│   │   ├── chroma.py
│   │   └── milvus.py
│   └── embedding/
│       ├── __init__.py
│       └── strategy.py       # Embedding generation (Gemini, OpenAI, local)
└── tests/
```

## Acceptance Criteria
- [ ] A single `Repository` interface works across SQL, Mongo, and Vector backends.
- [ ] `search_semantic()` works on entities stored in any engine (via sidecar vector index if needed).
- [ ] Connection config is read from `.ninjastack/connections.json`.
- [ ] Adapters are pluggable — adding a new engine requires only a new adapter module.

## Dependencies
- Plan 002 (ASD Core Models — entity provenance definitions)

## Open Questions
- Should entities stored in SQL also have a sidecar vector index automatically, or opt-in only?
- How do we handle cross-engine joins (e.g., SQL entity + Mongo entity in the same domain)?
