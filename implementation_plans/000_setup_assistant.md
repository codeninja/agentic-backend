# Implementation Plan 000: The Ninja CLI & Setup Assistant

## Objective
Create the **`ninjastack`** CLI tool and the conversational Setup Assistant. This is the entry point for all Ninja Stack operations, from initialization to sync and deployment.

## Technical Tasks

### 1. Ninja CLI Wrapper (`ninjastack`)
- Implement a Typer-based (or similar) Python CLI.
- State management: Read/Write project configuration from the `.ninjastack/` directory.
- Command routing:
    - `init`: Triggers the Conversational Assistant.
    - `sync`: Triggers ASD-to-Code generation.
    - `create`: Scaffolds libs/apps.
    - `serve`: Wraps Uvicorn/FastAPI for library composition.

### 2. Conversational Setup Assistant
- Implement an ADK-based agent that can:
    - Interview the user about their domain.
    - Propose and refine the **Agentic Schema Definition (ASD)** stored in `.ninjastack/schema.json`.

### 3. Stack Provisioner & Sync
- Logic to translate ASD into:
    - **Library-First Structure**: `libs/domain-*` scaffolding.
    - **Thin Apps**: `apps/api` etc.
    - **ADK Configs**: `agent.yaml` using Gemini + LiteLLM.
    - **K8s Manifests**: Standardized Helm charts.

### 4. ASD Bootstrapper
- The "Code-as-Schema" engine: Translates the final ASD into living code (Pydantic models, Agents, GQL Resolvers).

## Workflow (User Experience)
1. User runs `ninja-init`.
2. Assistant: "Starting fresh or bolting on to an existing DB?"
3. If Greenfield: Assistant asks "What are we building?" and drafts the schema.
4. If Bolt-on: Assistant asks for connection strings, introspects, and presents the graph.
5. Assistant: "I've drafted the Ninja Stack. Should I provision the local environment and generate the agents?"
6. Assistant executes the plan.

## Success Criteria
- [ ] A CLI command that spawns the setup assistant.
- [ ] Ability to generate a valid ASD file solely through conversation.
- [ ] Ability to generate a valid ASD file solely through DB introspection.
- [ ] Automated generation of the directory structure and core models from an ASD.
