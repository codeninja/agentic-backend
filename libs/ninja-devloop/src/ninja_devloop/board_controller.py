"""Central board controller — sync, cache, and transition management."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from ninja_devloop.github_client import GitHubClient
from ninja_devloop.models import BoardItem, BoardState, BoardStatus
from ninja_devloop.transitions import validate_transition

logger = logging.getLogger("ninja-board")


class BoardController:
    def __init__(
        self,
        cache_path: str | Path = ".dev-loop-board-cache.json",
        sync_interval: int = 300,
        client: GitHubClient | None = None,
    ):
        self.cache_path = Path(cache_path)
        self.sync_interval = sync_interval
        self.client = client or GitHubClient()
        self._state = BoardState()
        self._lock = threading.RLock()
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                raw = self.cache_path.read_text()
                self._state = BoardState.model_validate_json(raw)
            except Exception:
                self._state = BoardState()

    def _persist_cache(self) -> None:
        data = self._state.model_dump_json(indent=2)
        # Atomic write: write to tmp file in same directory, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=self.cache_path.parent,
            prefix=".board-cache-",
            suffix=".tmp",
        )
        try:
            os.write(fd, data.encode())
            os.close(fd)
            fd = -1
            os.replace(tmp_path, self.cache_path)
        except Exception:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def full_sync(self) -> BoardState:
        with self._lock:
            logger.info("Fetching board items...")
            raw_items = self.client.fetch_board_items()
            new_items: dict[int, BoardItem] = {}
            skipped_done = 0

            for raw in raw_items:
                content = raw.get("content", {})
                issue_num = content.get("number")
                if not issue_num:
                    continue

                status_str = raw.get("status", "No Status")
                try:
                    status = BoardStatus(status_str)
                except ValueError:
                    status = BoardStatus.NO_STATUS

                # Skip Done tickets — they're dead weight in the cache
                if status == BoardStatus.DONE:
                    skipped_done += 1
                    continue

                item = BoardItem(
                    item_id=raw.get("id", ""),
                    issue_number=issue_num,
                    status=status,
                    title=raw.get("title", content.get("title", "")),
                )
                new_items[issue_num] = item

            logger.info(
                "Board: %d active items, %d done (skipped), %d total",
                len(new_items),
                skipped_done,
                len(new_items) + skipped_done,
            )

            # Enrich each item with issue detail and PR info
            total = len(new_items)
            for i, (issue_num, item) in enumerate(new_items.items(), 1):
                logger.info(
                    "Enriching [%d/%d] #%d %s",
                    i,
                    total,
                    issue_num,
                    item.title[:60] if item.title else "(no title)",
                )
                try:
                    detail = self.client.fetch_issue_detail(issue_num)
                    item.title = detail.get("title", item.title)
                    item.body = detail.get("body", "")
                    item.labels = [label["name"] for label in detail.get("labels", [])]
                    raw_comments = detail.get("comments", [])
                    item.comments = [
                        {
                            "author": c.get("author", {}).get("login", "unknown"),
                            "body": c.get("body", ""),
                        }
                        for c in raw_comments[-5:]  # last 5 comments
                    ]
                except Exception as e:
                    logger.warning("  Failed to enrich #%d: %s", issue_num, e)

                # Check for PR on expected branch
                branch = f"fix/issue-{issue_num}"
                try:
                    pr_data = self.client.fetch_pr_for_branch(branch)
                    if pr_data:
                        item.pull_request = {
                            "number": pr_data.get("number"),
                            "is_draft": pr_data.get("isDraft", True),
                            "branch": branch,
                        }
                        logger.info(
                            "  PR #%s found (%s)",
                            pr_data.get("number"),
                            "draft" if pr_data.get("isDraft") else "ready",
                        )
                except Exception:
                    pass

                item.enriched = True

            self._state = BoardState(items=new_items, last_sync=time.time())
            self._persist_cache()
            logger.info("Sync complete — %d items cached", len(new_items))
            return self._state

    def needs_sync(self) -> bool:
        with self._lock:
            if self._state.last_sync == 0.0:
                return True
            return (time.time() - self._state.last_sync) >= self.sync_interval

    def get_state(self) -> BoardState:
        with self._lock:
            return self._state

    def set_status(self, issue_number: int, new_status: BoardStatus) -> None:
        with self._lock:
            item = self._state.get_item(issue_number)
            if not item:
                raise ValueError(f"Issue #{issue_number} not found in board state")

            old_status = item.status
            validate_transition(old_status, new_status, strict=True)
            logger.info("#%d: %s → %s", issue_number, old_status.value, new_status.value)
            self.client.set_board_status(item.item_id, new_status)
            item.status = new_status
            self._persist_cache()

    def get_issue_context(self, issue_number: int) -> dict:
        with self._lock:
            item = self._state.get_item(issue_number)

        if not item:
            raise ValueError(f"Issue #{issue_number} not found in board state")

        # Enrich on demand if not yet enriched
        if not item.enriched:
            try:
                detail = self.client.fetch_issue_detail(issue_number)
                item.title = detail.get("title", item.title)
                item.body = detail.get("body", "")
                item.labels = [label["name"] for label in detail.get("labels", [])]
                raw_comments = detail.get("comments", [])
                item.comments = [
                    {
                        "author": c.get("author", {}).get("login", "unknown"),
                        "body": c.get("body", ""),
                    }
                    for c in raw_comments[-5:]
                ]
                item.enriched = True
                with self._lock:
                    self._persist_cache()
            except Exception:
                pass

        return {
            "item_id": item.item_id,
            "issue_number": item.issue_number,
            "status": item.status.value,
            "title": item.title,
            "body": item.body,
            "labels": item.labels,
            "comments": item.comments,
            "pull_request": item.pull_request,
            "enriched": item.enriched,
        }
