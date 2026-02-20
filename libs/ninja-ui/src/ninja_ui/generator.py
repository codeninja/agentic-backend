"""Top-level UI generator — orchestrates CRUD and Chat generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ninja_core.schema.project import AgenticSchema

from ninja_ui.chat.generator import ChatGenerator
from ninja_ui.crud.generator import CrudGenerator


@dataclass
class UIGenerationResult:
    """Result of a UI generation run."""

    generated_files: list[Path] = field(default_factory=list)
    crud_dir: Path | None = None
    chat_dir: Path | None = None


class UIGenerator:
    """Orchestrates generation of all UI components from an ASD."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self._crud = CrudGenerator(schema)
        self._chat = ChatGenerator(schema)

    def generate(self, output_dir: Path) -> UIGenerationResult:
        """Generate all UI pages (CRUD + Chat) into output_dir."""
        result = UIGenerationResult()

        crud_files = self._crud.generate(output_dir)
        result.generated_files.extend(crud_files)
        result.crud_dir = output_dir / "crud"

        chat_files = self._chat.generate(output_dir)
        result.generated_files.extend(chat_files)
        result.chat_dir = output_dir / "chat"

        return result

    def generate_crud_only(self, output_dir: Path) -> UIGenerationResult:
        """Generate only CRUD viewer pages."""
        result = UIGenerationResult()
        crud_files = self._crud.generate(output_dir)
        result.generated_files.extend(crud_files)
        result.crud_dir = output_dir / "crud"
        return result

    def generate_chat_only(self, output_dir: Path) -> UIGenerationResult:
        """Generate only Chat UI pages."""
        result = UIGenerationResult()
        chat_files = self._chat.generate(output_dir)
        result.generated_files.extend(chat_files)
        result.chat_dir = output_dir / "chat"
        return result
