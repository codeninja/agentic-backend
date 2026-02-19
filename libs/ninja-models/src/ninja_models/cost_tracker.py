"""Token usage and cost logging per agent invocation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageRecord:
    """A single completion's token usage and cost."""

    model: str
    agent_name: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float = 0.0


class CostTracker:
    """Accumulates usage records and provides summary statistics."""

    def __init__(self) -> None:
        self._records: list[UsageRecord] = []

    @property
    def records(self) -> list[UsageRecord]:
        return list(self._records)

    def record(self, usage: UsageRecord) -> None:
        """Append a usage record and log it."""
        self._records.append(usage)
        logger.info(
            "Usage: model=%s agent=%s tokens=%d cost=$%.6f",
            usage.model,
            usage.agent_name,
            usage.total_tokens,
            usage.cost,
        )

    def total_cost(self) -> float:
        """Sum of all recorded costs."""
        return sum(r.cost for r in self._records)

    def total_tokens(self) -> int:
        """Sum of all recorded tokens."""
        return sum(r.total_tokens for r in self._records)

    def summary_by_agent(self) -> dict[str | None, AgentSummary]:
        """Aggregate usage per agent name."""
        agg: dict[str | None, _Agg] = {}
        for r in self._records:
            if r.agent_name not in agg:
                agg[r.agent_name] = _Agg()
            a = agg[r.agent_name]
            a.prompt_tokens += r.prompt_tokens
            a.completion_tokens += r.completion_tokens
            a.total_tokens += r.total_tokens
            a.cost += r.cost
            a.calls += 1

        return {
            name: AgentSummary(
                agent_name=name,
                calls=a.calls,
                prompt_tokens=a.prompt_tokens,
                completion_tokens=a.completion_tokens,
                total_tokens=a.total_tokens,
                cost=a.cost,
            )
            for name, a in agg.items()
        }

    def reset(self) -> None:
        """Clear all recorded usage."""
        self._records.clear()


@dataclass
class _Agg:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    calls: int = 0


@dataclass(frozen=True)
class AgentSummary:
    """Aggregated usage statistics for a single agent."""

    agent_name: str | None
    calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float = field(default=0.0)
