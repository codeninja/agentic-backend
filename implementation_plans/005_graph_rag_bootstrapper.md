# Implementation Plan 005: Graph-RAG Bootstrapper

> **Milestone**: 3 — Polyglot Persistence & Graph-RAG
> **Tickets**: 3.3

## Objective
Automatically construct and maintain a **Knowledge Graph** (Neo4j) from the ASD and live data. This graph powers Graph-RAG: agents can traverse multi-hop relationships and retrieve semantically clustered context before reasoning.

## Requirements
- **Auto-bootstrap from ASD**: SQL FKs become graph edges. Mongo references become edges. Vector similarity clusters become soft edges.
- **Live sync**: Changes to source data propagate to the graph (via CDC or periodic sync).
- **Community detection**: Identify clusters/communities in the graph for high-level thematic queries.
- **Agent-ready traversal**: Expose graph queries as ADK tools for Domain Agents.

## Architecture
```
ASD Relationships ──→ Graph Schema (Node Labels, Edge Types)
Source Data (SQL/Mongo) ──→ Neo4j Nodes + Edges
Vector Clusters ──→ Soft Edges (similarity > threshold)
                          │
                    Community Detection
                          │
                    Agent Tool: traverse()
```

## Key Components
- **Schema Mapper**: ASD relationships → Neo4j schema (node labels, edge types, properties).
- **Data Loader**: Bulk import from SQL/Mongo into Neo4j nodes.
- **Similarity Linker**: Query vector stores to create soft edges between semantically related entities.
- **Community Builder**: Run graph algorithms (Louvain, Label Propagation) to detect entity clusters.
- **Traversal Tools**: ADK-compatible tools for agents: `find_related()`, `traverse_path()`, `get_community()`.

## File Structure
```
libs/ninja-graph/
├── pyproject.toml
├── src/ninja_graph/
│   ├── __init__.py
│   ├── mapper.py             # ASD → Neo4j schema
│   ├── loader.py             # Bulk data import
│   ├── linker.py             # Vector similarity → soft edges
│   ├── community.py          # Community detection algorithms
│   └── tools.py              # ADK tool definitions for agents
└── tests/
```

## Acceptance Criteria
- [ ] Given an ASD with SQL FKs, auto-create equivalent Neo4j edges.
- [ ] Given vector embeddings, create soft edges for entities above a similarity threshold.
- [ ] Community detection produces meaningful clusters on a sample dataset.
- [ ] Domain Agents can call `find_related(entity_id, depth=2)` as an ADK tool.

## Dependencies
- Plan 002 (ASD Core Models)
- Plan 004 (Unified Persistence — for reading source data)

## Open Questions
- CDC vs periodic batch sync for keeping the graph current?
- Should community labels feed back into the ASD as "discovered domains"?
