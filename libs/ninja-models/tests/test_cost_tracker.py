"""Tests for ninja_models.cost_tracker."""

from ninja_models.cost_tracker import CostTracker, UsageRecord


def _make_record(
    model: str = "gemini/gemini-2.5-pro",
    agent: str | None = "test-agent",
    prompt: int = 100,
    completion: int = 50,
    cost: float = 0.001,
) -> UsageRecord:
    return UsageRecord(
        model=model,
        agent_name=agent,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        cost=cost,
    )


class TestUsageRecord:
    def test_immutable(self):
        r = _make_record()
        assert r.model == "gemini/gemini-2.5-pro"
        assert r.total_tokens == 150


class TestCostTracker:
    def test_empty(self):
        tracker = CostTracker()
        assert tracker.total_cost() == 0.0
        assert tracker.total_tokens() == 0
        assert tracker.records == []

    def test_record_and_totals(self):
        tracker = CostTracker()
        tracker.record(_make_record(cost=0.01))
        tracker.record(_make_record(cost=0.02))
        assert tracker.total_cost() == 0.03
        assert tracker.total_tokens() == 300
        assert len(tracker.records) == 2

    def test_summary_by_agent(self):
        tracker = CostTracker()
        tracker.record(_make_record(agent="a", cost=0.01, prompt=100, completion=50))
        tracker.record(_make_record(agent="a", cost=0.02, prompt=200, completion=100))
        tracker.record(_make_record(agent="b", cost=0.05, prompt=500, completion=250))

        summary = tracker.summary_by_agent()
        assert len(summary) == 2

        a = summary["a"]
        assert a.calls == 2
        assert a.prompt_tokens == 300
        assert a.completion_tokens == 150
        assert a.total_tokens == 450
        assert abs(a.cost - 0.03) < 1e-9

        b = summary["b"]
        assert b.calls == 1
        assert b.total_tokens == 750

    def test_reset(self):
        tracker = CostTracker()
        tracker.record(_make_record())
        tracker.reset()
        assert tracker.total_cost() == 0.0
        assert tracker.records == []

    def test_records_returns_copy(self):
        tracker = CostTracker()
        tracker.record(_make_record())
        records = tracker.records
        records.clear()
        assert len(tracker.records) == 1
