"""Shared fixtures for ninja-ui tests."""

from __future__ import annotations

import pytest
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


def _customer_entity() -> EntitySchema:
    return EntitySchema(
        name="Customer",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(
                name="name",
                field_type=FieldType.STRING,
                constraints=FieldConstraint(min_length=1, max_length=100),
            ),
            FieldSchema(name="email", field_type=FieldType.STRING),
            FieldSchema(name="active", field_type=FieldType.BOOLEAN, nullable=True),
        ],
        description="A customer.",
    )


def _order_entity() -> EntitySchema:
    return EntitySchema(
        name="Order",
        storage_engine=StorageEngine.SQL,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="customer_id", field_type=FieldType.UUID),
            FieldSchema(
                name="total",
                field_type=FieldType.FLOAT,
                constraints=FieldConstraint(ge=0),
            ),
            FieldSchema(name="status", field_type=FieldType.STRING),
        ],
        description="A purchase order.",
    )


def _product_entity() -> EntitySchema:
    return EntitySchema(
        name="Product",
        storage_engine=StorageEngine.VECTOR,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="price", field_type=FieldType.FLOAT),
            FieldSchema(
                name="description",
                field_type=FieldType.TEXT,
                nullable=True,
                embedding=EmbeddingConfig(model="text-embedding-3-small", dimensions=256),
            ),
        ],
        description="A product with vector search.",
    )


@pytest.fixture()
def sample_asd() -> AgenticSchema:
    """Return a 3-entity ASD with relationships and domains."""
    return AgenticSchema(
        project_name="test-shop",
        entities=[_customer_entity(), _order_entity(), _product_entity()],
        relationships=[
            RelationshipSchema(
                name="customer_orders",
                source_entity="Customer",
                target_entity="Order",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_MANY,
                source_field="id",
                target_field="customer_id",
            ),
        ],
        domains=[
            DomainSchema(name="Sales", entities=["Customer", "Order"]),
            DomainSchema(name="Catalog", entities=["Product"]),
        ],
    )


@pytest.fixture()
def customer_entity() -> EntitySchema:
    return _customer_entity()


@pytest.fixture()
def order_entity() -> EntitySchema:
    return _order_entity()


@pytest.fixture()
def product_entity() -> EntitySchema:
    return _product_entity()
