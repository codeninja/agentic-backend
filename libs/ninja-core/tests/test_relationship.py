"""Tests for RelationshipSchema, DomainSchema, AgentConfig, and AgenticSchema."""

import pytest
from ninja_core.schema import (
    AgentConfig,
    AgenticSchema,
    Cardinality,
    DomainSchema,
    EntitySchema,
    FieldSchema,
    FieldType,
    ReasoningLevel,
    RelationshipSchema,
    RelationshipType,
    StorageEngine,
)
from pydantic import ValidationError


def _simple_entity(name: str) -> EntitySchema:
    return EntitySchema(
        name=name,
        storage_engine=StorageEngine.SQL,
        fields=[FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True)],
    )


class TestRelationshipSchema:
    def test_hard_relationship(self):
        r = RelationshipSchema(
            name="user_orders",
            source_entity="User",
            target_entity="Order",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
            source_field="id",
            target_field="user_id",
        )
        assert r.relationship_type == RelationshipType.HARD
        assert r.cardinality == Cardinality.ONE_TO_MANY

    def test_soft_relationship(self):
        r = RelationshipSchema(
            name="similar_products",
            source_entity="Product",
            target_entity="Product",
            relationship_type=RelationshipType.SOFT,
            cardinality=Cardinality.MANY_TO_MANY,
        )
        assert r.source_field is None
        assert r.target_field is None

    def test_graph_relationship(self):
        r = RelationshipSchema(
            name="knows",
            source_entity="Person",
            target_entity="Person",
            relationship_type=RelationshipType.GRAPH,
            cardinality=Cardinality.MANY_TO_MANY,
            edge_label="KNOWS",
        )
        assert r.edge_label == "KNOWS"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            RelationshipSchema(
                name="",
                source_entity="A",
                target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_ONE,
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            RelationshipSchema(
                name="r",
                source_entity="A",
                target_entity="B",
                relationship_type=RelationshipType.HARD,
                cardinality=Cardinality.ONE_TO_ONE,
                weight=0.5,
            )


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert cfg.model_provider == "gemini"
        assert cfg.reasoning_level == ReasoningLevel.MEDIUM
        assert cfg.temperature == 0.7
        assert cfg.tool_permissions == []

    def test_custom_config(self):
        cfg = AgentConfig(
            model_provider="openai",
            model_name="gpt-4o",
            reasoning_level=ReasoningLevel.HIGH,
            tool_permissions=["search", "code_exec"],
            temperature=0.2,
            max_tokens=4096,
        )
        assert cfg.model_name == "gpt-4o"
        assert cfg.max_tokens == 4096

    def test_temperature_bounds(self):
        with pytest.raises(ValidationError):
            AgentConfig(temperature=3.0)

    def test_max_tokens_must_be_positive(self):
        with pytest.raises(ValidationError):
            AgentConfig(max_tokens=0)


class TestDomainSchema:
    def test_basic_domain(self):
        d = DomainSchema(name="Inventory", entities=["Product", "Warehouse"])
        assert d.name == "Inventory"
        assert len(d.entities) == 2
        assert d.agent_config.model_provider == "gemini"

    def test_domain_with_custom_agent(self):
        d = DomainSchema(
            name="Support",
            entities=["Ticket"],
            agent_config=AgentConfig(reasoning_level=ReasoningLevel.HIGH),
        )
        assert d.agent_config.reasoning_level == ReasoningLevel.HIGH

    def test_domain_requires_entities(self):
        with pytest.raises(ValidationError):
            DomainSchema(name="Empty", entities=[])


class TestAgenticSchema:
    def test_minimal_project(self):
        s = AgenticSchema(project_name="my-app")
        assert s.version == "1.0"
        assert s.entities == []
        assert s.relationships == []
        assert s.domains == []

    def test_full_project(self):
        user = _simple_entity("User")
        order = _simple_entity("Order")
        rel = RelationshipSchema(
            name="user_orders",
            source_entity="User",
            target_entity="Order",
            relationship_type=RelationshipType.HARD,
            cardinality=Cardinality.ONE_TO_MANY,
        )
        domain = DomainSchema(name="Commerce", entities=["User", "Order"])

        s = AgenticSchema(
            project_name="shop",
            entities=[user, order],
            relationships=[rel],
            domains=[domain],
            description="E-commerce backend",
        )
        assert len(s.entities) == 2
        assert len(s.relationships) == 1
        assert s.domains[0].name == "Commerce"

    def test_project_name_required(self):
        with pytest.raises(ValidationError):
            AgenticSchema(project_name="")
