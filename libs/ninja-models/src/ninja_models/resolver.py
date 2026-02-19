"""Resolve agent name to a model string with fallback chain support."""

from __future__ import annotations

import logging

from ninja_models.config import ModelsConfig, load_models_config

logger = logging.getLogger(__name__)


class ModelResolver:
    """Resolves an agent name to a concrete LiteLLM model string.

    Resolution order:
      1. Explicit agent mapping in config.agents
      2. config.default
      3. config.fallback (used at call-time when the primary fails)
    """

    def __init__(self, config: ModelsConfig | None = None) -> None:
        self._config = config or load_models_config()

    @property
    def config(self) -> ModelsConfig:
        return self._config

    def resolve(self, agent_name: str | None = None) -> str:
        """Return the primary model string for a given agent."""
        if agent_name and agent_name in self._config.agents:
            model = self._config.agents[agent_name]
            logger.debug("Resolved agent %r to model %r (agent mapping)", agent_name, model)
            return model

        logger.debug("Resolved agent %r to default model %r", agent_name, self._config.default)
        return self._config.default

    def fallback(self) -> str | None:
        """Return the fallback model, or None if not configured."""
        return self._config.fallback

    def resolve_chain(self, agent_name: str | None = None) -> list[str]:
        """Return the ordered list [primary, fallback] for a given agent.

        Duplicates are removed so callers can iterate without retrying the same model.
        """
        chain: list[str] = [self.resolve(agent_name)]
        fb = self.fallback()
        if fb and fb not in chain:
            chain.append(fb)
        return chain
