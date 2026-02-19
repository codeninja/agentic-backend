"""Shared fixtures for ninja-agents tests."""

import pytest
from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType


@pytest.fixture()
def order_entity() -> EntitySchema:
    return EntitySchema(
        name="Order",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="customer_id", field_type=FieldType.UUID),
            FieldSchema(name="total", field_type=FieldType.FLOAT),
            FieldSchema(name="status", field_type=FieldType.STRING),
        ],
    )


@pytest.fixture()
def product_entity() -> EntitySchema:
    return EntitySchema(
        name="Product",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="name", field_type=FieldType.STRING),
            FieldSchema(name="price", field_type=FieldType.FLOAT),
        ],
    )


@pytest.fixture()
def shipment_entity() -> EntitySchema:
    return EntitySchema(
        name="Shipment",
        storage_engine="sql",
        fields=[
            FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
            FieldSchema(name="order_id", field_type=FieldType.UUID),
            FieldSchema(name="carrier", field_type=FieldType.STRING),
        ],
    )


@pytest.fixture()
def billing_domain(order_entity: EntitySchema) -> DomainSchema:
    return DomainSchema(
        name="Billing",
        entities=["Order"],
        agent_config=AgentConfig(reasoning_level=ReasoningLevel.MEDIUM),
    )


@pytest.fixture()
def logistics_domain(shipment_entity: EntitySchema) -> DomainSchema:
    return DomainSchema(
        name="Logistics",
        entities=["Shipment"],
        agent_config=AgentConfig(reasoning_level=ReasoningLevel.MEDIUM),
    )
