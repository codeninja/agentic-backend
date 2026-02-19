"""Project-level configuration model for Ninja Stack."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectionProfile(BaseModel):
    """A single database connection profile."""

    name: str = Field(min_length=1, description="Profile name (e.g. 'primary-sql').")
    engine: str = Field(min_length=1, description="Engine type: postgres, mysql, mongodb, neo4j, chroma, milvus.")
    url: str = Field(min_length=1, description="Connection string / DSN.")
    default: bool = Field(default=False, description="Whether this is the default connection.")

    model_config = {"extra": "forbid"}


class ModelProvider(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="gemini", description="Provider name (gemini, openai, anthropic, ollama).")
    model: str = Field(default="gemini-2.0-flash", description="Default model identifier.")
    api_key_env: str = Field(default="GOOGLE_API_KEY", description="Env var holding the API key.")

    model_config = {"extra": "forbid"}


class AuthConfig(BaseModel):
    """Auth strategy configuration."""

    strategy: str = Field(default="none", description="Auth strategy: none, jwt, oauth2, apikey.")
    issuer: str | None = Field(default=None, description="Token issuer URL.")
    audience: str | None = Field(default=None, description="Token audience.")

    model_config = {"extra": "forbid"}


class NinjaStackConfig(BaseModel):
    """Top-level Ninja Stack project configuration.

    Aggregates all .ninjastack/ config files into a single model.
    """

    project_name: str = Field(default="my-ninja-project", min_length=1, description="Project name.")
    connections: list[ConnectionProfile] = Field(default_factory=list, description="Database connection profiles.")
    models: ModelProvider = Field(default_factory=ModelProvider, description="LLM provider configuration.")
    auth: AuthConfig = Field(default_factory=AuthConfig, description="Auth strategy configuration.")

    model_config = {"extra": "forbid"}
