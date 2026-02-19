# Implementation Plan 001: Unified Agentic Pipeline

## Overview
This plan outlines the integration of the 'Pydantic -> REST -> GQL' pipeline with the 'GQL -> MCP' bridge concept, establishing a 'Schema-first Single Source of Truth' architecture. The goal is to provide a seamless flow from raw data schemas to agent-ready tools.

## Architecture: The Unified Pipeline

1.  **Source of Truth**: Database Schema (SQL, MongoDB, etc.)
2.  **Introspection Layer**: Python (uv) based introspection using Pydantic for model generation.
3.  **Intermediate Representations**:
    *   **Pydantic Models**: Type-safe Python representations of the data.
    *   **REST Layer**: Deterministic CRUD endpoints generated from models.
    *   **GQL Layer**: Aggregated GraphQL schema providing a flexible query interface.
4.  **The MCP Bridge (The Final Mile)**:
    *   The `gql-mcp-bridge` service consumes the GQL schema.
    *   It dynamically exposes GQL operations (queries/mutations) as **Model Context Protocol (MCP)** tools.
    *   Agents (Coordinators, Domain Agents, Data Agents) use these MCP tools to interact with the backend.

## Key Concepts

### 1. Schema-first Single Source of Truth
*   Any change in the DB schema propagates through the pipeline.
*   Pydantic models are the primary definition point for validation and types.
*   GQL schema acts as the unified contract for the bridge.

### 2. Data Tolerance & Progressive Strictness
*   **Boundary Layer**: Implement Pydantic validators that handle "dirty" data (coercion, defaults).
*   **Logging**: Track where coercion occurs to identify schema drift or data quality issues.
*   **Evolution**: Gradually tighten validation rules as data is cleaned or migrated.

### 3. Generation Pipeline
1.  **Introspect**: Scan DB for tables/collections.
2.  **Model**: Generate Pydantic classes.
3.  **Bridge**: 
    *   `src/bridge/`: Code to map Pydantic -> GQL.
    *   `src/mcp/`: Configuration for the GQL-to-MCP bridge.
4.  **Orchestrate**:
    *   Generate Data Agents (entity-level).
    *   Generate Domain Agents (relationship-level).
    *   Generate Use Case Coordinators (workflow-level).

## Implementation Steps

### Phase 1: Core Scaffolding (Python/uv)
*   Initialize `uv` project in `src/`.
*   Implement basic introspection script for SQLite/PostgreSQL.
*   Generate Pydantic models from schema.

### Phase 2: GQL & Bridge (Node/pnpm)
*   Setup GQL server (e.g., Apollo or Yoga) in `src/server`.
*   Integrate `gql-mcp-bridge` as a submodule or sibling service.
*   Verify that GQL mutations are visible as MCP tools.

### Phase 3: Agentic Hierarchy
*   Define base classes for `DataAgent`, `DomainAgent`, and `Coordinator`.
*   Implement a "Shopping Cart" or "User Management" prototype following the hierarchy.

## Future Vision: The Orchestrator
The `agentic-backend` project serves as the orchestrator. It doesn't just provide a bridge; it manages the *lifecycle* of the entire agentic stack, from schema introspection to agent deployment.
