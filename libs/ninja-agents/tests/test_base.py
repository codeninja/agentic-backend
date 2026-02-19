"""Tests for base agent classes — scoping, delegation, determinism."""

import pytest
from ninja_agents.base import CoordinatorAgent, DataAgent, DomainAgent
from ninja_agents.tracing import TraceContext
from ninja_core.schema.agent import AgentConfig, ReasoningLevel
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema


class TestDataAgent:
    def test_default_no_llm(self, order_entity: EntitySchema) -> None:
        agent = DataAgent(order_entity)
        assert agent.uses_llm is False
        assert agent.config.reasoning_level == ReasoningLevel.NONE

    def test_tool_scoping_only_own_entity(self, order_entity: EntitySchema) -> None:
        agent = DataAgent(order_entity)
        names = agent.tool_names
        assert all("order" in n for n in names)
        assert agent.get_tool("shipment_get") is None

    def test_execute_valid_tool(self, order_entity: EntitySchema) -> None:
        agent = DataAgent(order_entity)
        result = agent.execute("order_get", id="abc-123")
        assert result["entity"] == "Order"
        assert result["operation"] == "get"

    def test_execute_invalid_tool_raises(self, order_entity: EntitySchema) -> None:
        agent = DataAgent(order_entity)
        with pytest.raises(KeyError, match="not in scope"):
            agent.execute("shipment_get")

    def test_execute_with_trace(self, order_entity: EntitySchema) -> None:
        agent = DataAgent(order_entity)
        trace = TraceContext()
        agent.execute("order_get", trace=trace, id="123")
        assert len(trace.spans) == 1
        assert trace.spans[0].agent_name == agent.name

    def test_explicit_llm_config(self, order_entity: EntitySchema) -> None:
        config = AgentConfig(reasoning_level=ReasoningLevel.LOW)
        agent = DataAgent(order_entity, config=config)
        assert agent.uses_llm is True


class TestDomainAgent:
    def test_delegates_to_data_agent(self, order_entity: EntitySchema, billing_domain: DomainSchema) -> None:
        da = DataAgent(order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        result = domain_agent.delegate("Order", "order_get", id="abc")
        assert result["entity"] == "Order"

    def test_cannot_access_other_domain_entity(
        self,
        order_entity: EntitySchema,
        billing_domain: DomainSchema,
    ) -> None:
        da = DataAgent(order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        with pytest.raises(KeyError, match="not in domain"):
            domain_agent.delegate("Shipment", "shipment_get")

    def test_uses_llm_by_default(self, order_entity: EntitySchema, billing_domain: DomainSchema) -> None:
        da = DataAgent(order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        assert domain_agent.uses_llm is True

    def test_execute_returns_structured_response(
        self, order_entity: EntitySchema, billing_domain: DomainSchema
    ) -> None:
        da = DataAgent(order_entity)
        domain_agent = DomainAgent(billing_domain, data_agents=[da])
        result = domain_agent.execute("get all orders")
        assert result["domain"] == "Billing"
        assert result["uses_llm"] is True


class TestCoordinatorAgent:
    def test_routes_to_domain(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        da_order = DataAgent(order_entity)
        da_ship = DataAgent(shipment_entity)
        billing = DomainAgent(billing_domain, data_agents=[da_order])
        logistics = DomainAgent(logistics_domain, data_agents=[da_ship])
        coordinator = CoordinatorAgent(domain_agents=[billing, logistics])
        results = coordinator.route("get order status", target_domains=["Billing"])
        assert "Billing" in results
        assert results["Billing"]["domain"] == "Billing"

    def test_unknown_domain_returns_error(
        self,
        order_entity: EntitySchema,
        billing_domain: DomainSchema,
    ) -> None:
        da = DataAgent(order_entity)
        billing = DomainAgent(billing_domain, data_agents=[da])
        coordinator = CoordinatorAgent(domain_agents=[billing])
        results = coordinator.route("query", target_domains=["NonExistent"])
        assert "error" in results["NonExistent"]

    def test_billing_cannot_access_logistics_tools(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        """A Billing agent cannot call Logistics tools (key acceptance criterion)."""
        da_order = DataAgent(order_entity)
        da_ship = DataAgent(shipment_entity)
        billing = DomainAgent(billing_domain, data_agents=[da_order])
        logistics = DomainAgent(logistics_domain, data_agents=[da_ship])

        # Billing agent has no access to Shipment
        with pytest.raises(KeyError):
            billing.delegate("Shipment", "shipment_get")

        # Billing's data agent has no shipment tools
        assert da_order.get_tool("shipment_get") is None

        # Logistics agent has no access to Order
        with pytest.raises(KeyError):
            logistics.delegate("Order", "order_get")
