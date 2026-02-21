"""Agentic chat UI generator — conversational interface to the Coordinator Agent."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, PackageLoader
from ninja_core.schema.project import AgenticSchema

# Domain names must be alphanumeric (with underscores, hyphens, and spaces allowed).
# This prevents script injection via malicious domain names in schema metadata.
_SAFE_DOMAIN_NAME = re.compile(r"^[\w \-]+$")


def _validate_domain_name(name: str) -> str:
    """Validate that a domain name contains only safe characters.

    Raises ValueError if the name contains characters that could be used
    for injection attacks (e.g. quotes, angle brackets, semicolons).
    """
    if not _SAFE_DOMAIN_NAME.match(name):
        raise ValueError(
            f"Domain name {name!r} contains unsafe characters. "
            "Only alphanumeric characters, underscores, hyphens, and spaces are allowed."
        )
    return name


def _get_template_env() -> Environment:
    """Create a Jinja2 environment with autoescape enabled for HTML templates."""
    return Environment(
        loader=PackageLoader("ninja_ui", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


class ChatGenerator:
    """Generates the agentic chat UI HTML page."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self._env = _get_template_env()

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate the chat UI page.

        Raises:
            ValueError: If any domain name contains unsafe characters.
        """
        chat_dir = output_dir / "chat"
        chat_dir.mkdir(parents=True, exist_ok=True)

        template = self._env.get_template("chat.html.j2")
        domains_meta = [
            {
                "name": _validate_domain_name(d.name),
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
