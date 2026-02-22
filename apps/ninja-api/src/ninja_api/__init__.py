"""Ninja API — thin FastAPI composition shell.

Wires together libs (ninja-core, ninja-gql, ninja-persistence, ninja-auth,
ninja-agents) into a servable FastAPI application.  Zero business logic lives
here — only composition.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from ninja_auth import AuthConfig, AuthGateway
from ninja_core import AgenticSchema
from ninja_core.serialization import load_schema
from ninja_gql import build_schema
from ninja_persistence import AdapterRegistry, ConnectionManager, Repository
from pydantic import BaseModel
from strawberry.fastapi import GraphQLRouter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Payload for the ``POST /chat`` endpoint."""

    message: str
    target_domains: list[str] | None = None


# ---------------------------------------------------------------------------
# Adapter: bridge build_schema(repo_getter) ↔ AdapterRegistry.get_repository
# ---------------------------------------------------------------------------


def _make_repo_getter(asd: AgenticSchema, registry: AdapterRegistry) -> Callable[[str], Repository[Any]]:
    """Return a ``(entity_name: str) -> Repository`` closure.

    ``build_schema()`` expects a callable that maps an entity name string to a
    ``Repository`` instance, but ``AdapterRegistry.get_repository()`` takes an
    ``EntitySchema`` object.  This thin adapter bridges that gap.
    """
    entity_map = {e.name: e for e in asd.entities}

    def getter(entity_name: str) -> Repository[Any]:
        entity = entity_map.get(entity_name)
        if entity is None:
            raise ValueError(f"Unknown entity: {entity_name}")
        return registry.get_repository(entity)

    return getter


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of shared resources."""
    # --- Startup -----------------------------------------------------------
    try:
        asd = load_schema()
    except FileNotFoundError:
        logger.warning(".ninjastack/schema.json not found — starting with empty schema")
        asd = AgenticSchema(project_name="default", entities=[])

    conn_mgr = ConnectionManager.from_file()

    registry: AdapterRegistry | None = None
    schema = None

    if conn_mgr.profiles:
        registry = AdapterRegistry(conn_mgr)
        repo_getter = _make_repo_getter(asd, registry)
        schema = build_schema(asd, repo_getter=repo_getter)
    else:
        logger.info("No connection profiles found — starting without persistence")
        schema = build_schema(asd)

    # Expose on app.state so routes / middleware can access them
    app.state.asd = asd
    app.state.conn_mgr = conn_mgr
    app.state.registry = registry
    app.state.schema = schema

    # Mount GraphQL router now that the schema is ready
    graphql_router = GraphQLRouter(schema)
    app.include_router(graphql_router, prefix="/graphql")

    yield

    # --- Shutdown ----------------------------------------------------------
    await conn_mgr.close_all()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct the FastAPI application with all middleware and routes."""
    app = FastAPI(
        title="Ninja Stack API",
        description="Agentic backend — schema-driven GraphQL API",
        lifespan=lifespan,
    )

    # --- CORS --------------------------------------------------------------
    origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Auth Gateway ------------------------------------------------------
    auth_config = AuthConfig.from_file()
    # Ensure API-specific paths are always public
    api_public = {"/health", "/graphql", "/graphql/*", "/docs", "/openapi.json"}
    auth_config.public_paths = list(set(auth_config.public_paths) | api_public)
    app.add_middleware(AuthGateway, config=auth_config)

    # --- Routes ------------------------------------------------------------

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        """Lightweight health-check endpoint."""
        return {
            "status": "ok",
            "schema_loaded": getattr(request.app.state, "asd", None) is not None,
        }

    @app.post("/chat")
    async def chat(request: Request, payload: ChatRequest) -> dict[str, Any]:
        """Fan out a natural-language query to domain agents."""
        orchestrator = getattr(request.app.state, "orchestrator", None)
        if orchestrator is None:
            return {"error": "Agent orchestrator not initialized"}
        result = await orchestrator.fan_out(payload.message, target_domains=payload.target_domains)
        return result

    return app


def get_app() -> FastAPI:
    """Return the module-level app singleton (created on first call).

    Deferred so that import alone does not trigger config validation.
    ``uvicorn ninja_api:app`` still works because uvicorn resolves the
    attribute at runtime, which invokes ``__getattr__``.
    """
    global _app  # noqa: PLW0603
    if _app is None:
        _app = create_app()
    return _app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    """Module-level ``__getattr__`` so ``uvicorn ninja_api:app`` works."""
    if name == "app":
        return get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
