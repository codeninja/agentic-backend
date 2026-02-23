"""Parallel delegation — Coordinator fans out to DomainAgents concurrently.

Uses ADK ``ParallelAgent`` for the fan-out topology while keeping a
synchronous convenience wrapper for non-async callers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent

from ninja_agents.base import CoordinatorAgent
from ninja_agents.safety import sanitize_error, validate_request_size
from ninja_agents.tracing import DomainTraceView, TraceContext

logger = logging.getLogger(__name__)


async def _execute_domain(
    coordinator: CoordinatorAgent,
    domain_name: str,
    request: str,
    trace: DomainTraceView | None,
) -> tuple[str, dict[str, Any]]:
    """Execute a single domain agent with a domain-scoped trace view.

    Each domain receives its own :class:`DomainTraceView` so that tool
    input/output recorded during execution is isolated from other domains.
    """
    da = coordinator.get_domain_agent(domain_name)
    if da is None:
        return domain_name, {"error": f"Unknown domain: {domain_name}"}
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, da.execute, request, trace)
    return domain_name, result


class Orchestrator:
    """Orchestrates parallel fan-out from a CoordinatorAgent to multiple DomainAgents.

    Provides ``build_parallel_agent()`` to construct an ADK ``ParallelAgent``
    for use within the ADK runtime, and ``fan_out()`` / ``fan_out_sync()``
    for direct programmatic parallel execution.
    """

    def __init__(self, coordinator: CoordinatorAgent) -> None:
        self.coordinator = coordinator

    def build_parallel_agent(self, target_domains: list[str] | None = None) -> ParallelAgent:
        """Build an ADK ParallelAgent for fan-out execution.

        Creates fresh ``LlmAgent`` instances (ADK enforces single-parent,
        so the coordinator's own sub_agents cannot be reused here).
        """
        domains = target_domains or self.coordinator.domain_names
        sub_agents: list[LlmAgent] = []
        for d in domains:
            da = self.coordinator.get_domain_agent(d)
            if da is not None:
                sub_agents.append(
                    LlmAgent(
                        name=f"{da.name}_parallel",
                        model=da.agent.model,
                        description=da.agent.description,
                        instruction=da.agent.instruction,
                        tools=[],
                        sub_agents=[],
                    )
                )
        return ParallelAgent(name="parallel_fan_out", sub_agents=sub_agents)

    async def fan_out(
        self,
        request: str,
        target_domains: list[str] | None = None,
        trace: TraceContext | None = None,
    ) -> dict[str, Any]:
        """Fan out request to multiple domains concurrently, collect results.

        Validates request size before fan-out. Error messages from failed
        domains are sanitized to prevent information disclosure.

        Args:
            request: The user request to process.
            target_domains: Domains to route to.  Defaults to all domains.
            trace: Optional trace context for observability.

        Returns:
            Dict mapping domain name to its result, plus an ``errors`` key
            containing a dict of all domain-level failures keyed by domain
            name.  Each error entry includes ``domain``, ``error``, and
            ``error_code`` so failures are self-describing.

        Raises:
            ValueError: If the request exceeds the size limit.
        """
        validate_request_size(request)
        domains = target_domains or self.coordinator.domain_names
        span = trace.start_span(self.coordinator.name) if trace else None
        try:
            # Create per-domain trace views so each domain only sees its own
            # tool I/O — prevents cross-domain data leakage.
            domain_views: dict[str, DomainTraceView | None] = {
                d: trace.domain_view(d) if trace else None for d in domains
            }
            tasks = [
                _execute_domain(self.coordinator, d, request, domain_views[d])
                for d in domains
            ]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            results: dict[str, Any] = {}
            errors: dict[str, dict[str, Any]] = {}
            for domain_name, item in zip(domains, results_list):
                if isinstance(item, Exception):
                    logger.error(
                        "Domain agent '%s' failed during fan_out",
                        domain_name,
                        exc_info=item,
                    )
                    entry = {
                        "domain": domain_name,
                        "error": "Request failed",
                        "error_code": "DOMAIN_ERROR",
                    }
                    results[domain_name] = entry
                    errors[domain_name] = entry
                else:
                    _, result = item
                    results[domain_name] = result
            results["errors"] = errors
            return results
        finally:
            if span:
                trace.finish_span(span.span_id)

    def fan_out_sync(
        self,
        request: str,
        target_domains: list[str] | None = None,
        trace: TraceContext | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper around fan_out for non-async contexts."""
        return asyncio.run(self.fan_out(request, target_domains, trace))
