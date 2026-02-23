#!/usr/bin/env python3
"""Example 2: Code Generation — Generate models, agents, and GraphQL from a schema.

Demonstrates:
- Running the codegen engine against an AgenticSchema
- Generated Pydantic models (one per entity)
- Generated ADK DataAgent/DomainAgent/CoordinatorAgent stubs
- Generated Strawberry GraphQL types, queries, and mutations
- Inspecting generated file contents
"""

import tempfile
from pathlib import Path

# Re-use the bookstore schema from Example 1
from _bookstore_schema import SCHEMA
from ninja_codegen.generators.agents import generate_agents
from ninja_codegen.generators.graphql import generate_graphql
from ninja_codegen.generators.models import generate_models

# ---------------------------------------------------------------------------
# 1. Generate Pydantic Models
# ---------------------------------------------------------------------------

output_dir = Path(tempfile.mkdtemp(prefix="ninjastack-gen-"))
print(f"📁 Output directory: {output_dir}\n")

model_paths = generate_models(SCHEMA.entities, output_dir)
print("✅ Generated Pydantic models:")
for p in model_paths:
    print(f"   {p.relative_to(output_dir)}")

# Show one generated model
book_model = (output_dir / "_generated" / "models" / "book.py").read_text()
print("\n--- book.py (first 30 lines) ---")
for line in book_model.splitlines()[:30]:
    print(f"  {line}")

# ---------------------------------------------------------------------------
# 2. Generate ADK Agent Stubs
# ---------------------------------------------------------------------------

agent_paths = generate_agents(SCHEMA.entities, SCHEMA.domains, output_dir)
print("\n✅ Generated ADK agents:")
for p in agent_paths:
    print(f"   {p.relative_to(output_dir)}")

# Show a data agent
book_agent = (output_dir / "_generated" / "agents" / "book_agent.py").read_text()
print("\n--- book_agent.py ---")
for line in book_agent.splitlines():
    print(f"  {line}")

# Show a domain agent
catalog_agent = (output_dir / "_generated" / "agents" / "catalog_agent.py").read_text()
print("\n--- catalog_agent.py ---")
for line in catalog_agent.splitlines():
    print(f"  {line}")

# ---------------------------------------------------------------------------
# 3. Generate GraphQL Types
# ---------------------------------------------------------------------------

gql_paths = generate_graphql(SCHEMA.entities, output_dir)
print("\n✅ Generated GraphQL types:")
for p in gql_paths:
    print(f"   {p.relative_to(output_dir)}")

# Show one GQL type
book_gql = (output_dir / "_generated" / "graphql" / "book_gql.py").read_text()
print("\n--- book_gql.py (first 40 lines) ---")
for line in book_gql.splitlines()[:40]:
    print(f"  {line}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

all_files = list((output_dir / "_generated").rglob("*.py"))
print(f"\n📊 Total generated files: {len(all_files)}")
print(f"   Models:  {len(model_paths)}")
print(f"   Agents:  {len(agent_paths)}")
print(f"   GraphQL: {len(gql_paths)}")
print("\n💡 These files are what `ninjastack sync` produces from your schema.json")
