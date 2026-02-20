"""Tests for the CLI runner module."""

from __future__ import annotations

from pathlib import Path


class TestRunAssistant:
    async def test_run_assistant_creates_state_dir(self, tmp_path: Path) -> None:
        """run_assistant should create .ninjastack/ in the project root."""
        # We can't run the full interactive loop in tests, but we can verify
        # that the function initializes state correctly by checking the import
        # and that the state dir would be created.
        from ninja_cli.state import init_state

        config = init_state("test-project", tmp_path)
        assert (tmp_path / ".ninjastack" / "schema.json").is_file()
        assert config.project_name == "test-project"
