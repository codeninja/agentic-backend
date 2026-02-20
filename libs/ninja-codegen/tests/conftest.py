"""Shared test fixtures for ninja-codegen."""

from __future__ import annotations

import pytest
from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import Cardinality, RelationshipSchema, RelationshipType


@pytest.fixture
def order_entity() -> EntitySchema:
    return EntitySchema(
        name="Order",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="customer_id", field_type=FieldType.UUID),
            FieldSchema(name="total", field_type=FieldType.FLOAT),
            FieldSchema(name="status", field_type=FieldType.STRING),
            FieldSchema(name="created_at", field_type=FieldType.DATETIME, nullable=True),
        ],
        description="A customer order",
    )


@pytest.fixture
def product_entity() -> EntitySchema:
    return EntitySchema(
        name="Product",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="price", field_type=FieldType.FLOAT),
            FieldSchema(name="in_stock", field_type=FieldType.BOOLEAN),
        ],
    )


@pytest.fixture
def customer_entity() -> EntitySchema:
    return EntitySchema(
        name="Customer",
        storage_engine="mongo",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="email", field_type=FieldType.STRING, unique=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
        ],
    )


@pytest.fixture
def billing_domain() -> DomainSchema:
    return DomainSchema(
        name="Billing",
        entities=["Order", "Customer"],
        agent_config=AgentConfig(reasoning_level=ReasoningLevel.MEDIUM),
        description="Handles billing and orders",
    )


@pytest.fixture
def inventory_domain() -> DomainSchema:
    return DomainSchema(
        name="Inventory",
        entities=["Product"],
        agent_config=AgentConfig(reasoning_level=ReasoningLevel.LOW),
    )


@pytest.fixture
def sample_schema(
    order_entity: EntitySchema,
    product_entity: EntitySchema,
    customer_entity: EntitySchema,
    billing_domain: DomainSchema,
    inventory_domain: DomainSchema,
) -> AgenticSchema:
    return AgenticSchema(
        project_name="TestProject",
        entities=[order_entity, product_entity, customer_entity],
        domains=[billing_domain, inventory_domain],
        relationships=[
            RelationshipSchema(
                name="order_customer",
                source_entity="Order",
                target_entity="Customer",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.MANY_TO_ONE,
                source_field="customer_id",
                target_field="id",
            ),
        ],
        description="Test project for codegen",
    )
