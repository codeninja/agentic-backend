"""Board status transition rules."""

from ninja_devloop.models import BoardStatus


class InvalidTransitionError(Exception):
    def __init__(self, from_status: BoardStatus, to_status: BoardStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition: {from_status.value} \u2192 {to_status.value}")


VALID_TRANSITIONS: dict[BoardStatus, set[BoardStatus]] = {
    BoardStatus.NO_STATUS: {BoardStatus.TRIAGE},
    BoardStatus.TRIAGE: {BoardStatus.TODO, BoardStatus.PLANNING, BoardStatus.NEED_HUMAN, BoardStatus.DONE},
    BoardStatus.PLANNING: {BoardStatus.TODO, BoardStatus.NEED_HUMAN, BoardStatus.DONE},
    BoardStatus.TODO: {BoardStatus.IN_PROGRESS},
    BoardStatus.IN_PROGRESS: {BoardStatus.AI_REVIEW, BoardStatus.PLANNING, BoardStatus.DONE},
    BoardStatus.AI_REVIEW: {BoardStatus.IN_REVIEW, BoardStatus.DONE, BoardStatus.REJECTED, BoardStatus.NEED_HUMAN},
    BoardStatus.REJECTED: {BoardStatus.IN_PROGRESS, BoardStatus.NEED_HUMAN},
    BoardStatus.IN_REVIEW: {BoardStatus.DONE, BoardStatus.REJECTED},
    BoardStatus.DONE: set(),
    BoardStatus.NEED_HUMAN: {BoardStatus.TRIAGE, BoardStatus.TODO, BoardStatus.PLANNING, BoardStatus.DONE},
}


def validate_transition(from_status: BoardStatus, to_status: BoardStatus, *, strict: bool = True) -> bool:
    valid_targets = VALID_TRANSITIONS.get(from_status, set())
    if to_status in valid_targets:
        return True
    if strict:
        raise InvalidTransitionError(from_status, to_status)
    return False
