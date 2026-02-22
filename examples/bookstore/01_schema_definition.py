#!/usr/bin/env python3
"""Example 1: Schema Definition — Defining your data model with the ASD.

Demonstrates:
- Creating entities with typed fields, constraints, and storage engines
- Defining relationships between entities (hard FK, soft semantic, graph)
- Grouping entities into domains with agent configuration
- Assembling the full AgenticSchema (project-level container)
- Serializing to .ninjastack/schema.json
"""

from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import (
    EmbeddingConfig,
    EntitySchema,
    FieldConstraint,
    FieldSchema,
    FieldType,
    StorageEngine,
)
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType

# ---------------------------------------------------------------------------
# 1. Define Entities
# ---------------------------------------------------------------------------

book = EntitySchema(
    name="Book",
    storage_engine=StorageEngine.SQL,
    description="A book in the catalog.",
    fields=[
        FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
        FieldSchema(
            name="title",
            field_type=FieldType.STRING,
            indexed=True,
            constraints=FieldConstraint(min_length=1, max_length=500),
        ),
        FieldSchema(name="author", field_type=FieldType.STRING, indexed=True),
        FieldSchema(
            name="isbn", field_type=FieldType.STRING, unique=True, constraints=FieldConstraint(pattern=r"^\d{13}$")
        ),
        FieldSchema(name="price", field_type=FieldType.FLOAT, constraints=FieldConstraint(ge=0.0)),
        FieldSchema(
            name="genre",
            field_type=FieldType.ENUM,
            constraints=FieldConstraint(enum_values=["fiction", "non-fiction", "sci-fi", "mystery", "biography"]),
        ),
        FieldSchema(name="published_date", field_type=FieldType.DATE, nullable=True),
        FieldSchema(name="in_stock", field_type=FieldType.BOOLEAN, default=True),
    ],
)

customer = EntitySchema(
    name="Customer",
    storage_engine=StorageEngine.SQL,
    description="A registered bookstore customer.",
    fields=[
        FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
        FieldSchema(name="email", field_type=FieldType.STRING, unique=True),
        FieldSchema(name="name", field_type=FieldType.STRING),
        FieldSchema(name="joined_at", field_type=FieldType.DATETIME),
    ],
)

order = EntitySchema(
    name="Order",
    storage_engine=StorageEngine.SQL,
    description="A purchase order linking a customer to books.",
    fields=[
        FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
        FieldSchema(name="customer_id", field_type=FieldType.UUID, indexed=True),
        FieldSchema(name="total", field_type=FieldType.FLOAT, constraints=FieldConstraint(ge=0.0)),
        FieldSchema(
            name="status",
            field_type=FieldType.ENUM,
            constraints=FieldConstraint(enum_values=["pending", "confirmed", "shipped", "delivered", "cancelled"]),
        ),
        FieldSchema(name="created_at", field_type=FieldType.DATETIME),
    ],
)

review = EntitySchema(
    name="Review",
    storage_engine=StorageEngine.SQL,
    description="A customer review of a book. Text is semantic-searchable.",
    fields=[
        FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
        FieldSchema(name="book_id", field_type=FieldType.UUID, indexed=True),
        FieldSchema(name="customer_id", field_type=FieldType.UUID, indexed=True),
        FieldSchema(name="rating", field_type=FieldType.INTEGER, constraints=FieldConstraint(ge=1, le=5)),
        FieldSchema(
            name="text",
            field_type=FieldType.TEXT,
            description="Free-text review body — vectorized for semantic search.",
            embedding=EmbeddingConfig(
                model="text-embedding-3-small",
                dimensions=1536,
                chunk_strategy="paragraph",
            ),
        ),
        FieldSchema(name="created_at", field_type=FieldType.DATETIME),
    ],
)

print("✅ Entities defined:")
for e in [book, customer, order, review]:
    print(f"   {e.name} ({e.storage_engine.value}) — {len(e.fields)} fields")

