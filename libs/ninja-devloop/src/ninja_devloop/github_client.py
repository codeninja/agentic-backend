"""GitHub API client wrapping the `gh` CLI."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from ninja_devloop.models import STATUS_OPTION_IDS, BoardStatus

# Project constants
DEFAULT_REPO = "codeninja/ninja-stack"
DEFAULT_PROJECT_NUM = 4
DEFAULT_PROJECT_OWNER = "codeninja"
DEFAULT_PROJECT_ID = "PVT_kwHNOkLOAT6Qtg"
DEFAULT_FIELD_ID = "PVTSSF_lAHNOkLOAT6Qts4Pf31M"


class GitHubClientError(Exception):
    pass


class GitHubClient:
    def __init__(
        self,
        repo: str = DEFAULT_REPO,
        project_num: int = DEFAULT_PROJECT_NUM,
        project_owner: str = DEFAULT_PROJECT_OWNER,
        project_id: str = DEFAULT_PROJECT_ID,
        field_id: str = DEFAULT_FIELD_ID,
    ):
        self.repo = repo
        self.project_num = project_num
        self.project_owner = project_owner
        self.project_id = project_id
        self.field_id = field_id

    def _run(self, args: list[str], *, timeout: int = 30) -> str:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise GitHubClientError(f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired as e:
            raise GitHubClientError(f"Command timed out: {' '.join(args)}") from e

    def _run_json(self, args: list[str], *, timeout: int = 30) -> Any:
        raw = self._run(args, timeout=timeout)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise GitHubClientError(f"Invalid JSON from: {' '.join(args)}") from e

    def fetch_board_items(self) -> list[dict]:
        data = self._run_json(
            [
                "gh",
                "project",
                "item-list",
                str(self.project_num),
                "--owner",
                self.project_owner,
                "--format",
                "json",
                "--limit",
                "500",
            ],
            timeout=60,
        )
        return data.get("items", [])

    def fetch_issue_detail(self, issue_number: int) -> dict:
        return self._run_json(
            [
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                self.repo,
                "--json",
                "title,body,labels,comments",
            ]
        )

    def fetch_pr_for_branch(self, branch: str) -> dict | None:
        data = self._run_json(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.repo,
                "--head",
                branch,
                "--json",
                "number,isDraft",
            ]
        )
        if isinstance(data, list) and data:
            return data[0]
        return None

    def set_board_status(self, item_id: str, status: BoardStatus) -> None:
        option_id = STATUS_OPTION_IDS.get(status)
        if not option_id:
            raise GitHubClientError(f"No option ID for status: {status}")
        query = f"""mutation {{
            updateProjectV2ItemFieldValue(input: {{
                projectId: "{self.project_id}",
                itemId: "{item_id}",
                fieldId: "{self.field_id}",
                value: {{ singleSelectOptionId: "{option_id}" }}
            }}) {{ projectV2Item {{ id }} }}
        }}"""
        self._run(["gh", "api", "graphql", "-f", f"query={query}"])

    def check_rate_limit(self) -> dict:
        return self._run_json(["gh", "api", "rate_limit"])

    def add_issue_comment(self, issue_number: int, body: str) -> None:
        self._run(
            [
                "gh",
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                self.repo,
                "--body",
                body,
            ]
        )
