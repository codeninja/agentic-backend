"""Shared fixtures for ninja-api tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ninja_core.schema.domain import DomainSchema
from ninja_core.schema.entity import EntitySchema, FieldSchema, FieldType, StorageEngine
from ninja_core.schema.project import AgenticSchema


@pytest.fixture()
def sample_asd() -> AgenticSchema:
    """Minimal ASD with one domain and two entities."""
    return AgenticSchema(
        project_name="test-project",
        entities=[
            EntitySchema(
                name="User",
                storage_engine=StorageEngine.SQL,
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                    FieldSchema(name="name", field_type=FieldType.STRING),
                ],
                description="A user.",
            ),
            EntitySchema(
                name="Task",
                storage_engine=StorageEngine.SQL,
                fields=[
                    FieldSchema(name="id", field_type=FieldType.UUID, primary_key=True),
                    FieldSchema(name="title", field_type=FieldType.STRING),
                ],
                description="A task.",
            ),
        ],
        domains=[
            DomainSchema(name="Core", entities=["User", "Task"]),
        ],
    )


@pytest.fixture()
def asd_file(tmp_path: Path, sample_asd: AgenticSchema) -> Path:
    """Write the sample ASD to a temp file and return its path."""
    schema_path = tmp_path / ".ninjastack" / "schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(sample_asd.model_dump_json(indent=2))
    return schema_path


@pytest.fixture()
def connections_file(tmp_path: Path) -> Path:
    """Write a minimal connections.json to temp and return its path."""
    conn_path = tmp_path / ".ninjastack" / "connections.json"
    conn_path.parent.mkdir(parents=True, exist_ok=True)
    conn_path.write_text(
        json.dumps(
            {
                "default": {
                    "engine": "sql",
                    "url": "sqlite+aiosqlite:///:memory:",
                }
            }
        )
    )
    return conn_path


class MockRepo:
    """Mock repository that satisfies the Repository protocol."""

    async def find_by_id(self, id: str) -> dict[str, Any] | None:
        return {"id": id, "name": "test"}

    async def find_many(self, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return [{"id": "1", "name": "test"}]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "id": "new-id"}

    async def update(self, id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        return {"id": id, **patch}

    async def delete(self, id: str) -> bool:
        return True

    async def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return []

    async def upsert_embedding(self, id: str, embedding: list[float]) -> None:
        pass


@pytest.fixture()
def mock_repo() -> MockRepo:
    """Return a mock repository instance."""
    return MockRepo()


@pytest.fixture(autouse=True)
def _set_dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set NINJASTACK_ENV=test so AuthConfig validators don't error."""
    monkeypatch.setenv("NINJASTACK_ENV", "test")
