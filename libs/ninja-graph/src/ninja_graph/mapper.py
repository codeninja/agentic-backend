"""ASD relationships → Neo4j schema mapping.

Converts entity definitions and relationships from the Agentic Schema Definition
into a graph schema with node labels, edge types, and property mappings.
"""

from __future__ import annotations

from ninja_core.schema.entity import EntitySchema, FieldSchema
from ninja_core.schema.project import AgenticSchema
from ninja_core.schema.relationship import RelationshipSchema
from pydantic import BaseModel, Field


class NodeLabel(BaseModel):
    """A node label derived from an ASD entity."""

    name: str = Field(description="Node label (entity name).")
    properties: list[str] = Field(default_factory=list, description="Property names from entity fields.")
    primary_key: str | None = Field(default=None, description="Primary key field name.")


class EdgeType(BaseModel):
    """An edge type derived from an ASD relationship."""

    name: str = Field(description="Edge type label.")
    source_label: str = Field(description="Source node label.")
    target_label: str = Field(description="Target node label.")
    properties: list[str] = Field(default_factory=list, description="Edge property names.")


class GraphSchema(BaseModel):
    """Complete graph schema derived from an ASD."""

    node_labels: list[NodeLabel] = Field(default_factory=list)
    edge_types: list[EdgeType] = Field(default_factory=list)


def _extract_node_label(entity: EntitySchema) -> NodeLabel:
    """Convert an entity to a node label definition."""
    pk: str | None = None
    props: list[str] = []
    field: FieldSchema
    for field in entity.fields:
        props.append(field.name)
        if field.primary_key:
            pk = field.name
    return NodeLabel(name=entity.name, properties=props, primary_key=pk)


def _extract_edge_type(rel: RelationshipSchema) -> EdgeType:
    """Convert a relationship to an edge type definition."""
    label = rel.edge_label or rel.name.upper()
    props: list[str] = []
    if rel.source_field:
        props.append(rel.source_field)
    if rel.target_field:
        props.append(rel.target_field)
    return EdgeType(name=label, source_label=rel.source_entity, target_label=rel.target_entity, properties=props)


def map_asd_to_graph_schema(asd: AgenticSchema) -> GraphSchema:
    """Map an Agentic Schema Definition to a graph schema.

    All entities become node labels. All relationships become edge types.
    """
    node_labels = [_extract_node_label(e) for e in asd.entities]
    edge_types = [_extract_edge_type(r) for r in asd.relationships]
    return GraphSchema(node_labels=node_labels, edge_types=edge_types)
