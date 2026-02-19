"""Tests for ninja_models.litellm_bridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ninja_models.config import ModelsConfig
from ninja_models.cost_tracker import CostTracker
from ninja_models.litellm_bridge import LiteLLMBridge


def _mock_response(prompt_tokens: int = 10, completion_tokens: int = 20) -> MagicMock:
    """Create a fake LiteLLM ModelResponse."""
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    resp = MagicMock()
    resp.usage = usage
    return resp


class TestLiteLLMBridge:
    def _make_bridge(self, config: ModelsConfig | None = None) -> LiteLLMBridge:
        return LiteLLMBridge(config=config or ModelsConfig(), cost_tracker=CostTracker())

    @patch("ninja_models.litellm_bridge.litellm")
    def test_completion_uses_resolved_model(self, mock_litellm: MagicMock):
        mock_litellm.completion.return_value = _mock_response()
        mock_litellm.completion_cost.return_value = 0.001

        config = ModelsConfig(agents={"billing": "openai/gpt-4o"})
        bridge = self._make_bridge(config)

        messages = [{"role": "user", "content": "hello"}]
        bridge.completion(messages, agent_name="billing")

        mock_litellm.completion.assert_called_once_with(model="openai/gpt-4o", messages=messages)

    @patch("ninja_models.litellm_bridge.litellm")
    def test_completion_with_explicit_model(self, mock_litellm: MagicMock):
        mock_litellm.completion.return_value = _mock_response()
        mock_litellm.completion_cost.return_value = 0.0

        bridge = self._make_bridge()
        messages = [{"role": "user", "content": "hello"}]
        bridge.completion(messages, model="anthropic/claude-sonnet-4-20250514")

        mock_litellm.completion.assert_called_once_with(model="anthropic/claude-sonnet-4-20250514", messages=messages)

    @patch("ninja_models.litellm_bridge.litellm")
    def test_fallback_on_failure(self, mock_litellm: MagicMock):
        mock_litellm.completion.side_effect = [
            Exception("primary failed"),
            _mock_response(),
        ]
        mock_litellm.completion_cost.return_value = 0.0

        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            fallback="gemini/gemini-2.5-flash",
        )
        bridge = self._make_bridge(config)

        messages = [{"role": "user", "content": "hello"}]
        resp = bridge.completion(messages)

        assert resp is not None
        assert mock_litellm.completion.call_count == 2
        calls = mock_litellm.completion.call_args_list
        assert calls[0].kwargs["model"] == "gemini/gemini-2.5-pro"
        assert calls[1].kwargs["model"] == "gemini/gemini-2.5-flash"

    @patch("ninja_models.litellm_bridge.litellm")
    def test_all_models_fail_raises(self, mock_litellm: MagicMock):
        mock_litellm.completion.side_effect = Exception("all failed")

        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            fallback="gemini/gemini-2.5-flash",
        )
        bridge = self._make_bridge(config)

        with pytest.raises(Exception, match="all failed"):
            bridge.completion([{"role": "user", "content": "hello"}])

    @patch("ninja_models.litellm_bridge.litellm")
    def test_records_usage(self, mock_litellm: MagicMock):
        mock_litellm.completion.return_value = _mock_response(prompt_tokens=100, completion_tokens=50)
        mock_litellm.completion_cost.return_value = 0.005

        bridge = self._make_bridge()
        bridge.completion([{"role": "user", "content": "hello"}], agent_name="test")

        assert bridge.cost_tracker.total_tokens() == 150
        assert bridge.cost_tracker.total_cost() == 0.005
        assert len(bridge.cost_tracker.records) == 1

        record = bridge.cost_tracker.records[0]
        assert record.agent_name == "test"
        assert record.model == "gemini/gemini-2.5-pro"

    @patch("ninja_models.litellm_bridge.litellm")
    def test_cost_calculation_failure_defaults_to_zero(self, mock_litellm: MagicMock):
        mock_litellm.completion.return_value = _mock_response()
        mock_litellm.completion_cost.side_effect = Exception("unknown model")

        bridge = self._make_bridge()
        bridge.completion([{"role": "user", "content": "hello"}])

        assert bridge.cost_tracker.total_cost() == 0.0

    @pytest.mark.asyncio
    @patch("ninja_models.litellm_bridge.litellm")
    async def test_acompletion(self, mock_litellm: MagicMock):
        mock_litellm.acompletion = AsyncMock(return_value=_mock_response())
        mock_litellm.completion_cost.return_value = 0.001

        bridge = self._make_bridge()
        messages = [{"role": "user", "content": "hello"}]
        resp = await bridge.acompletion(messages, agent_name="test")

        assert resp is not None
        mock_litellm.acompletion.assert_called_once()

    @pytest.mark.asyncio
    @patch("ninja_models.litellm_bridge.litellm")
    async def test_acompletion_fallback(self, mock_litellm: MagicMock):
        mock_litellm.acompletion = AsyncMock(side_effect=[Exception("primary failed"), _mock_response()])
        mock_litellm.completion_cost.return_value = 0.0

        config = ModelsConfig(
            default="gemini/gemini-2.5-pro",
            fallback="gemini/gemini-2.5-flash",
        )
        bridge = self._make_bridge(config)

        resp = await bridge.acompletion([{"role": "user", "content": "hello"}])
        assert resp is not None
        assert mock_litellm.acompletion.call_count == 2
