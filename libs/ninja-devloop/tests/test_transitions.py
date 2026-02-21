"""Tests for ninja_devloop.transitions."""

import pytest
from ninja_devloop.models import BoardStatus
from ninja_devloop.transitions import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    validate_transition,
)


class TestValidTransitions:
    def test_valid_transition_returns_true(self):
        assert validate_transition(BoardStatus.TRIAGE, BoardStatus.TODO) is True

    def test_valid_transition_no_exception_in_strict(self):
        # Should not raise
        validate_transition(BoardStatus.TODO, BoardStatus.IN_PROGRESS, strict=True)

    def test_invalid_transition_raises_in_strict(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(BoardStatus.TODO, BoardStatus.DONE, strict=True)
        assert exc_info.value.from_status == BoardStatus.TODO
        assert exc_info.value.to_status == BoardStatus.DONE
        assert "Todo" in str(exc_info.value)
        assert "Done" in str(exc_info.value)

    def test_invalid_transition_returns_false_permissive(self):
        assert validate_transition(BoardStatus.TODO, BoardStatus.DONE, strict=False) is False

    def test_done_has_no_valid_transitions(self):
        assert VALID_TRANSITIONS[BoardStatus.DONE] == set()

    def test_no_status_can_only_go_to_triage(self):
        assert VALID_TRANSITIONS[BoardStatus.NO_STATUS] == {BoardStatus.TRIAGE}

    def test_every_status_has_entry(self):
        for status in BoardStatus:
            assert status in VALID_TRANSITIONS, f"Missing entry for {status}"

    @pytest.mark.parametrize(
        "from_s,to_s",
        [
            (BoardStatus.TRIAGE, BoardStatus.PLANNING),
            (BoardStatus.PLANNING, BoardStatus.TODO),
            (BoardStatus.IN_PROGRESS, BoardStatus.AI_REVIEW),
            (BoardStatus.AI_REVIEW, BoardStatus.IN_REVIEW),
            (BoardStatus.AI_REVIEW, BoardStatus.REJECTED),
            (BoardStatus.REJECTED, BoardStatus.IN_PROGRESS),
            (BoardStatus.IN_REVIEW, BoardStatus.DONE),
            (BoardStatus.IN_REVIEW, BoardStatus.REJECTED),
            (BoardStatus.NEED_HUMAN, BoardStatus.TRIAGE),
        ],
    )
    def test_various_valid_transitions(self, from_s, to_s):
        assert validate_transition(from_s, to_s) is True
