# Agentic Backend

Schema-first agentic backend framework. Point at a database, get a full agentic backend + UI.

## Vision

Replace or migrate traditional backends to an agentic architecture through automated introspection or conversational design:

1. **Introspection Mode (Bolt-on)**: Connect to existing databases (SQL, NoSQL, Graph, Vector) and auto-generate the Ninja Stack.
2. **Conversation Mode (Greenfield)**: Converse with the Ninja Setup Assistant to define your domain; it writes the schemas and provisions the tech stack for you.
3. **Hybrid Mode**: Bolt on to an existing system, then use the agent to expand the schema or migrate logic.
4. **Auto-generate the Ninja Stack**: Models, agents, GQL layer, and prompts are derived from the Agentic Schema Definition (ASD).
5. **Spin up UIs**: CRUD data viewer + agentic chat interface.

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
┌───────────────────────────────────────────────────────────┐
│                   Data Agents (Polyglot)                  │
│  ┌─────────────┬─────────────┬─────────────┬───────────┐  │
│  │    User     │   Address   │   Product   │ Semantic  │  │
│  │   Agent     │   Agent     │   Agent     │ Context   │  │
│  └─────────────┴─────────────┴─────────────┴───────────┘  │
└───────────────────────────────────────────────────────────┘
                          │
┌───────────────────────────────────────────────────────────┐
│               Unified Persistence Layer                   │
│      (SQL / NoSQL / Graph / Vector / External API)        │
└───────────────────────────────────────────────────────────┘
              ┌─────┴─────┬──────────┬──────────┐
              │    DB     │  Vector  │  Graph   │
              │(SQL/NoSQL)│  Store   │   DB     │
              └───────────┴──────────┴──────────┘
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
- Use **Graph-RAG** to navigate multi-hop relationships and semantic clusters
- Example: User Domain Agent contains User + Address agents, knows users have addresses

### Data Agents
- Single-entity experts
- CRUD operations + entity-specific business logic
- Interface with the Persistence Layer
- Not all agents need LLM — many are deterministic data fetchers

## Design Principles

- **Library-First Development**: All business logic, domain models, and agent behaviors live in granular, modular libraries. Applications are pure composition; they contain zero business logic.
- **Composition over Application**: Deployable units are assembled from versioned libraries by the build system.
- **AI-First Persistence**: Vector and Graph stores are first-class storage targets. Every entity has an optional embedding and a node in the global knowledge graph.
- **Polyglot Introspection**: Support for Postgres (SQL), MongoDB (NoSQL), Neo4j (Graph), and direct Vector-only entities.
- **Graph-Native Reasoning**: Native support for Graph-RAG for complex relationship traversal.
- **Schema-first**: The data model is the source of truth; everything derives from it.
- **Explicit > implicit**: Clear ownership, typed contracts.
- **LLM where it matters**: Reserve reasoning for ambiguity, keep hot paths deterministic.
- **Tolerance for dirty data**: Boundary layer handles schema drift, coercion, missing fields.

## Usage: The Ninja CLI

The Ninja Stack is managed via a unified CLI. 

### Installation
```bash
uv tool install ninjastack
```

### Commands
- **`ninjastack init`**: Spawns the Conversational Setup Assistant. Handles DB introspection or greenfield schema design. Creates the `.ninjastack/` directory.
- **`ninjastack sync`**: Runs the polyglot introspection and code generation engine. Syncs the `.ninjastack/` state with your `libs/` and `apps/`.
- **`ninjastack create [app|lib|agent]`**: Scaffolds new components into the monorepo following the composition-first pattern.
- **`ninjastack serve [app]`**: Starts a local development server for a specific app (FastAPI, CRUD UI, etc.).
- **`ninjastack deploy [app]`**: Triggers the K8s/Helm deployment workflow.

## Project State: `.ninjastack/`

All project metadata, the Agentic Schema Definition (ASD), and connection profiles are stored in the `.ninjastack/` directory at the project root. This ensures the environment is reproducible and the Ninja agents have a persistent "anchor" for the project's evolution.


## Multi-Engine Support

### Relational (Postgres/MySQL)
- Foreign-key based relationship mapping.
- Structured GQL schema generation.

### Document (MongoDB/DynamoDB)
- Schema inference from sample sets.
- Nested object flattening for agent tools.

### Graph (Neo4j/FalkorDB)
- Native relationship traversal.
- Knowledge Graph construction from polyglot sources.

### Vector (Chroma/Milvus/Pinecone)
- Semantic search as a native tool for every Data Agent.
- "Long-term entity memory" integrated into the persistence layer.

## Graph-RAG & Discovery

The backend doesn't just store data; it maps it:

1. **Extraction**: Automated entity and relationship extraction from structured and unstructured sources.
2. **Indexing**: Graph-native indexing (communities, clusters) for high-level thematic queries.
3. **Traversal**: Agents use graph traversal to answer "Why" and "How" by following semantic and hard links across the polyglot stack.

## Data Tolerance

Real-world data is messy. The boundary layer handles:

- **Missing fields** — convention-based defaults
- **Type coercion** — int↔string, flexible timestamps
- **Schema drift** — especially for schemaless databases (MongoDB)
- **Progressive strictness** — log coercions, tighten rules based on observed patterns

## Generation Pipeline

```
Polyglot Introspection (SQL/NoSQL/Vector)
        ↓
Pydantic Models (Unified Representation)
        ↓
Data Agents (per entity)
        ↓
Domain Agents (inferred from FKs or semantic links)
        ↓
Use Case Coordinators (common patterns)
        ↓
GQL Layer (auto-generated)
        ↓
UIs: CRUD Viewer + Agentic Chat
```

## Status

Early development.

## Tech Stack

- **Core Platform**: Google Gemini (Pro/Flash)
- **Agentic Framework**: Google ADK (Agent Development Kit)
- **Model Interoperability**: LiteLLM integration via ADK connectors (Ollama, OpenAI, Anthropic support)
- **Core Languages**: Python (Backend/Agents), Pydantic (Contracts)
- **Persistence**: SQLAlchemy (SQL), Motor/Beanie (Mongo), Neo4j (Graph), Chroma/Milvus (Vector)
- **API**: FastAPI, Strawberry (GraphQL)

## License

TBD
