"""Board models for the dev-loop controller."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class BoardStatus(StrEnum):
    TRIAGE = "Triage"
    PLANNING = "Planning"
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    AI_REVIEW = "AI Review"
    REJECTED = "Rejected"
    IN_REVIEW = "In Review"
    DONE = "Done"
    NEED_HUMAN = "Need Human"
    NO_STATUS = "No Status"


STATUS_OPTION_IDS: dict[BoardStatus, str] = {
    BoardStatus.TRIAGE: "7075b0bd",
    BoardStatus.PLANNING: "5860e624",
    BoardStatus.TODO: "398c03ac",
    BoardStatus.IN_PROGRESS: "20fd4c4d",
    BoardStatus.AI_REVIEW: "35df9b65",
    BoardStatus.REJECTED: "1b81d027",
    BoardStatus.IN_REVIEW: "bbfc519d",
    BoardStatus.DONE: "873d8d61",
    BoardStatus.NEED_HUMAN: "f96e10cc",
}

OPTION_ID_TO_STATUS: dict[str, BoardStatus] = {v: k for k, v in STATUS_OPTION_IDS.items()}


_PRIORITY_ORDER: dict[str, int] = {
    "priority: critical": 1,
    "priority: high": 10,
    "priority: medium": 50,
    "priority: low": 90,
}


def _priority_key(item: BoardItem) -> int:
    for label in item.labels:
        low = label.lower()
        if low in _PRIORITY_ORDER:
            return _PRIORITY_ORDER[low]
    return 50  # default to medium


class BoardItem(BaseModel):
    item_id: str
    issue_number: int
    status: BoardStatus = BoardStatus.NO_STATUS
    title: str = ""
    body: str = ""
    labels: list[str] = []
    comments: list[dict] = []
    pull_request: dict | None = None
    enriched: bool = False


class BoardState(BaseModel):
    items: dict[int, BoardItem] = {}
    last_sync: float = 0.0

    def by_status(self, status: BoardStatus) -> list[BoardItem]:
        return sorted(
            (item for item in self.items.values() if item.status == status),
            key=lambda i: i.issue_number,
        )

    def prioritized_todo(self) -> list[BoardItem]:
        todo_items = [item for item in self.items.values() if item.status == BoardStatus.TODO]
        return sorted(todo_items, key=_priority_key)

    def status_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items.values():
            key = item.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def get_item(self, issue_number: int) -> BoardItem | None:
        return self.items.get(issue_number)
