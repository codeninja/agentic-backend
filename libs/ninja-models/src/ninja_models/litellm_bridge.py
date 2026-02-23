"""ADK-to-LiteLLM adapter: unified completion interface with fallback support."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import litellm

from ninja_models.config import ModelsConfig, ProviderConfig, load_models_config
from ninja_models.cost_tracker import CostTracker, UsageRecord
from ninja_models.resolver import ModelResolver

logger = logging.getLogger(__name__)

# Only allow simple alphanumeric provider names to prevent abuse.
_PROVIDER_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _resolve_provider_credentials(
    name: str, provider: ProviderConfig
) -> dict[str, str]:
    """Resolve provider credentials from environment without writing them back.

    Args:
        name: Provider name (e.g. ``"openai"``, ``"anthropic"``).
        provider: Provider configuration containing ``api_key_env`` and ``base_url``.

    Returns:
        A dict with optional ``api_key`` and ``api_base`` entries suitable for
        passing directly to ``litellm.completion``.

    Raises:
        ValueError: If *name* contains characters outside ``[a-zA-Z0-9_-]``.
    """
    if not _PROVIDER_NAME_RE.match(name):
        raise ValueError(
            f"Invalid provider name {name!r}: must match [a-zA-Z0-9_-]+"
        )

    creds: dict[str, str] = {}

    if provider.api_key_env:
        api_key = os.getenv(provider.api_key_env)
        if api_key:
            creds["api_key"] = api_key

    if provider.base_url:
        creds["api_base"] = provider.base_url

    return creds


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

        # Resolve credentials once at init and keep them in memory — never in
        # os.environ.  Keyed by lower-cased provider name.
        self._provider_creds: dict[str, dict[str, str]] = {}
        for name, provider in self._config.providers.items():
            creds = _resolve_provider_credentials(name, provider)
            if creds:
                self._provider_creds[name.lower()] = creds

    @property
    def resolver(self) -> ModelResolver:
        """Return the model resolver."""
        return self._resolver

    @property
    def cost_tracker(self) -> CostTracker:
        """Return the cost tracker."""
        return self._cost_tracker

    def _creds_for_model(self, model: str) -> dict[str, str]:
        """Extract the provider prefix from a model string and return its credentials.

        LiteLLM model strings use a ``provider/model-name`` convention (e.g.
        ``"openai/gpt-4o"``).  If no ``/`` is present the full string is treated
        as the provider key.

        Returns:
            A (possibly empty) dict with ``api_key`` and/or ``api_base``.
        """
        provider = model.split("/", 1)[0].lower() if "/" in model else model.lower()
        return dict(self._provider_creds.get(provider, {}))

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
                call_kwargs = {**self._creds_for_model(candidate), **kwargs}
                response = litellm.completion(model=candidate, messages=messages, **call_kwargs)
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
        """Async version of completion with automatic fallback.

        Args:
            messages: OpenAI-style message list.
            agent_name: Ninja Stack agent name for model resolution.
            model: Explicit model override (skips resolver).
            **kwargs: Passed through to litellm.acompletion.

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
                logger.info("Attempting async completion with model=%s agent=%s", candidate, agent_name)
                call_kwargs = {**self._creds_for_model(candidate), **kwargs}
                response = await litellm.acompletion(model=candidate, messages=messages, **call_kwargs)
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
