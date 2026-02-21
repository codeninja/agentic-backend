"""SSE chat endpoint — streams agent responses via Server-Sent Events.

Uses ``sse-starlette`` to stream domain results from the
``Orchestrator.fan_out()`` call as individual SSE events.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, Request
from ninja_auth.context import UserContext
from ninja_auth.gateway import get_user_context
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ninja_api.startup import AgentRouterAdapter

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """Request body for the ``POST /chat`` endpoint."""

    message: str = Field(min_length=1, description="The user's message or query.")
    domains: list[str] | None = Field(
        default=None,
        description="Optional list of domain names to target. When ``None``, all domains are queried.",
    )


async def _stream_results(
    results: dict[str, Any],
) -> AsyncGenerator[dict[str, str], None]:
    """Yield SSE events for each domain result.

    Each event has:
    - ``event``: the domain name
    - ``data``: JSON-serialized result dict
    """
    for domain_name, result in results.items():
        yield {
            "event": domain_name,
            "data": json.dumps(result, default=str),
        }
    # Final event to signal completion.
    yield {
        "event": "done",
        "data": json.dumps({"status": "complete"}),
    }


async def chat_endpoint(
    request: Request,
    body: ChatRequest,
    user: UserContext = Depends(get_user_context),
) -> EventSourceResponse:
    """Stream agent responses as Server-Sent Events.

    Accepts a chat message and optional domain filter, fans out through
    the orchestrator, and streams each domain's response as a separate
    SSE event.

    Args:
        request: The incoming HTTP request.
        body: The parsed chat request body.
        user: The authenticated user context (injected by auth middleware).

    Returns:
        An ``EventSourceResponse`` streaming domain results.
    """
    agent_router: AgentRouterAdapter = request.app.state.agent_router
    orchestrator = agent_router._orchestrator

    logger.info(
        "Chat request from user=%s message=%r domains=%s",
        user.user_id,
        body.message[:80],
        body.domains,
    )

    results = await orchestrator.fan_out(
        request=body.message,
        target_domains=body.domains,
    )

    return EventSourceResponse(_stream_results(results))
