"""Tests for parallel fan-out orchestration."""

import logging
from unittest.mock import patch

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
        # 2 domain results + 1 "errors" key
        assert len(results) == 3
        assert "Billing" in results
        assert "Logistics" in results

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

    @pytest.mark.asyncio
    async def test_fan_out_exception_returns_generic_error(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        """Domain agent exceptions must not leak internal details to callers."""
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        sensitive_msg = "psycopg2.OperationalError: connection to server at '10.0.0.5' refused"
        with patch(
            "ninja_agents.orchestrator._execute_domain",
            side_effect=RuntimeError(sensitive_msg),
        ):
            results = await orch.fan_out("get status", target_domains=["Billing"])

        # Generic error returned, not the sensitive exception message
        assert "Billing" in results
        assert results["Billing"]["error"] == "Request failed"
        assert results["Billing"]["error_code"] == "DOMAIN_ERROR"
        # Internal details must NOT appear anywhere in the result
        assert sensitive_msg not in str(results)

    @pytest.mark.asyncio
    async def test_fan_out_exception_logged_server_side(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Full exception details must be logged server-side for operators."""
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        sensitive_msg = "neo4j.exceptions.ServiceUnavailable: bolt://db:7687"
        with patch(
            "ninja_agents.orchestrator._execute_domain",
            side_effect=RuntimeError(sensitive_msg),
        ):
            with caplog.at_level(logging.ERROR, logger="ninja_agents.orchestrator"):
                await orch.fan_out("get status", target_domains=["Billing"])

        # Domain name must appear in the log for operator triage
        assert "Billing" in caplog.text
        # The full exception must be logged server-side
        assert sensitive_msg in caplog.text

    @pytest.mark.asyncio
    async def test_fan_out_partial_failure(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        """When one domain fails, others still return successful results."""
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)

        from ninja_agents.orchestrator import _execute_domain as real_execute_domain

        async def _mock_execute_domain(coordinator, domain_name, request, trace):
            if domain_name == "Billing":
                raise RuntimeError("internal DB error at /var/lib/postgres/data")
            return await real_execute_domain(coordinator, domain_name, request, trace)

        with patch(
            "ninja_agents.orchestrator._execute_domain",
            side_effect=_mock_execute_domain,
        ):
            results = await orch.fan_out("status", target_domains=["Billing", "Logistics"])

        # Billing should have generic error with domain context
        assert results["Billing"]["error"] == "Request failed"
        assert results["Billing"]["error_code"] == "DOMAIN_ERROR"
        assert results["Billing"]["domain"] == "Billing"
        # Logistics should succeed normally
        assert results["Logistics"]["domain"] == "Logistics"
        # errors dict should contain only Billing
        assert "Billing" in results["errors"]
        assert "Logistics" not in results["errors"]

    @pytest.mark.asyncio
    async def test_fan_out_all_domains_fail_preserves_every_error(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        """When ALL domains fail, every error must be preserved — no last-writer-wins."""
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)

        with patch(
            "ninja_agents.orchestrator._execute_domain",
            side_effect=RuntimeError("connection refused"),
        ):
            results = await orch.fan_out("status", target_domains=["Billing", "Logistics"])

        # Both domains must have their own error entry
        assert results["Billing"]["error"] == "Request failed"
        assert results["Billing"]["domain"] == "Billing"
        assert results["Logistics"]["error"] == "Request failed"
        assert results["Logistics"]["domain"] == "Logistics"
        # errors dict must contain BOTH failures
        assert len(results["errors"]) == 2
        assert "Billing" in results["errors"]
        assert "Logistics" in results["errors"]

    @pytest.mark.asyncio
    async def test_fan_out_errors_dict_empty_on_success(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        """When all domains succeed, the errors dict must be empty."""
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)
        results = await orch.fan_out("get status", target_domains=["Billing", "Logistics"])
        assert results["errors"] == {}
        assert results["Billing"]["domain"] == "Billing"
        assert results["Logistics"]["domain"] == "Logistics"

    @pytest.mark.asyncio
    async def test_fan_out_error_entries_are_self_describing(
        self,
        order_entity: EntitySchema,
        shipment_entity: EntitySchema,
        billing_domain: DomainSchema,
        logistics_domain: DomainSchema,
    ) -> None:
        """Each error entry must include the domain name so errors are distinguishable."""
        orch = self._build_orchestrator(order_entity, shipment_entity, billing_domain, logistics_domain)

        with patch(
            "ninja_agents.orchestrator._execute_domain",
            side_effect=RuntimeError("timeout"),
        ):
            results = await orch.fan_out("status", target_domains=["Billing", "Logistics"])

        for domain_name in ("Billing", "Logistics"):
            entry = results[domain_name]
            assert entry["domain"] == domain_name
            assert entry["error"] == "Request failed"
            assert entry["error_code"] == "DOMAIN_ERROR"
