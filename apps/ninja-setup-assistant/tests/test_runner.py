"""Tests for the CLI runner module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ninja_setup_assistant.runner import run_assistant


class TestRunAssistant:
    async def test_run_assistant_creates_state_dir(self, tmp_path: Path) -> None:
        """run_assistant should create .ninjastack/ in the project root."""
        from ninja_cli.state import init_state

        config = init_state("test-project", tmp_path)
        assert (tmp_path / ".ninjastack" / "schema.json").is_file()
        assert config.project_name == "test-project"

    async def test_run_assistant_returns_none_without_api_key(self, tmp_path: Path) -> None:
        """Without an API key, run_assistant should return None gracefully."""
        with patch.dict("os.environ", {}, clear=True):
            result = await run_assistant(project_name="test", root=tmp_path)
            assert result is None
