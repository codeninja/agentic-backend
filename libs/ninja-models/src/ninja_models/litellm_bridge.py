"""ADK-to-LiteLLM adapter: unified completion interface with fallback support."""

from __future__ import annotations

import logging
import os
from typing import Any

import litellm

from ninja_models.config import ModelsConfig, ProviderConfig, load_models_config
from ninja_models.cost_tracker import CostTracker, UsageRecord
from ninja_models.resolver import ModelResolver

logger = logging.getLogger(__name__)


def _configure_provider_env(name: str, provider: ProviderConfig) -> None:
    """Push provider config into the environment where LiteLLM expects it."""
    if provider.api_key_env:
        api_key = os.getenv(provider.api_key_env)
        if api_key:
            env_var = f"{name.upper()}_API_KEY"
            os.environ[env_var] = api_key

    if provider.base_url and name.lower() == "ollama":
        os.environ["OLLAMA_API_BASE"] = provider.base_url


class LiteLLMBridge:
    """Wraps litellm.completion with Ninja Stack model resolution and cost tracking."""

    def __init__(
        self,
        config: ModelsConfig | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self._config = config or load_models_config()
        self._resolver = ModelResolver(self._config)
        self._cost_tracker = cost_tracker or CostTracker()

        # Push provider env vars once at init
        for name, provider in self._config.providers.items():
            _configure_provider_env(name, provider)

    @property
    def resolver(self) -> ModelResolver:
        return self._resolver

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    def completion(
        self,
        messages: list[dict[str, str]],
        *,
        agent_name: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> litellm.ModelResponse:
        """Run a chat completion through LiteLLM with automatic fallback.

        Args:
            messages: OpenAI-style message list.
            agent_name: Ninja Stack agent name for model resolution.
            model: Explicit model override (skips resolver).
            **kwargs: Passed through to litellm.completion.

        Returns:
            The LiteLLM ModelResponse.

        Raises:
            Exception: If all models in the chain fail.
        """
        if model:
            chain = [model]
        else:
            chain = self._resolver.resolve_chain(agent_name)

        last_error: Exception | None = None
        for candidate in chain:
            try:
                logger.info("Attempting completion with model=%s agent=%s", candidate, agent_name)
                response = litellm.completion(model=candidate, messages=messages, **kwargs)
                self._record_usage(response, candidate, agent_name)
                return response
            except Exception as exc:  # noqa: BLE001
                logger.warning("Model %s failed: %s", candidate, exc)
                last_error = exc

        raise last_error  # type: ignore[misc]

    async def acompletion(
        self,
        messages: list[dict[str, str]],
        *,
        agent_name: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> litellm.ModelResponse:
        """Async version of completion with automatic fallback."""
        if model:
            chain = [model]
        else:
            chain = self._resolver.resolve_chain(agent_name)

        last_error: Exception | None = None
        for candidate in chain:
            try:
                logger.info("Attempting async completion with model=%s agent=%s", candidate, agent_name)
                response = await litellm.acompletion(model=candidate, messages=messages, **kwargs)
                self._record_usage(response, candidate, agent_name)
                return response
            except Exception as exc:  # noqa: BLE001
                logger.warning("Model %s failed: %s", candidate, exc)
                last_error = exc

        raise last_error  # type: ignore[misc]

    def _record_usage(
        self,
        response: litellm.ModelResponse,
        model: str,
        agent_name: str | None,
    ) -> None:
        """Extract token usage from a response and record it."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return

        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)

        # Attempt cost calculation via litellm
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:  # noqa: BLE001
            cost = 0.0

        self._cost_tracker.record(
            UsageRecord(
                model=model,
                agent_name=agent_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=cost,
            )
        )
