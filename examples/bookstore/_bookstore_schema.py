"""Shared bookstore schema used by all examples."""

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

# --- Entities ---

BOOK = EntitySchema(
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

CUSTOMER = EntitySchema(
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

ORDER = EntitySchema(
    name="Order",
    storage_engine=StorageEngine.SQL,
    description="A purchase order.",
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

REVIEW = EntitySchema(
    name="Review",
    storage_engine=StorageEngine.SQL,
    description="A customer review of a book.",
    fields=[
        FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
        FieldSchema(name="book_id", field_type=FieldType.UUID, indexed=True),
        FieldSchema(name="customer_id", field_type=FieldType.UUID, indexed=True),
        FieldSchema(name="rating", field_type=FieldType.INTEGER, constraints=FieldConstraint(ge=1, le=5)),
        FieldSchema(
            name="text",
            field_type=FieldType.TEXT,
            embedding=EmbeddingConfig(model="text-embedding-3-small", dimensions=1536, chunk_strategy="paragraph"),
        ),
        FieldSchema(name="created_at", field_type=FieldType.DATETIME),
    ],
)

ENTITIES = [BOOK, CUSTOMER, ORDER, REVIEW]

# --- Relationships ---

RELATIONSHIPS = [
    RelationshipSchema(
        name="order_customer",
        source_entity="Order",
        target_entity="Customer",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.MANY_TO_ONE,
        source_field="customer_id",
        target_field="id",
    ),
    RelationshipSchema(
        name="review_book",
        source_entity="Review",
        target_entity="Book",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.MANY_TO_ONE,
        source_field="book_id",
        target_field="id",
    ),
    RelationshipSchema(
        name="review_customer",
        source_entity="Review",
        target_entity="Customer",
        relationship_type=RelationshipType.HARD,
        cardinality=Cardinality.MANY_TO_ONE,
        source_field="customer_id",
        target_field="id",
    ),
    RelationshipSchema(
        name="book_similar_reviews",
        source_entity="Book",
        target_entity="Review",
        relationship_type=RelationshipType.SOFT,
        cardinality=Cardinality.MANY_TO_MANY,
    ),
]

# --- Domains ---

CATALOG_DOMAIN = DomainSchema(
    name="Catalog",
    entities=["Book", "Review"],
    description="Book catalog and reviews.",
    agent_config=AgentConfig(
        model_provider="gemini",
        model_name="gemini-2.5-flash",
        reasoning_level=ReasoningLevel.MEDIUM,
        system_prompt="You are the Catalog agent. Help users find books and reviews.",
    ),
)

COMMERCE_DOMAIN = DomainSchema(
    name="Commerce",
    entities=["Customer", "Order"],
    description="Customer management and order processing.",
    agent_config=AgentConfig(
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        reasoning_level=ReasoningLevel.HIGH,
        temperature=0.3,
        system_prompt="You are the Commerce agent. Handle customer accounts and orders accurately.",
    ),
)

DOMAINS = [CATALOG_DOMAIN, COMMERCE_DOMAIN]

# --- Full Schema ---

SCHEMA = AgenticSchema(
    project_name="Bookstore",
    description="Online bookstore with catalog, commerce, and semantic review search.",
    entities=ENTITIES,
    relationships=RELATIONSHIPS,
    domains=DOMAINS,
)
