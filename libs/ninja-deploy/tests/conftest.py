"""Shared fixtures for ninja-deploy tests."""

from __future__ import annotations

import pytest
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import (
    EmbeddingConfig,
    EntitySchema,
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
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="email", field_type=FieldType.STRING),
        ],
        description="A customer.",
    )


def _order_entity() -> EntitySchema:
    return EntitySchema(
        name="Order",
        storage_engine=StorageEngine.MONGO,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="customer_id", field_type=FieldType.UUID),
            FieldSchema(name="total", field_type=FieldType.FLOAT),
        ],
        description="An order stored in MongoDB.",
    )


def _product_entity() -> EntitySchema:
    return EntitySchema(
        name="Product",
        storage_engine=StorageEngine.VECTOR,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(
                name="description",
                field_type=FieldType.TEXT,
                nullable=True,
                embedding=EmbeddingConfig(model="text-embedding-3-small", dimensions=256),
            ),
        ],
        description="A product with vector search.",
    )


def _graph_entity() -> EntitySchema:
    return EntitySchema(
        name="Category",
        storage_engine=StorageEngine.GRAPH,
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
        description="Category node in graph DB.",
    )


@pytest.fixture()
def sample_asd() -> AgenticSchema:
    """ASD with all 4 storage engines (SQL, Mongo, Graph, Vector)."""
    return AgenticSchema(
        project_name="test-shop",
        entities=[_customer_entity(), _order_entity(), _product_entity(), _graph_entity()],
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
            DomainSchema(name="Catalog", entities=["Product", "Category"]),
        ],
    )


@pytest.fixture()
def sql_only_asd() -> AgenticSchema:
    """ASD with only SQL storage engine."""
    return AgenticSchema(
        project_name="simple-app",
        entities=[_customer_entity()],
        domains=[DomainSchema(name="Core", entities=["Customer"])],
    )
