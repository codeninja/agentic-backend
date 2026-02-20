# Quickstart

Build a bookstore agentic backend in under 5 minutes.

## Option A: Bolt-on to an Existing Database

```bash
# Introspect your database
ninjastack introspect --db postgres://localhost/bookstore

# Review the discovered schema
cat .ninjastack/schema.json

# Generate the full stack
ninjastack sync

# Start the server
ninjastack serve
```

## Option B: Design from Scratch

```python
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.project import AgenticSchema

# Define an entity
book = EntitySchema(
    name="Book",
    storage_engine=StorageEngine.SQL,
    fields=[
        FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
        FieldSchema(name="title", field_type=FieldType.STRING, indexed=True),
        FieldSchema(name="author", field_type=FieldType.STRING),
        FieldSchema(name="price", field_type=FieldType.FLOAT),
    ],
)

# Group into a domain
catalog = DomainSchema(name="Catalog", entities=["Book"])

# Create the project schema
schema = AgenticSchema(
    project_name="Bookstore",
    entities=[book],
    domains=[catalog],
)
```

## Option C: Conversational Setup

```bash
ninjastack init --interactive

# Chat with the AI assistant:
# "I need a bookstore with books, customers, orders, and reviews.
#  Reviews should support semantic search."
```

## What Gets Generated

After `ninjastack sync`, you get:

| Generated | Description |
|-----------|-------------|
| `_generated/models/` | Pydantic models per entity |
| `_generated/agents/` | ADK DataAgent + DomainAgent + CoordinatorAgent |
| `_generated/graphql/` | Strawberry types, queries, mutations |
| `.ninjastack/schema.json` | Your Agentic Schema Definition |

## Next Steps

- [Concepts](concepts.md) — Understand the architecture
- [Examples](../examples/index.md) — Walk through the full bookstore example
