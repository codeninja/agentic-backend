# Example 1: Schema Definition

Define your data model using the Agentic Schema Definition.

```python title="examples/bookstore/01_schema_definition.py"
--8<-- "examples/bookstore/01_schema_definition.py"
```

## What This Shows

- **Entities** with typed fields, constraints, and storage engines
- **Relationships** — hard (FK), soft (semantic), graph
- **Domains** — logical groupings with agent config
- **AgenticSchema** — the full project container
- **Serialization** to JSON

## Run It

```bash
PYTHONPATH=examples/bookstore uv run python examples/bookstore/01_schema_definition.py
```
