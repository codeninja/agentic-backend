"""Tests for tracing / observability."""

import time
from types import SimpleNamespace

from ninja_agents.tracing import AgentSpan, TraceContext


class TestTraceContext:
    def test_trace_id_auto_generated(self) -> None:
        trace = TraceContext()
        assert trace.trace_id
        assert len(trace.trace_id) == 32  # hex UUID

    def test_custom_trace_id(self) -> None:
        trace = TraceContext(trace_id="custom-123")
        assert trace.trace_id == "custom-123"

    def test_start_and_finish_span(self) -> None:
        trace = TraceContext()
        span = trace.start_span("test_agent")
        assert span.agent_name == "test_agent"
        assert span.span_id  # unique key assigned
        assert span.end_time is None
        trace.finish_span(span.span_id)
        assert span.end_time is not None
        assert span.duration_ms >= 0

    def test_multiple_spans(self) -> None:
        trace = TraceContext()
        span_a = trace.start_span("agent_a")
        span_b = trace.start_span("agent_b")
        trace.finish_span(span_a.span_id)
        trace.finish_span(span_b.span_id)
        assert len(trace.spans) == 2

    def test_total_tokens(self) -> None:
        trace = TraceContext()
        span = trace.start_span("agent")
        span.record_tokens(100, 50)
        span.record_tokens(200, 100)
        trace.finish_span(span.span_id)
        assert trace.total_input_tokens == 300
        assert trace.total_output_tokens == 150

    def test_to_dict_structure(self) -> None:
        trace = TraceContext(trace_id="test-trace")
        span = trace.start_span("agent")
        span.record_tool_call(
            tool_name="order_get",
            input_summary="id=123",
            output_summary="found",
            duration_ms=5.0,
        )
        span.record_tokens(10, 20)
        trace.finish_span(span.span_id)

        d = trace.to_dict()
        assert d["trace_id"] == "test-trace"
        assert d["total_input_tokens"] == 10
        assert d["total_output_tokens"] == 20
        assert len(d["spans"]) == 1
        assert len(d["spans"][0]["tool_calls"]) == 1
        assert d["spans"][0]["tool_calls"][0]["tool_name"] == "order_get"
        assert d["spans"][0]["tool_calls"][0]["success"] is True

    def test_record_adk_event_captures_tokens(self) -> None:
        trace = TraceContext()
        span = trace.start_span("my_agent")
        # Simulate an ADK event with usage_metadata
        event = SimpleNamespace(
            author="my_agent",
            usage_metadata=SimpleNamespace(
                prompt_token_count=50,
                candidates_token_count=25,
            ),
        )
        trace.record_adk_event(event)
        trace.finish_span(span.span_id)
        assert trace.total_input_tokens == 50
        assert trace.total_output_tokens == 25

    def test_record_adk_event_no_metadata(self) -> None:
        trace = TraceContext()
        event = SimpleNamespace(author="agent", usage_metadata=None)
        trace.record_adk_event(event)
        assert trace.total_input_tokens == 0

    # -- Duplicate name collision tests ------------------------------------

    def test_duplicate_agent_names_do_not_collide(self) -> None:
        """Two agents with the same name get separate spans."""
        trace = TraceContext()
        span1 = trace.start_span("worker")
        span2 = trace.start_span("worker")

        # They must have different span IDs
        assert span1.span_id != span2.span_id
        # Both should be in the spans list
        assert len(trace.spans) == 2

        # Finishing one should not affect the other
        span1.record_tokens(100, 50)
        span2.record_tokens(200, 80)
        trace.finish_span(span1.span_id)

        # span2 should still be active (not finished)
        assert span2.end_time is None

        trace.finish_span(span2.span_id)
        assert span1.end_time is not None
        assert span2.end_time is not None

        # Token totals should reflect both spans
        assert trace.total_input_tokens == 300
        assert trace.total_output_tokens == 130

    def test_duplicate_names_in_to_dict(self) -> None:
        """Serialization preserves all spans even with duplicate names."""
        trace = TraceContext(trace_id="dup-test")
        span1 = trace.start_span("worker")
        span2 = trace.start_span("worker")
        span1.record_tokens(10, 5)
        span2.record_tokens(20, 10)
        trace.finish_span(span1.span_id)
        trace.finish_span(span2.span_id)

        d = trace.to_dict()
        assert len(d["spans"]) == 2
        assert d["spans"][0]["agent_name"] == "worker"
        assert d["spans"][1]["agent_name"] == "worker"
        assert d["total_input_tokens"] == 30
        assert d["total_output_tokens"] == 15

    def test_adk_event_attributes_to_most_recent_active_span(self) -> None:
        """ADK events go to the most recently started active span for that agent."""
        trace = TraceContext()
        span1 = trace.start_span("llm_agent")
        span2 = trace.start_span("llm_agent")

        event = SimpleNamespace(
            author="llm_agent",
            usage_metadata=SimpleNamespace(
                prompt_token_count=40,
                candidates_token_count=20,
            ),
        )
        trace.record_adk_event(event)

        # Tokens should go to the most recent active span (span2)
        assert span2.input_tokens == 40
        assert span2.output_tokens == 20
        assert span1.input_tokens == 0
        assert span1.output_tokens == 0

    def test_span_ids_are_unique_across_names(self) -> None:
        """Span IDs are globally unique, not just per agent name."""
        trace = TraceContext()
        ids = set()
        for name in ["a", "b", "a", "b", "c"]:
            span = trace.start_span(name)
            ids.add(span.span_id)
        assert len(ids) == 5


class TestAgentSpan:
    def test_duration_while_running(self) -> None:
        span = AgentSpan(agent_name="test")
        time.sleep(0.01)
        assert span.duration_ms > 0

    def test_tool_call_recording(self) -> None:
        span = AgentSpan(agent_name="test")
        record = span.record_tool_call(
            tool_name="create",
            input_summary="data={}",
            output_summary="ok",
            duration_ms=1.5,
            success=True,
        )
        assert record.tool_name == "create"
        assert record.success is True
        assert len(span.tool_calls) == 1

    def test_error_recording(self) -> None:
        span = AgentSpan(agent_name="test")
        span.record_tool_call(
            tool_name="fail",
            input_summary="bad",
            output_summary="",
            duration_ms=0.1,
            success=False,
            error="Something broke",
        )
        assert span.tool_calls[0].success is False
        assert span.tool_calls[0].error == "Something broke"
