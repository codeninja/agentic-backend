"""Parallel delegation logic — Coordinator fans out to DomainAgents concurrently."""

from __future__ import annotations

import asyncio
from typing import Any

from ninja_agents.base import CoordinatorAgent
from ninja_agents.tracing import TraceContext


async def _execute_domain(
    coordinator: CoordinatorAgent,
    domain_name: str,
    request: str,
    trace: TraceContext | None,
) -> tuple[str, dict[str, Any]]:
    """Execute a single domain agent (runs in executor for sync agents)."""
    da = coordinator.get_domain_agent(domain_name)
    if da is None:
        return domain_name, {"error": f"Unknown domain: {domain_name}"}
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, da.execute, request, trace)
    return domain_name, result


class Orchestrator:
    """Orchestrates parallel fan-out from a CoordinatorAgent to multiple DomainAgents."""

    def __init__(self, coordinator: CoordinatorAgent) -> None:
        self.coordinator = coordinator

    async def fan_out(
        self,
        request: str,
        target_domains: list[str] | None = None,
        trace: TraceContext | None = None,
    ) -> dict[str, Any]:
        """Fan out request to multiple domains concurrently, collect results.

        Args:
            request: The user request to process.
            target_domains: Domains to route to. Defaults to all domains.
            trace: Optional trace context for observability.

        Returns:
            Dict mapping domain name to its result.
        """
        domains = target_domains or self.coordinator.domain_names
        if trace:
            trace.start_span(self.coordinator.name)
        try:
            tasks = [_execute_domain(self.coordinator, d, request, trace) for d in domains]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            results: dict[str, Any] = {}
            for item in results_list:
                if isinstance(item, Exception):
                    results["_error"] = str(item)
                else:
                    domain_name, result = item
                    results[domain_name] = result
            return results
        finally:
            if trace:
                trace.finish_span(self.coordinator.name)

    def fan_out_sync(
        self,
        request: str,
        target_domains: list[str] | None = None,
        trace: TraceContext | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper around fan_out for non-async contexts."""
        return asyncio.run(self.fan_out(request, target_domains, trace))
