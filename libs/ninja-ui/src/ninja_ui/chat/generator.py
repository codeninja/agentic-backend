"""Agentic chat UI generator — conversational interface to the Coordinator Agent."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader
from ninja_core.schema.project import AgenticSchema

from ninja_ui.shared.sanitize import safe_identifier, sanitize_for_js_string


def _get_template_env() -> Environment:
    """Create a Jinja2 environment with autoescape enabled for HTML safety."""
    env = Environment(
        loader=PackageLoader("ninja_ui", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["safe_id"] = safe_identifier
    env.filters["js_string"] = sanitize_for_js_string
    return env


class ChatGenerator:
    """Generates the agentic chat UI HTML page."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self._env = _get_template_env()

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate the chat UI page."""
        chat_dir = output_dir / "chat"
        chat_dir.mkdir(parents=True, exist_ok=True)

        template = self._env.get_template("chat.html.j2")
        domains_meta = [
            {
                "name": d.name,
                "description": d.description or d.name,
                "entities": d.entities,
            }
            for d in self.schema.domains
        ]

        html = template.render(
            project_name=self.schema.project_name,
            domains=domains_meta,
            gql_endpoint="/graphql",
        )

        out_path = chat_dir / "index.html"
        out_path.write_text(html, encoding="utf-8")
        return [out_path]
