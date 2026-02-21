"""CRUD viewer generator — produces HTML table views per ASD entity."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader
from ninja_core.schema.entity import EntitySchema
from ninja_core.schema.project import AgenticSchema

from ninja_ui.shared.assets import FIELD_TYPE_INPUT_MAP, snake_case


def _get_template_env() -> Environment:
    """Create a Jinja2 environment with autoescape enabled for HTML templates."""
    return Environment(
        loader=PackageLoader("ninja_ui", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _build_field_meta(entity: EntitySchema) -> list[dict]:
    """Pre-process entity fields for template rendering."""
    meta: list[dict] = []
    for f in entity.fields:
        ft = f.field_type.value if hasattr(f.field_type, "value") else str(f.field_type)
        constraints: dict = {}
        if f.constraints:
            if f.constraints.min_length is not None:
                constraints["minlength"] = f.constraints.min_length
            if f.constraints.max_length is not None:
                constraints["maxlength"] = f.constraints.max_length
            if f.constraints.pattern is not None:
                constraints["pattern"] = f.constraints.pattern
            if f.constraints.ge is not None:
                constraints["min"] = f.constraints.ge
            if f.constraints.le is not None:
                constraints["max"] = f.constraints.le
            if f.constraints.enum_values:
                constraints["enum_values"] = f.constraints.enum_values
        meta.append(
            {
                "name": f.name,
                "field_type": ft,
                "input_type": FIELD_TYPE_INPUT_MAP.get(ft, "text"),
                "nullable": f.nullable,
                "primary_key": f.primary_key,
                "constraints": constraints,
                "description": f.description or "",
            }
        )
    return meta


def _find_relationships(entity: EntitySchema, schema: AgenticSchema) -> list[dict]:
    """Find relationships where this entity is source or target."""
    rels: list[dict] = []
    for r in schema.relationships:
        if r.source_entity == entity.name:
            rels.append(
                {
                    "name": r.name,
                    "target_entity": r.target_entity,
                    "target_slug": snake_case(r.target_entity),
                    "cardinality": r.cardinality.value if hasattr(r.cardinality, "value") else str(r.cardinality),
                    "direction": "outgoing",
                }
            )
        elif r.target_entity == entity.name:
            rels.append(
                {
                    "name": r.name,
                    "target_entity": r.source_entity,
                    "target_slug": snake_case(r.source_entity),
                    "cardinality": r.cardinality.value if hasattr(r.cardinality, "value") else str(r.cardinality),
                    "direction": "incoming",
                }
            )
    return rels


class CrudGenerator:
    """Generates CRUD viewer HTML pages from ASD entities."""

    def __init__(self, schema: AgenticSchema) -> None:
        self.schema = schema
        self._env = _get_template_env()

    def generate_entity_page(self, entity: EntitySchema, output_dir: Path) -> Path:
        """Generate an HTML CRUD page for a single entity."""
        template = self._env.get_template("crud_entity.html.j2")
        fields_meta = _build_field_meta(entity)
        relationships = _find_relationships(entity, self.schema)
        has_embedding = any(f.embedding is not None for f in entity.fields)
        slug = snake_case(entity.name)

        html = template.render(
            entity=entity,
            fields_meta=fields_meta,
            relationships=relationships,
            has_embedding=has_embedding,
            slug=slug,
            gql_endpoint="/graphql",
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{slug}.html"
        out_path.write_text(html, encoding="utf-8")
        return out_path

    def generate_index(self, output_dir: Path) -> Path:
        """Generate the CRUD index page listing all entities."""
        template = self._env.get_template("crud_index.html.j2")
        entities_meta = [
            {
                "name": e.name,
                "slug": snake_case(e.name),
                "field_count": len(e.fields),
                "storage_engine": (
                    e.storage_engine.value if hasattr(e.storage_engine, "value") else str(e.storage_engine)
                ),
            }
            for e in self.schema.entities
        ]
        html = template.render(
            project_name=self.schema.project_name,
            entities=entities_meta,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "index.html"
        out_path.write_text(html, encoding="utf-8")
        return out_path

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate all CRUD viewer pages."""
        crud_dir = output_dir / "crud"
        paths: list[Path] = []
        paths.append(self.generate_index(crud_dir))
        for entity in self.schema.entities:
            paths.append(self.generate_entity_page(entity, crud_dir))
        return paths