# ---------------------------------------------------------------------------
# 2. Define Relationships
# ---------------------------------------------------------------------------

relationships = [
    # Hard FK: Order → Customer
    RelationshipSchema(
        name="order_customer",
        source_entity="Order",
        target_entity="Customer",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.MANY_TO_ONE,
        source_field="customer_id",
        target_field="id",
        description="Each order belongs to one customer.",
    ),
    # Hard FK: Review → Book
    RelationshipSchema(
        name="review_book",
        source_entity="Review",
        target_entity="Book",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.MANY_TO_ONE,
        source_field="book_id",
        target_field="id",
        description="Each review is about one book.",
    ),
    # Hard FK: Review → Customer
    RelationshipSchema(
        name="review_customer",
        source_entity="Review",
        target_entity="Customer",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.MANY_TO_ONE,
        source_field="customer_id",
        target_field="id",
        description="Each review is written by one customer.",
    ),
    # Soft/Semantic: Book ↔ Review (vector similarity for recommendations)
    RelationshipSchema(
        name="book_similar_reviews",
        source_entity="Book",
        target_entity="Review",
        relationship_type=RelationshipType.SOFT,
        cardinality=Cardinality.MANY_TO_MANY,
        description="Semantic similarity between book descriptions and review text.",
    ),
]

print(f"\n✅ Relationships defined: {len(relationships)}")
for r in relationships:
    print(f"   {r.name}: {r.source_entity} → {r.target_entity} ({r.relationship_type.value}, {r.cardinality.value})")

# ---------------------------------------------------------------------------
# 3. Define Domains
# ---------------------------------------------------------------------------

catalog_domain = DomainSchema(
    name="Catalog",
    entities=["Book", "Review"],
    description="Book catalog and reviews — handles browsing, search, and recommendations.",
    agent_config=AgentConfig(
        model_provider="gemini",
        model_name="gemini-2.5-flash",
        reasoning_level=ReasoningLevel.MEDIUM,
        system_prompt=(
            "You are the Catalog domain agent. Help users find books, browse reviews, and get recommendations."
        ),
    ),
)

commerce_domain = DomainSchema(
    name="Commerce",
    entities=["Customer", "Order"],
    description="Customer management and order processing.",
    agent_config=AgentConfig(
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        reasoning_level=ReasoningLevel.HIGH,
        temperature=0.3,  # Lower temp for transactional operations
        system_prompt="You are the Commerce domain agent. Handle customer accounts and order operations accurately.",
    ),
)

print(f"\n✅ Domains defined: {len([catalog_domain, commerce_domain])}")
for d in [catalog_domain, commerce_domain]:
    model = d.agent_config.model_name
    reasoning = d.agent_config.reasoning_level.value
    print(f"   {d.name}: entities={d.entities}, model={model}, reasoning={reasoning}")

# ---------------------------------------------------------------------------
# 4. Assemble the Full Schema
# ---------------------------------------------------------------------------

schema = AgenticSchema(
    project_name="Bookstore",
    description="Online bookstore with catalog, commerce, and semantic review search.",
    entities=[book, customer, order, review],
    relationships=relationships,
    domains=[catalog_domain, commerce_domain],
)

print(f"\n✅ AgenticSchema assembled: '{schema.project_name}'")
print(f"   {len(schema.entities)} entities, {len(schema.relationships)} relationships, {len(schema.domains)} domains")

# ---------------------------------------------------------------------------
# 5. Serialize to JSON (what .ninjastack/schema.json looks like)
# ---------------------------------------------------------------------------

json_output = schema.model_dump_json(indent=2)
print(f"\n📄 Serialized schema ({len(json_output)} bytes):")
print(json_output[:500] + "..." if len(json_output) > 500 else json_output)

# You can also save to disk:
# save_schema(schema, ".ninjastack/schema.json")
