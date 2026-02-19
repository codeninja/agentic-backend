# Implementation Plan 012: Monorepo Build System & Library Testing

> **Milestone**: 1 — The Foundation
> **Tickets**: (New)

## Objective
Establish the build system, dependency management, and testing infrastructure for the library-first monorepo. Every library must be independently buildable, testable, and publishable.

## Requirements
- **Independent libraries**: Each `libs/*` package has its own `pyproject.toml`, dependencies, and test suite.
- **Workspace management**: A monorepo tool that understands inter-library dependencies.
- **Affected testing**: Only test libraries that changed (or whose dependencies changed).
- **Consistent tooling**: Standardized linting, formatting, and type checking across all libraries.
- **CI integration**: GitHub Actions runs affected tests on PR, full suite on merge.

## Build System Options
| Tool | Pros | Cons |
|------|------|------|
| **uv workspaces** | Native Python, fast, already in stack | Newer, less ecosystem |
| **NX (Python plugin)** | Mature affected graph, familiar | Node dependency, heavier |
| **Pants / Bazel** | Enterprise-grade, hermetic | Complex setup |
| **Simple Makefile** | Zero deps, transparent | Manual dependency tracking |

**Recommendation**: Start with **uv workspaces** for simplicity. Migrate to NX or Pants if the monorepo exceeds ~20 libraries.

## Standards
- **Linting**: Ruff
- **Formatting**: Ruff format
- **Type checking**: Pyright (strict mode)
- **Testing**: Pytest with per-library `tests/` directories
- **Coverage**: Minimum 80% per library

## File Structure (Root)
```
agentic-backend/
├── pyproject.toml            # Workspace root (uv workspace)
├── libs/
│   ├── ninja-core/
│   │   ├── pyproject.toml
│   │   ├── src/ninja_core/
│   │   └── tests/
│   ├── ninja-persistence/
│   ├── ninja-auth/
│   ├── ninja-codegen/
│   ├── ninja-graph/
│   ├── ninja-boundary/
│   ├── ninja-gql/
│   ├── ninja-models/
│   ├── ninja-deploy/
│   └── ninja-ui/
├── apps/
│   ├── ninja-api/            # FastAPI shell
│   └── ninja-setup-assistant/ # CLI agent
├── .ninjastack/              # Project state
├── .github/workflows/
└── docs/
```

## Acceptance Criteria
- [ ] `uv sync` from root resolves all inter-library dependencies.
- [ ] `uv run pytest libs/ninja-core` runs only ninja-core tests.
- [ ] Adding a dependency to `ninja-persistence` that depends on `ninja-core` works seamlessly.
- [ ] CI pipeline runs only affected library tests on PR.
- [ ] Ruff + Pyright pass across all libraries with zero warnings.

## Dependencies
- None (this is infrastructure — must be established before any library code).
