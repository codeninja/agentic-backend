"""Tests for ninja_devloop.board_controller."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ninja_devloop.board_controller import BoardController
from ninja_devloop.github_client import GitHubClient
from ninja_devloop.models import BoardItem, BoardState, BoardStatus
from ninja_devloop.transitions import InvalidTransitionError


def _mock_client() -> MagicMock:
    client = MagicMock(spec=GitHubClient)
    client.fetch_board_items.return_value = [
        {
            "id": "PVTI_001",
            "status": "Triage",
            "title": "Fix login bug",
            "content": {"number": 10, "title": "Fix login bug"},
        },
        {
            "id": "PVTI_002",
            "status": "Todo",
            "title": "Add caching",
            "content": {"number": 20, "title": "Add caching"},
        },
        {
            "id": "PVTI_003",
            "status": "In Progress",
            "title": "Refactor auth",
            "content": {"number": 30, "title": "Refactor auth"},
        },
    ]
    client.fetch_issue_detail.side_effect = lambda num: {
        "title": f"Issue #{num}",
        "body": f"Body for #{num}",
        "labels": [{"name": "bug"}, {"name": "priority: high"}],
        "comments": [
            {"author": {"login": "alice"}, "body": "First comment"},
            {"author": {"login": "bob"}, "body": "Second comment"},
        ],
    }
    client.fetch_pr_for_branch.return_value = None
    client.set_board_status.return_value = None
    return client


class TestFullSync:
    def test_sync_populates_state(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        state = ctrl.full_sync()

        assert len(state.items) == 3
        assert state.items[10].status == BoardStatus.TRIAGE
        assert state.items[20].status == BoardStatus.TODO
        assert state.items[30].status == BoardStatus.IN_PROGRESS

    def test_sync_skips_done_items(self, tmp_path: Path):
        client = _mock_client()
        client.fetch_board_items.return_value.append(
            {
                "id": "PVTI_DONE",
                "status": "Done",
                "title": "Already finished",
                "content": {"number": 99, "title": "Already finished"},
            }
        )
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        state = ctrl.full_sync()

        assert 99 not in state.items
        assert len(state.items) == 3

    def test_sync_enriches_items(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        state = ctrl.full_sync()

        item = state.items[10]
        assert item.enriched is True
        assert item.body == "Body for #10"
        assert item.labels == ["bug", "priority: high"]
        assert len(item.comments) == 2

    def test_sync_persists_cache(self, tmp_path: Path):
        cache_file = tmp_path / "cache.json"
        client = _mock_client()
        ctrl = BoardController(cache_path=cache_file, client=client)
        ctrl.full_sync()

        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "items" in data
        assert data["last_sync"] > 0

    def test_sync_loads_from_cache_on_restart(self, tmp_path: Path):
        cache_file = tmp_path / "cache.json"
        client = _mock_client()

        ctrl1 = BoardController(cache_path=cache_file, client=client)
        ctrl1.full_sync()

        # Create new controller with same cache (no sync)
        client2 = _mock_client()
        ctrl2 = BoardController(cache_path=cache_file, client=client2)
        state = ctrl2.get_state()
        assert len(state.items) == 3
        client2.fetch_board_items.assert_not_called()


class TestSetStatus:
    def test_valid_transition(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        ctrl.full_sync()

        ctrl.set_status(10, BoardStatus.TODO)  # Triage → Todo
        assert ctrl.get_state().items[10].status == BoardStatus.TODO
        client.set_board_status.assert_called_once_with("PVTI_001", BoardStatus.TODO)

    def test_invalid_transition_raises(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        ctrl.full_sync()

        # Todo → Done is invalid (must go through In Progress first)
        with pytest.raises(InvalidTransitionError):
            ctrl.set_status(20, BoardStatus.DONE)

    def test_unknown_issue_raises(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        ctrl.full_sync()

        with pytest.raises(ValueError, match="not found"):
            ctrl.set_status(999, BoardStatus.TODO)

    def test_set_status_persists(self, tmp_path: Path):
        cache_file = tmp_path / "cache.json"
        client = _mock_client()
        ctrl = BoardController(cache_path=cache_file, client=client)
        ctrl.full_sync()

        ctrl.set_status(10, BoardStatus.TODO)

        # Reload from cache
        ctrl2 = BoardController(cache_path=cache_file, client=_mock_client())
        assert ctrl2.get_state().items[10].status == BoardStatus.TODO


class TestGetIssueContext:
    def test_returns_context_dict(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        ctrl.full_sync()

        ctx = ctrl.get_issue_context(10)
        assert ctx["issue_number"] == 10
        assert ctx["title"] == "Issue #10"
        assert ctx["body"] == "Body for #10"
        assert "bug" in ctx["labels"]
        assert ctx["enriched"] is True

    def test_missing_issue_raises(self, tmp_path: Path):
        client = _mock_client()
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=client)
        ctrl.full_sync()

        with pytest.raises(ValueError, match="not found"):
            ctrl.get_issue_context(999)

    def test_enriches_on_demand(self, tmp_path: Path):
        client = _mock_client()
        # Simulate a non-enriched item by loading from cache
        cache_file = tmp_path / "cache.json"
        state = BoardState(
            items={
                42: BoardItem(
                    item_id="PVTI_X",
                    issue_number=42,
                    status=BoardStatus.TODO,
                    enriched=False,
                )
            },
            last_sync=1000.0,
        )
        cache_file.write_text(state.model_dump_json())

        ctrl = BoardController(cache_path=cache_file, client=client)
        ctx = ctrl.get_issue_context(42)
        assert ctx["enriched"] is True
        client.fetch_issue_detail.assert_called_once_with(42)


class TestNeedsSync:
    def test_needs_sync_when_never_synced(self, tmp_path: Path):
        ctrl = BoardController(cache_path=tmp_path / "cache.json", client=_mock_client())
        assert ctrl.needs_sync() is True

    def test_no_sync_needed_after_sync(self, tmp_path: Path):
        ctrl = BoardController(
            cache_path=tmp_path / "cache.json",
            client=_mock_client(),
            sync_interval=300,
        )
        ctrl.full_sync()
        assert ctrl.needs_sync() is False
