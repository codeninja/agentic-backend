# Agentic Backend: The Orchestrator

The **Agentic Backend** is a schema-first framework designed to transform traditional data layers into unified agentic architectures. It serves as the **Orchestrator** for the 'Unified Agentic Pipeline', managing everything from database introspection to the deployment of Model Context Protocol (MCP) tools.

## Unified Pipeline Vision

This project implements a seamless 'Schema-first Single Source of Truth' architecture:

`DB Schema` → `Pydantic Models` → `REST/GQL Layer` → `GQL-to-MCP Bridge` → `Agent Tools`

By pointing this orchestrator at a database, you get a full stack of agents capable of understanding, querying, and mutating your data with high reliability.

## Agent Hierarchy

The backend organizes intelligence into a clear hierarchy:

1.  **Use Case Coordinators**: Top-level orchestrators for complex workflows (e.g., "Onboard a new customer"). They delegate to Domain Agents.
2.  **Domain Agents**: Experts in specific business domains (e.g., "Orders", "Users"). They understand relationships and compose multiple Data Agents.
3.  **Data Agents**: Entity-level experts. They provide granular CRUD operations and entity-specific logic via the GQL/MCP bridge.

## Core Principles

*   **Schema-first**: The data model is the source of truth. All models, agents, and GQL schemas are derived from it.
*   **Data Tolerance**: A robust boundary layer handles "dirty" data through type coercion, defaults, and progressive strictness.
*   **LLM where it matters**: Deterministic paths stay deterministic; LLMs are reserved for reasoning, ambiguity, and complex orchestration.
*   **GQL -> MCP Bridge**: Uses the `gql-mcp-bridge` concept to turn any GraphQL operation into a standard MCP tool, making the backend instantly usable by any agentic system.

## Project Structure

*   `src/`: Core implementation (Python/uv for introspection, Node/pnpm for GQL/Bridge).
*   `docs/`: Deep-dive documentation on architecture and design patterns.
*   `implementation_plans/`: Step-by-step blueprints for new features and integrations.

## Getting Started

### Prerequisites
*   [uv](https://github.com/astral-sh/uv) (Python package manager)
*   [pnpm](https://pnpm.io/) (Node package manager)

### Installation
1.  Clone the repo.
2.  Follow instructions in `src/README.md` (coming soon) to connect your database.

## Status: Revival in Progress
The project is currently being restructured to align with the unified pipeline vision. See `implementation_plans/001-unified-pipeline.md` for details.
