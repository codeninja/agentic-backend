"""Observability — trace context with structured logging, timing, and cost attribution.

Integrates with ADK events: call ``TraceContext.record_adk_event()`` to
capture token usage from ``Event.usage_metadata`` emitted by the ADK runtime.

Domain isolation: use ``TraceContext.domain_view(domain)`` to obtain a
``DomainTraceView`` that only exposes spans belonging to one domain.
This prevents cross-domain data leakage when the orchestrator fans out
to multiple domain agents concurrently.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Summary sanitization — strip PII / credentials from tool I/O summaries
# ---------------------------------------------------------------------------

_SUMMARY_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Bearer tokens (must come before generic credential pattern)
    (re.compile(r"(?i)Bearer\s+\S+"), "Bearer ***"),
    # Credentials and secrets
    (re.compile(r"(?i)(password|secret|token|api[_-]?key|credential|authorization)\s*[=:]\s*\S+"), r"\1=***"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "***@***.***"),
    # SSN-like patterns (xxx-xx-xxxx)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "***-**-****"),
    # Credit card-like patterns (4 groups of 4 digits)
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "****-****-****-****"),
]

# Maximum length for sanitized summaries.
_MAX_SUMMARY_LENGTH = 200


def sanitize_summary(raw: str, max_length: int = _MAX_SUMMARY_LENGTH) -> str:
    """Sanitize a tool input or output summary for safe storage in trace data.

    Redacts credentials, PII patterns (emails, SSNs, credit cards), and
    bearer tokens.  Truncates the result to ``max_length`` characters.

    Args:
        raw: The raw summary string.
        max_length: Maximum allowed length after sanitization.

    Returns:
        A sanitized, truncated summary string.
    """
    sanitized = raw
    for pattern, replacement in _SUMMARY_REDACT_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""

    tool_name: str
    agent_name: str
    input_summary: str
    output_summary: str
    duration_ms: float
    success: bool
    domain: str = ""
    error: str | None = None


@dataclass
class AgentSpan:
    """Timing and cost span for a single agent invocation."""

    agent_name: str
    domain: str = ""
    span_id: str = ""
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
        """Record a tool call, sanitizing input and output summaries."""
        record = ToolCallRecord(
            tool_name=tool_name,
            agent_name=self.agent_name,
            input_summary=sanitize_summary(input_summary),
            output_summary=sanitize_summary(output_summary),
            duration_ms=duration_ms,
            success=success,
            domain=self.domain,
            error=error,
        )
        self.tool_calls.append(record)
        return record

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


class TraceContext:
    """Trace context that flows through all agent hops in a request.

    Supports domain-scoped views via :meth:`domain_view` so that domain
    agents only see their own spans and tool calls, preventing cross-domain
    data leakage during parallel fan-out.
    """

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex
        self.spans: list[AgentSpan] = []
        self._active_spans: dict[str, AgentSpan] = {}
        self._span_counter: int = 0

    def _next_span_id(self, agent_name: str) -> str:
        self._span_counter += 1
        return f"{agent_name}#{self._span_counter}"

    def start_span(self, agent_name: str, *, domain: str = "") -> AgentSpan:
        """Start a new span, optionally tagged with a domain for isolation.

        Args:
            agent_name: Name of the agent owning this span.
            domain: Domain name to tag the span with (used for filtering).

        Returns:
            The newly created :class:`AgentSpan`.
        """
        span = AgentSpan(agent_name=agent_name, domain=domain)
        span_id = self._next_span_id(agent_name)
        span.span_id = span_id
        self.spans.append(span)
        self._active_spans[span_id] = span
        logger.debug("trace=%s span=%s domain=%s started", self.trace_id, span_id, domain or "(none)")
        return span

    def finish_span(self, span_id: str) -> AgentSpan | None:
        """Finish an active span."""
        span = self._active_spans.pop(span_id, None)
        if span is not None:
            span.finish()
            logger.debug(
                "trace=%s span=%s finished duration_ms=%.1f",
                self.trace_id,
                span_id,
                span.duration_ms,
            )
        return span

    def _spans_for_domain(self, domain: str | None) -> list[AgentSpan]:
        """Return spans filtered by domain, or all spans if domain is None."""
        if domain is None:
            return self.spans
        return [s for s in self.spans if s.domain == domain]

    @property
    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.spans)

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.spans)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.spans)

    def record_adk_event(self, event: Any, *, domain: str = "") -> None:
        """Extract token counts from an ADK ``Event`` and attribute them.

        If the event has ``usage_metadata`` with ``prompt_token_count`` /
        ``candidates_token_count``, the tokens are recorded on the active
        span for ``event.author`` (if one exists).

        Args:
            event: An ADK ``Event`` object.
            domain: Domain name to tag any auto-created span with.
        """
        author: str | None = getattr(event, "author", None)
        usage = getattr(event, "usage_metadata", None)
        if author and usage:
            # Find the most recent active span for this author.
            span: AgentSpan | None = None
            for s in reversed(list(self._active_spans.values())):
                if s.agent_name == author:
                    span = s
                    break
            if span is None:
                span = self.start_span(author, domain=domain)
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            if input_tokens or output_tokens:
                span.record_tokens(input_tokens, output_tokens)

    def domain_view(self, domain: str) -> DomainTraceView:
        """Create a domain-scoped view of this trace context.

        The returned :class:`DomainTraceView` automatically tags all new
        spans with the given domain and only exposes spans belonging to
        that domain via :meth:`to_dict`.

        Args:
            domain: The domain name to scope this view to.

        Returns:
            A :class:`DomainTraceView` bound to the specified domain.
        """
        return DomainTraceView(self, domain)

    def to_dict(self, *, domain: str | None = None) -> dict[str, Any]:
        """Serialize trace data, optionally filtered to a single domain.

        Args:
            domain: If provided, only include spans tagged with this domain.
                When ``None``, all spans are included (for the orchestrator).

        Returns:
            A dictionary containing trace metadata and span details.
        """
        spans = self._spans_for_domain(domain)
        return {
            "trace_id": self.trace_id,
            "total_duration_ms": sum(s.duration_ms for s in spans),
            "total_input_tokens": sum(s.input_tokens for s in spans),
            "total_output_tokens": sum(s.output_tokens for s in spans),
            "spans": [
                {
                    "agent_name": s.agent_name,
                    "domain": s.domain,
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
                for s in spans
            ],
        }


class DomainTraceView:
    """A domain-scoped proxy over a :class:`TraceContext`.

    Automatically tags all spans created through this view with the
    owning domain.  The :meth:`to_dict` method only returns spans
    belonging to this domain, preventing cross-domain data leakage.

    This object exposes the same public interface as ``TraceContext``
    for ``start_span`` / ``finish_span`` / ``to_dict``, so domain agents
    can use it as a drop-in replacement.
    """

    def __init__(self, parent: TraceContext, domain: str) -> None:
        self._parent = parent
        self._domain = domain

    @property
    def trace_id(self) -> str:
        """The trace ID from the parent context."""
        return self._parent.trace_id

    @property
    def domain(self) -> str:
        """The domain this view is scoped to."""
        return self._domain

    def start_span(self, agent_name: str, **kwargs: Any) -> AgentSpan:
        """Start a span tagged with this view's domain.

        Any ``domain`` keyword argument is overridden to ensure the span
        is correctly attributed.

        Args:
            agent_name: Name of the agent owning this span.
            **kwargs: Additional keyword arguments forwarded to the parent.

        Returns:
            The newly created :class:`AgentSpan`.
        """
        kwargs["domain"] = self._domain
        return self._parent.start_span(agent_name, **kwargs)

    def finish_span(self, span_id: str) -> AgentSpan | None:
        """Finish a span (delegated to the parent context).

        Args:
            span_id: The span ID to finish.

        Returns:
            The finished :class:`AgentSpan`, or ``None`` if not found.
        """
        return self._parent.finish_span(span_id)

    def record_adk_event(self, event: Any) -> None:
        """Record an ADK event, tagged with this view's domain.

        Args:
            event: An ADK ``Event`` object.
        """
        self._parent.record_adk_event(event, domain=self._domain)

    @property
    def total_duration_ms(self) -> float:
        """Total duration of spans in this domain only."""
        return sum(s.duration_ms for s in self._parent._spans_for_domain(self._domain))

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens for spans in this domain only."""
        return sum(s.input_tokens for s in self._parent._spans_for_domain(self._domain))

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens for spans in this domain only."""
        return sum(s.output_tokens for s in self._parent._spans_for_domain(self._domain))

    def to_dict(self) -> dict[str, Any]:
        """Serialize only this domain's trace data.

        Returns:
            A dictionary containing trace metadata and span details
            filtered to this domain.
        """
        return self._parent.to_dict(domain=self._domain)
