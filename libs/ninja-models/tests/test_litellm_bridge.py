"""Tests for ninja_models.litellm_bridge."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ninja_models.config import ModelsConfig, ProviderConfig
from ninja_models.cost_tracker import CostTracker
from ninja_models.litellm_bridge import (
    LiteLLMBridge,
    _resolve_provider_credentials,
)


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


class TestResolveProviderCredentials:
    """Tests for the _resolve_provider_credentials helper."""

    def test_resolves_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MY_SECRET_KEY", "sk-secret-123")
        provider = ProviderConfig(api_key_env="MY_SECRET_KEY")
        creds = _resolve_provider_credentials("openai", provider)
        assert creds == {"api_key": "sk-secret-123"}

    def test_resolves_base_url(self):
        provider = ProviderConfig(base_url="http://localhost:11434")
        creds = _resolve_provider_credentials("ollama", provider)
        assert creds == {"api_base": "http://localhost:11434"}

    def test_resolves_both_key_and_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ANTHRO_KEY", "sk-anthro")
        provider = ProviderConfig(api_key_env="ANTHRO_KEY", base_url="https://custom.api")
        creds = _resolve_provider_credentials("anthropic", provider)
        assert creds == {"api_key": "sk-anthro", "api_base": "https://custom.api"}

    def test_missing_env_var_returns_no_key(self):
        provider = ProviderConfig(api_key_env="NONEXISTENT_KEY_12345")
        creds = _resolve_provider_credentials("openai", provider)
        assert creds == {}

    def test_empty_provider_returns_empty(self):
        provider = ProviderConfig()
        creds = _resolve_provider_credentials("gemini", provider)
        assert creds == {}

    def test_invalid_provider_name_raises(self):
        provider = ProviderConfig()
        with pytest.raises(ValueError, match="Invalid provider name"):
            _resolve_provider_credentials("../../etc/passwd", provider)

    def test_invalid_provider_name_with_spaces_raises(self):
        provider = ProviderConfig()
        with pytest.raises(ValueError, match="Invalid provider name"):
            _resolve_provider_credentials("my provider", provider)

    def test_does_not_write_to_os_environ(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TEST_API_KEY_165", "secret-value")
        provider = ProviderConfig(api_key_env="TEST_API_KEY_165")
        _resolve_provider_credentials("testprovider", provider)
        # The key should NOT appear under the derived name in os.environ
        assert "TESTPROVIDER_API_KEY" not in os.environ


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
    def test_completion_passes_api_key_per_request(self, mock_litellm: MagicMock, monkeypatch: pytest.MonkeyPatch):
        """API keys are passed directly to litellm.completion, not via os.environ."""
        monkeypatch.setenv("OPENAI_SECRET_165", "sk-test-key")
        monkeypatch.delenv("MYPROVIDER165_API_KEY", raising=False)
        mock_litellm.completion.return_value = _mock_response()
        mock_litellm.completion_cost.return_value = 0.0

        config = ModelsConfig(
            default="myprovider165/gpt-4o",
            providers={"myprovider165": ProviderConfig(api_key_env="OPENAI_SECRET_165")},
        )
        bridge = self._make_bridge(config)

        messages = [{"role": "user", "content": "hello"}]
        bridge.completion(messages)

        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-key"
        # Must NOT have polluted os.environ with derived key name
        assert "MYPROVIDER165_API_KEY" not in os.environ

    @patch("ninja_models.litellm_bridge.litellm")
    def test_completion_passes_api_base_per_request(self, mock_litellm: MagicMock):
        """Base URL is passed directly to litellm.completion."""
        mock_litellm.completion.return_value = _mock_response()
        mock_litellm.completion_cost.return_value = 0.0

        config = ModelsConfig(
            default="ollama/llama3",
            providers={"ollama": ProviderConfig(base_url="http://localhost:11434")},
        )
        bridge = self._make_bridge(config)

        messages = [{"role": "user", "content": "hello"}]
        bridge.completion(messages)

        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["api_base"] == "http://localhost:11434"

    @patch("ninja_models.litellm_bridge.litellm")
    def test_caller_kwargs_override_provider_creds(self, mock_litellm: MagicMock, monkeypatch: pytest.MonkeyPatch):
        """Explicit kwargs from the caller take precedence over provider config."""
        monkeypatch.setenv("OPENAI_SECRET", "sk-provider-key")
        mock_litellm.completion.return_value = _mock_response()
        mock_litellm.completion_cost.return_value = 0.0

        config = ModelsConfig(
            default="openai/gpt-4o",
            providers={"openai": ProviderConfig(api_key_env="OPENAI_SECRET")},
        )
        bridge = self._make_bridge(config)

        messages = [{"role": "user", "content": "hello"}]
        bridge.completion(messages, api_key="sk-override-key")

        call_kwargs = mock_litellm.completion.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-override-key"

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
    async def test_acompletion_passes_api_key(self, mock_litellm: MagicMock, monkeypatch: pytest.MonkeyPatch):
        """Async path also passes credentials per-request."""
        monkeypatch.setenv("OPENAI_SECRET", "sk-async-key")
        mock_litellm.acompletion = AsyncMock(return_value=_mock_response())
        mock_litellm.completion_cost.return_value = 0.0

        config = ModelsConfig(
            default="openai/gpt-4o",
            providers={"openai": ProviderConfig(api_key_env="OPENAI_SECRET")},
        )
        bridge = self._make_bridge(config)

        await bridge.acompletion([{"role": "user", "content": "hello"}])

        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-async-key"

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

    def test_no_environ_pollution_on_init(self, monkeypatch: pytest.MonkeyPatch):
        """Creating a bridge must not write any new keys to os.environ."""
        monkeypatch.setenv("SECRET_KEY_165", "super-secret")
        env_before = set(os.environ.keys())

        config = ModelsConfig(
            providers={"openai": ProviderConfig(api_key_env="SECRET_KEY_165")},
        )
        LiteLLMBridge(config=config, cost_tracker=CostTracker())

        env_after = set(os.environ.keys())
        assert env_before == env_after, f"New env vars added: {env_after - env_before}"
