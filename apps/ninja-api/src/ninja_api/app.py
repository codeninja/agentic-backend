"""FastAPI app factory — the thin composition shell for Ninja Stack.

Creates and configures the FastAPI application by wiring together:
- ``ninja-core`` for ASD loading
- ``ninja-gql`` for Strawberry GraphQL schema
- ``ninja-auth`` for authentication middleware
- ``ninja-agents`` for agent orchestration (via SSE chat endpoint)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ninja_auth.config import AuthConfig
from ninja_auth.gateway import AuthGateway
from ninja_gql.schema import build_schema
from strawberry.fastapi import GraphQLRouter

from ninja_api.chat import chat_endpoint
from ninja_api.startup import load_asd, make_agent_router, make_repo_getter

logger = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    """Read allowed CORS origins from ``NINJA_CORS_ORIGINS`` env var.

    Returns a list of origin strings.  Defaults to ``["*"]`` in dev
    (when ``NINJA_CORS_ORIGINS`` is not set).
    """
    raw = os.environ.get("NINJA_CORS_ORIGINS", "")
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(schema_path: Path | None = None) -> FastAPI:
    """Create and configure the Ninja Stack FastAPI application.

    This is the main entry point.  The app is a **composition shell** —
    it contains zero business logic, only wiring.

    Args:
        schema_path: Override the ASD file path.  Defaults to
            ``.ninjastack/schema.json``.

    Returns:
        A fully configured ``FastAPI`` instance.
    """
    # --- Load ASD and wire services ---
    asd_path = schema_path or Path(".ninjastack/schema.json")
    logger.info("Loading ASD from %s", asd_path)
    asd = load_asd(asd_path)

    repo_getter = make_repo_getter(asd)
    agent_router = make_agent_router(asd)
    gql_schema = build_schema(asd, repo_getter=repo_getter, agent_router=agent_router)

    # --- Build FastAPI app ---
    app = FastAPI(
        title="Ninja Stack API",
        description="Schema-first agentic backend — auto-generated GraphQL + agent chat",
        version="0.1.0",
    )

    # Store references on app.state for endpoint access.
    app.state.asd = asd
    app.state.repo_getter = repo_getter
    app.state.agent_router = agent_router
    app.state.gql_schema = gql_schema

    # --- Auth middleware ---
    auth_config = AuthConfig.from_file()
    # Ensure /graphql playground is public.
    public_paths = set(auth_config.public_paths)
    public_paths.add("/graphql")
    auth_config = auth_config.model_copy(update={"public_paths": list(public_paths)})
    app.state.auth_config = auth_config
    app.add_middleware(AuthGateway, config=auth_config)

    # --- CORS middleware ---
    origins = _parse_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Health endpoint (no auth — covered by public_paths) ---
    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check — always returns ``{"status": "ok"}``."""
        return {"status": "ok"}

    # --- SSE chat endpoint ---
    app.post("/chat")(chat_endpoint)

    # --- Mount GraphQL router ---
    gql_router = GraphQLRouter(gql_schema)
    app.include_router(gql_router, prefix="/graphql")

    logger.info(
        "Ninja API ready — %d entities, %d domains",
        len(asd.entities),
        len(asd.domains),
    )

    return app
