"""Observability — trace context with structured logging, timing, and cost attribution.

Integrates with ADK events: call ``TraceContext.record_adk_event()`` to
capture token usage from ``Event.usage_metadata`` emitted by the ADK runtime.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""

    tool_name: str
    agent_name: str
    input_summary: str
    output_summary: str
    duration_ms: float
    success: bool
    error: str | None = None


@dataclass
class AgentSpan:
    """Timing and cost span for a single agent invocation."""

    agent_name: str
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.monotonic() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def finish(self) -> None:
        self.end_time = time.monotonic()

    def record_tool_call(
        self,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        duration_ms: float,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> ToolCallRecord:
        record = ToolCallRecord(
            tool_name=tool_name,
            agent_name=self.agent_name,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self.tool_calls.append(record)
        return record

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


class TraceContext:
    """Trace context that flows through all agent hops in a request."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex
        self.spans: list[AgentSpan] = []
        self._active_spans: dict[str, AgentSpan] = {}

    def start_span(self, agent_name: str) -> AgentSpan:
        span = AgentSpan(agent_name=agent_name)
        self.spans.append(span)
        self._active_spans[agent_name] = span
        logger.debug("trace=%s agent=%s started", self.trace_id, agent_name)
        return span

    def finish_span(self, agent_name: str) -> AgentSpan | None:
        span = self._active_spans.pop(agent_name, None)
        if span is not None:
            span.finish()
            logger.debug(
                "trace=%s agent=%s finished duration_ms=%.1f",
                self.trace_id,
                agent_name,
                span.duration_ms,
            )
        return span

    @property
    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.spans)

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.spans)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.spans)

    def record_adk_event(self, event: Any) -> None:
        """Extract token counts from an ADK ``Event`` and attribute them.

        If the event has ``usage_metadata`` with ``prompt_token_count`` /
        ``candidates_token_count``, the tokens are recorded on the active
        span for ``event.author`` (if one exists).
        """
        author: str | None = getattr(event, "author", None)
        usage = getattr(event, "usage_metadata", None)
        if author and usage:
            span = self._active_spans.get(author)
            if span is None:
                span = self.start_span(author)
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            if input_tokens or output_tokens:
                span.record_tokens(input_tokens, output_tokens)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "total_duration_ms": self.total_duration_ms,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "spans": [
                {
                    "agent_name": s.agent_name,
                    "duration_ms": s.duration_ms,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "tool_calls": [
                        {
                            "tool_name": tc.tool_name,
                            "agent_name": tc.agent_name,
                            "input_summary": tc.input_summary,
                            "output_summary": tc.output_summary,
                            "duration_ms": tc.duration_ms,
                            "success": tc.success,
                            "error": tc.error,
                        }
                        for tc in s.tool_calls
                    ],
                }
                for s in self.spans
            ],
        }
