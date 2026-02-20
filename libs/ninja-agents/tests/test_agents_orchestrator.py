"""Tests for parallel fan-out orchestration."""

import pytest
from google.adk.agents import ParallelAgent
from ninja_agents.base import CoordinatorAgent, DataAgent, DomainAgent
from ninja_agents.orchestrator import Orchestrator
from ninja_agents.tracing import TraceContext
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema


class TestOrchestrator:
    def _build_orchestrator(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> Orchestrator:
        da_order = DataAgent(entity=order_entity)
        da_ship = DataAgent(entity=shipment_entity)
        billing = DomainAgent(billing_domain, data_agents=[da_order])
        logistics = DomainAgent(logistics_domain, data_agents=[da_ship])
        coordinator = CoordinatorAgent(domain_agents=[billing, logistics])
        return Orchestrator(coordinator)

    def test_build_parallel_agent(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        parallel = orch.build_parallel_agent()
        assert isinstance(parallel, ParallelAgent)
        assert len(parallel.sub_agents) == 2

    @pytest.mark.asyncio
    async def test_fan_out_parallel(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        results = await orch.fan_out("get status", target_domains=["Billing", "Logistics"])
        assert "Billing" in results
        assert "Logistics" in results
        assert results["Billing"]["domain"] == "Billing"
        assert results["Logistics"]["domain"] == "Logistics"

    @pytest.mark.asyncio
    async def test_fan_out_all_domains(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        results = await orch.fan_out("overview")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_fan_out_with_tracing(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        trace = TraceContext()
        await orch.fan_out("status", target_domains=["Billing", "Logistics"], trace=trace)
        # Coordinator span + 2 domain agent spans
        assert len(trace.spans) >= 3
        agent_names = [s.agent_name for s in trace.spans]
        assert "coordinator" in agent_names

    def test_fan_out_sync(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        results = orch.fan_out_sync("get status", target_domains=["Billing"])
        assert "Billing" in results
