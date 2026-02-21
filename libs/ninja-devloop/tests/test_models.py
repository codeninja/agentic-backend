"""Tests for ninja_devloop.models."""

from ninja_devloop.models import (
    OPTION_ID_TO_STATUS,
    STATUS_OPTION_IDS,
    BoardItem,
    BoardState,
    BoardStatus,
)


class TestBoardStatus:
    def test_has_all_10_members(self):
        assert len(BoardStatus) == 10

    def test_values(self):
        assert BoardStatus.TRIAGE == "Triage"
        assert BoardStatus.PLANNING == "Planning"
        assert BoardStatus.TODO == "Todo"
        assert BoardStatus.IN_PROGRESS == "In Progress"
        assert BoardStatus.AI_REVIEW == "AI Review"
        assert BoardStatus.REJECTED == "Rejected"
        assert BoardStatus.IN_REVIEW == "In Review"
        assert BoardStatus.DONE == "Done"
        assert BoardStatus.NEED_HUMAN == "Need Human"
        assert BoardStatus.NO_STATUS == "No Status"


class TestStatusOptionIds:
    def test_has_entries_for_all_except_no_status(self):
        for status in BoardStatus:
            if status == BoardStatus.NO_STATUS:
                assert status not in STATUS_OPTION_IDS
            else:
                assert status in STATUS_OPTION_IDS

    def test_option_id_to_status_reverses(self):
        for status, option_id in STATUS_OPTION_IDS.items():
            assert OPTION_ID_TO_STATUS[option_id] is status

    def test_option_id_to_status_length(self):
        assert len(OPTION_ID_TO_STATUS) == len(STATUS_OPTION_IDS)


class TestBoardItem:
    def test_creation_with_defaults(self):
        item = BoardItem(item_id="PVTI_123", issue_number=42)
        assert item.item_id == "PVTI_123"
        assert item.issue_number == 42
        assert item.status == BoardStatus.NO_STATUS
        assert item.title == ""
        assert item.body == ""
        assert item.labels == []
        assert item.comments == []
        assert item.pull_request is None
        assert item.enriched is False

    def test_creation_with_values(self):
        item = BoardItem(
            item_id="PVTI_456",
            issue_number=10,
            status=BoardStatus.TODO,
            title="Fix bug",
            labels=["priority: high", "bug"],
            pull_request={"number": 99, "is_draft": False, "branch": "fix/bug"},
        )
        assert item.status == BoardStatus.TODO
        assert item.title == "Fix bug"
        assert item.pull_request["number"] == 99


def _make_state() -> BoardState:
    return BoardState(
        items={
            1: BoardItem(item_id="A", issue_number=1, status=BoardStatus.TODO, labels=["priority: low"]),
            5: BoardItem(item_id="B", issue_number=5, status=BoardStatus.TODO, labels=["priority: critical"]),
            3: BoardItem(item_id="C", issue_number=3, status=BoardStatus.IN_PROGRESS),
            7: BoardItem(item_id="D", issue_number=7, status=BoardStatus.TODO, labels=["priority: high"]),
            2: BoardItem(item_id="E", issue_number=2, status=BoardStatus.DONE),
        }
    )


class TestBoardState:
    def test_by_status(self):
        state = _make_state()
        todos = state.by_status(BoardStatus.TODO)
        assert len(todos) == 3
        assert [i.issue_number for i in todos] == [1, 5, 7]

    def test_by_status_empty(self):
        state = _make_state()
        assert state.by_status(BoardStatus.TRIAGE) == []

    def test_prioritized_todo(self):
        state = _make_state()
        ordered = state.prioritized_todo()
        assert len(ordered) == 3
        # critical (5) < high (7) < low (1)
        assert [i.issue_number for i in ordered] == [5, 7, 1]

    def test_prioritized_todo_default_medium(self):
        state = BoardState(
            items={
                1: BoardItem(item_id="A", issue_number=1, status=BoardStatus.TODO, labels=[]),
                2: BoardItem(item_id="B", issue_number=2, status=BoardStatus.TODO, labels=["priority: high"]),
            }
        )
        ordered = state.prioritized_todo()
        # high (2) < default-medium (1)
        assert [i.issue_number for i in ordered] == [2, 1]

    def test_status_summary(self):
        state = _make_state()
        summary = state.status_summary()
        assert summary == {"Todo": 3, "In Progress": 1, "Done": 1}

    def test_status_summary_empty(self):
        state = BoardState()
        assert state.status_summary() == {}

    def test_get_item_found(self):
        state = _make_state()
        item = state.get_item(3)
        assert item is not None
        assert item.issue_number == 3

    def test_get_item_not_found(self):
        state = _make_state()
        assert state.get_item(999) is None
