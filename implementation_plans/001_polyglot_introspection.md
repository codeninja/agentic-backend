# Implementation Plan 001: Polyglot & Graph Introspection

## Objective
Build a unified introspection engine that can consume connection strings for SQL (Postgres), NoSQL (MongoDB), Graph (Neo4j), and Vector (Milvus/Chroma) and output a standardized **Agentic Schema Definition (ASD)**.

## ASD (Agentic Schema Definition)
A Pydantic-based intermediate representation that describes:
- **Entities**: Fields, types, constraints, and embeddings.
- **Relationships**: Hard (FKs), Soft (Semantic/Vector), and Graph (Nodes/Edges).
- **Metadata**: Provenance (where the data lives) and access patterns.

## Technical Tasks

### 1. Unified Model Definitions
Define the Pydantic models in `src/generator/models.py`:
- `EntitySchema`: Unified view of a table/collection/node.
- `RelationshipSchema`: Type-agnostic relationship (SQL FK, Mongo Ref, Graph Edge).
- `AgenticSchema`: The full Ninja Stack definition.

### 2. Provider Implementation
Create an extensible provider pattern in `src/generator/providers/`:
- `SQLProvider`: Uses SQLAlchemy to introspect Postgres/MySQL schemas.
- `NoSQLProvider`: Uses Motor to sample MongoDB collections and infer schema.
- `GraphProvider`: Uses Neo4j drivers to map labels and relationship types.
- `VectorProvider`: Pulls metadata/collections from Milvus/Chroma.

### 3. Graph-RAG Bootstrapper
- Logic to automatically create a "Knowledge Graph" from existing SQL/NoSQL schemas.
- Map SQL Foreign Keys → Graph Edges.
- Map Document Embeddings → Vector Clusters.

### 4. Code Generation Engine
Generate the boilerplate for:
- `Data Agents` (ADK-compatible Python classes).
- `GraphQL Resolvers` (Strawberry).
- `Pydantic Boundary Models` (Coercion logic).

## Success Criteria
- [ ] Connect to a Postgres instance and generate a full ASD.
- [ ] Connect to a MongoDB instance and infer ASD from 100 sample docs.
- [ ] Merge both into a single ASD with inferred cross-database relationships.
- [ ] Bootstrap a Neo4j knowledge graph from the ASD.
