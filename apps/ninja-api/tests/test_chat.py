"""Tests for the SSE chat endpoint."""

from __future__ import annotations

from pathlib import Path

import httpx
import jwt
import pytest


@pytest.fixture()
def app(asd_file: Path, connections_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a test app with mocked startup dependencies."""
    from ninja_api.app import create_app

    monkeypatch.chdir(asd_file.parent.parent)
    return create_app(schema_path=asd_file)


@pytest.fixture()
def auth_token(app) -> str:
    """Generate a valid JWT token using the app's own auth config."""
    config = app.state.auth_config
    return jwt.encode(
        {"sub": "test-user", "roles": ["admin"]},
        config.bearer.secret_key,
        algorithm=config.bearer.algorithm,
    )


@pytest.fixture()
async def client(app) -> httpx.AsyncClient:
    """Return an async HTTP client wired to the test app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestChatEndpoint:
    async def test_chat_requires_auth(self, client: httpx.AsyncClient) -> None:
        """POST /chat without auth should return 401."""
        resp = await client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 401

    async def test_chat_returns_sse_stream(self, client: httpx.AsyncClient, auth_token: str) -> None:
        """POST /chat with valid auth should return SSE events."""
        resp = await client.post(
            "/chat",
            json={"message": "list all users"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        # Parse SSE events from the response body.
        body = resp.text
        assert "event:" in body or "data:" in body

    async def test_chat_stream_contains_done_event(self, client: httpx.AsyncClient, auth_token: str) -> None:
        """The SSE stream should end with a 'done' event."""
        resp = await client.post(
            "/chat",
            json={"message": "show tasks"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "event: done" in resp.text

    async def test_chat_with_domain_filter(self, client: httpx.AsyncClient, auth_token: str) -> None:
        """POST /chat with domain filter should target specific domains."""
        resp = await client.post(
            "/chat",
            json={"message": "show tasks", "domains": ["Core"]},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

    async def test_chat_empty_message_rejected(self, client: httpx.AsyncClient, auth_token: str) -> None:
        """POST /chat with empty message should return 422."""
        resp = await client.post(
            "/chat",
            json={"message": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 422
