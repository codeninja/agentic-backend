"""Tests for tracing / observability."""

import time
from types import SimpleNamespace

from ninja_agents.tracing import AgentSpan, TraceContext, sanitize_summary


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

    def test_domain_field_propagated(self) -> None:
        """Spans tagged with a domain propagate it to tool call records."""
        span = AgentSpan(agent_name="agent", domain="Finance")
        record = span.record_tool_call(
            tool_name="get",
            input_summary="id=1",
            output_summary="ok",
            duration_ms=1.0,
        )
        assert record.domain == "Finance"
        assert span.domain == "Finance"

    def test_record_tool_call_sanitizes_summaries(self) -> None:
        """Tool call recording must sanitize input and output summaries."""
        span = AgentSpan(agent_name="agent")
        record = span.record_tool_call(
            tool_name="login",
            input_summary="password=super_secret_123",
            output_summary="token=abc123 user@example.com",
            duration_ms=1.0,
        )
        assert "super_secret_123" not in record.input_summary
        assert "user@example.com" not in record.output_summary


class TestSanitizeSummary:
    """Tests for the sanitize_summary helper."""

    def test_redacts_password(self) -> None:
        assert "my_pass" not in sanitize_summary("password=my_pass foo")

    def test_redacts_api_key(self) -> None:
        assert "sk-abc123" not in sanitize_summary("api_key=sk-abc123")

    def test_redacts_email(self) -> None:
        result = sanitize_summary("user john@example.com created")
        assert "john@example.com" not in result
        assert "***@***.***" in result

    def test_redacts_ssn(self) -> None:
        result = sanitize_summary("ssn: 123-45-6789")
        assert "123-45-6789" not in result
        assert "***-**-****" in result

    def test_redacts_credit_card(self) -> None:
        result = sanitize_summary("card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in result

    def test_redacts_bearer_token(self) -> None:
        result = sanitize_summary("Authorization: Bearer eyJhbGciOiJI...")
        assert "eyJhbGciOiJI" not in result

    def test_truncates_long_summaries(self) -> None:
        long_input = "x" * 300
        result = sanitize_summary(long_input)
        assert len(result) <= 204  # 200 + "..."

    def test_preserves_safe_content(self) -> None:
        safe = "order_id=abc status=active"
        assert sanitize_summary(safe) == safe

    def test_custom_max_length(self) -> None:
        result = sanitize_summary("a" * 50, max_length=10)
        assert len(result) <= 14  # 10 + "..."


class TestDomainTraceView:
    """Tests for domain-scoped trace isolation."""

    def test_domain_view_tags_spans(self) -> None:
        """Spans created via a domain view are tagged with the domain."""
        trace = TraceContext()
        view = trace.domain_view("Finance")
        span = view.start_span("agent_a")
        assert span.domain == "Finance"
        view.finish_span(span.span_id)
        assert trace.spans[0].domain == "Finance"

    def test_domain_view_shares_trace_id(self) -> None:
        """Domain views use the same trace_id as the parent context."""
        trace = TraceContext(trace_id="shared-id")
        view = trace.domain_view("HR")
        assert view.trace_id == "shared-id"

    def test_domain_view_to_dict_isolates_spans(self) -> None:
        """to_dict on a domain view only returns that domain's spans."""
        trace = TraceContext()
        finance_view = trace.domain_view("Finance")
        hr_view = trace.domain_view("HR")

        f_span = finance_view.start_span("finance_agent")
        f_span.record_tool_call(
            tool_name="get_salary",
            input_summary="emp_id=1",
            output_summary="salary=100000",
            duration_ms=5.0,
        )
        finance_view.finish_span(f_span.span_id)

        h_span = hr_view.start_span("hr_agent")
        h_span.record_tool_call(
            tool_name="get_employee",
            input_summary="emp_id=1",
            output_summary="name=John",
            duration_ms=3.0,
        )
        hr_view.finish_span(h_span.span_id)

        # Finance view should only see finance spans
        finance_dict = finance_view.to_dict()
        assert len(finance_dict["spans"]) == 1
        assert finance_dict["spans"][0]["agent_name"] == "finance_agent"
        assert finance_dict["spans"][0]["tool_calls"][0]["tool_name"] == "get_salary"

        # HR view should only see HR spans
        hr_dict = hr_view.to_dict()
        assert len(hr_dict["spans"]) == 1
        assert hr_dict["spans"][0]["agent_name"] == "hr_agent"

        # Parent trace sees everything
        full_dict = trace.to_dict()
        assert len(full_dict["spans"]) == 2

    def test_domain_view_token_isolation(self) -> None:
        """Token counts on domain views only reflect that domain's spans."""
        trace = TraceContext()
        v1 = trace.domain_view("A")
        v2 = trace.domain_view("B")

        s1 = v1.start_span("agent_a")
        s1.record_tokens(100, 50)
        v1.finish_span(s1.span_id)

        s2 = v2.start_span("agent_b")
        s2.record_tokens(200, 80)
        v2.finish_span(s2.span_id)

        assert v1.total_input_tokens == 100
        assert v1.total_output_tokens == 50
        assert v2.total_input_tokens == 200
        assert v2.total_output_tokens == 80
        # Parent has totals
        assert trace.total_input_tokens == 300
        assert trace.total_output_tokens == 130

    def test_domain_view_prevents_cross_domain_tool_leakage(self) -> None:
        """A domain view must NOT expose tool calls from other domains."""
        trace = TraceContext()
        billing_view = trace.domain_view("Billing")
        hr_view = trace.domain_view("HR")

        # Billing agent records a sensitive tool call
        b_span = billing_view.start_span("billing_agent")
        b_span.record_tool_call(
            tool_name="charge_card",
            input_summary="card=4111111111111111",
            output_summary="charged $500",
            duration_ms=10.0,
        )
        billing_view.finish_span(b_span.span_id)

        # HR view should see zero spans/tool calls
        hr_dict = hr_view.to_dict()
        assert len(hr_dict["spans"]) == 0
        # Verify no billing data in HR's serialized output
        hr_str = str(hr_dict)
        assert "charge_card" not in hr_str
        assert "charged" not in hr_str

    def test_domain_view_record_adk_event(self) -> None:
        """ADK events recorded via a domain view are tagged correctly."""
        trace = TraceContext()
        view = trace.domain_view("Sales")
        event = SimpleNamespace(
            author="sales_agent",
            usage_metadata=SimpleNamespace(
                prompt_token_count=30,
                candidates_token_count=15,
            ),
        )
        view.record_adk_event(event)
        assert view.total_input_tokens == 30
        assert view.total_output_tokens == 15
        # The auto-created span should be tagged with the domain
        assert trace.spans[-1].domain == "Sales"

    def test_to_dict_domain_filter(self) -> None:
        """TraceContext.to_dict(domain=...) filters correctly."""
        trace = TraceContext()
        s1 = trace.start_span("a1", domain="X")
        s1.record_tokens(10, 5)
        trace.finish_span(s1.span_id)

        s2 = trace.start_span("a2", domain="Y")
        s2.record_tokens(20, 10)
        trace.finish_span(s2.span_id)

        x_dict = trace.to_dict(domain="X")
        assert len(x_dict["spans"]) == 1
        assert x_dict["total_input_tokens"] == 10

        y_dict = trace.to_dict(domain="Y")
        assert len(y_dict["spans"]) == 1
        assert y_dict["total_input_tokens"] == 20

        all_dict = trace.to_dict()
        assert len(all_dict["spans"]) == 2
        assert all_dict["total_input_tokens"] == 30

    def test_domain_view_domain_property(self) -> None:
        """DomainTraceView exposes the domain it's scoped to."""
        trace = TraceContext()
        view = trace.domain_view("MyDomain")
        assert view.domain == "MyDomain"
