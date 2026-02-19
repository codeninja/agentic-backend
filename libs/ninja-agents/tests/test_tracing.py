"""Tests for tracing / observability."""

import time

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
        assert span.end_time is None
        trace.finish_span("test_agent")
        assert span.end_time is not None
        assert span.duration_ms >= 0

    def test_multiple_spans(self) -> None:
        trace = TraceContext()
        trace.start_span("agent_a")
        trace.start_span("agent_b")
        trace.finish_span("agent_a")
        trace.finish_span("agent_b")
        assert len(trace.spans) == 2

    def test_total_tokens(self) -> None:
        trace = TraceContext()
        span = trace.start_span("agent")
        span.record_tokens(100, 50)
        span.record_tokens(200, 100)
        trace.finish_span("agent")
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
        trace.finish_span("agent")

        d = trace.to_dict()
        assert d["trace_id"] == "test-trace"
        assert d["total_input_tokens"] == 10
        assert d["total_output_tokens"] == 20
        assert len(d["spans"]) == 1
        assert len(d["spans"][0]["tool_calls"]) == 1
        assert d["spans"][0]["tool_calls"][0]["tool_name"] == "order_get"
        assert d["spans"][0]["tool_calls"][0]["success"] is True


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
