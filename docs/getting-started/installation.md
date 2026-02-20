# Installation

## From PyPI

```bash
pip install agentic-backend
```

## From Source

```bash
git clone https://github.com/codeninja/agentic-backend.git
cd agentic-backend
uv sync
```

## Verify Installation

```bash
ninjastack --version
```

## Optional: API Key for LLM Features

The conversational setup assistant and domain agents require a Gemini API key:

```bash
export GOOGLE_API_KEY="your-key-here"
```

!!! note
    Data agents, code generation, and RBAC work without an API key.
    Only LLM-powered features (domain agents, setup assistant) need one.

## Development Setup

```bash
# Clone and install all workspace packages
git clone https://github.com/codeninja/agentic-backend.git
cd agentic-backend
uv sync

# Run tests
uv run pytest

# Run a specific library's tests
uv run pytest libs/ninja-core/
```
