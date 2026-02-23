"""Entity and field schema definitions for the Agentic Schema Definition."""

from __future__ import annotations

import keyword
import re
import sre_parse
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Valid identifier: starts with letter, alphanumeric + underscores, max 64 chars.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

# Maximum allowed length for description fields.
MAX_DESCRIPTION_LENGTH = 500


class StorageEngine(str, Enum):
    """Database engine that owns an entity."""

    SQL = "sql"
    MONGO = "mongo"
    GRAPH = "graph"
    VECTOR = "vector"


class FieldType(str, Enum):
    """Supported field types across all storage engines."""

    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    UUID = "uuid"
    JSON = "json"
    ARRAY = "array"
    BINARY = "binary"
    ENUM = "enum"


class EmbeddingConfig(BaseModel):
    """Configuration for vectorizing a field."""

    model: str = Field(description="Embedding model identifier (e.g. 'text-embedding-3-small').")
    dimensions: int = Field(gt=0, description="Vector dimensionality.")
    chunk_strategy: str | None = Field(default=None, description="Chunking strategy for long text fields.")

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# ReDoS safety — detect nested quantifiers prone to catastrophic backtracking
# ---------------------------------------------------------------------------

_QUANTIFIER_OPS = {
    sre_parse.MAX_REPEAT,
    sre_parse.MIN_REPEAT,
}


def _has_variable_quantifier(items: list[tuple[int, Any]]) -> bool:
    """Return True if *items* contain a variable-width quantifier at any depth.

    Fixed-width quantifiers like ``{3}`` are safe and are not counted.
    """
    for op, av in items:
        if op in _QUANTIFIER_OPS:
            min_count, max_count, _ = av
            if min_count != max_count:
                return True
        if op == sre_parse.SUBPATTERN:
            # av = (group, add_flags, del_flags, pattern)
            if _has_variable_quantifier(list(av[-1])):
                return True
        if op == sre_parse.BRANCH:
            # av = [None, [branch1_items, branch2_items, ...]]
            for branch in av[1]:
                if _has_variable_quantifier(list(branch)):
                    return True
    return False


def _check_redos_safety(pattern: str) -> None:
    """Raise :class:`ValueError` if *pattern* contains nested quantifiers.

    A nested quantifier is a quantifier (``+``, ``*``, ``{m,n}``) applied to a
    group that itself contains a quantifier on a variable-width sub-expression.
    These constructs are the primary source of ReDoS via catastrophic
    backtracking.

    Examples of rejected patterns::

        (a+)+       — quantifier on group containing quantifier
        (a+)*       — same
        (a*)*       — same
        (a|a)+      — branch inside quantified group (ambiguous alternation)
        ((a+)b)+    — nested group with inner quantifier

    Examples of accepted patterns::

        [a-z]+      — character class with quantifier (no nesting)
        (abc)+      — group with quantifier but no inner quantifier
        a{2,4}      — bounded quantifier, no group
        (a{2})+     — inner quantifier is fixed-width ({2}), outer is fine
    """
    try:
        parsed = sre_parse.parse(pattern)
    except re.error:
        # Syntax errors are caught separately by the field_validator; skip here.
        return

    _walk_for_nested_quantifiers(list(parsed), in_quantifier=False)


def _walk_for_nested_quantifiers(
    items: list[tuple[int, Any]],
    in_quantifier: bool,
) -> None:
    """Recursively walk the parsed regex tree looking for nested quantifiers.

    Args:
        items: Parsed regex items from :mod:`sre_parse`.
        in_quantifier: True if we are already inside a quantified group.

    Raises:
        ValueError: If a nested quantifier is detected.
    """
    for op, av in items:
        if op in _QUANTIFIER_OPS:
            # av = (min, max, [sub-items])
            min_count, max_count, sub_items = av
            is_fixed = min_count == max_count

            if in_quantifier and not is_fixed:
                raise ValueError(
                    "ReDoS safety: pattern contains nested quantifiers "
                    "prone to catastrophic backtracking. "
                    "Avoid patterns like (a+)+, (a*)*,  (a+)*, (a|a)+, etc."
                )

            # The contents of this quantifier may themselves contain quantifiers
            # Check if any sub-expression has a variable-width quantifier
            if not is_fixed and _has_variable_quantifier(list(sub_items)):
                raise ValueError(
                    "ReDoS safety: pattern contains nested quantifiers "
                    "prone to catastrophic backtracking. "
                    "Avoid patterns like (a+)+, (a*)*,  (a+)*, (a|a)+, etc."
                )

            # Walk children — they are now "inside a quantifier" if this one
            # is variable-width.
            _walk_for_nested_quantifiers(
                list(sub_items),
                in_quantifier=in_quantifier or (not is_fixed),
            )

        elif op == sre_parse.SUBPATTERN:
            _walk_for_nested_quantifiers(list(av[-1]), in_quantifier=in_quantifier)

        elif op == sre_parse.BRANCH:
            for branch in av[1]:
                _walk_for_nested_quantifiers(list(branch), in_quantifier=in_quantifier)


class FieldConstraint(BaseModel):
    """Validation constraints for a field.

    The ``pattern`` field accepts a subset of regular expressions suitable for
    field-level string validation.  At model construction time the pattern is:

    1. Compiled with :func:`re.compile` — invalid syntax is rejected.
    2. Checked for *ReDoS-prone* constructs (nested quantifiers such as
       ``(a+)+``, ``(a*)*``, ``(a|a)*``, ``(a+)*``, etc.) that can cause
       catastrophic backtracking.

    Supported patterns include any valid Python regex that does **not** contain
    nested quantifiers (a quantifier applied to a group that itself contains a
    quantifier on a non-fixed-width sub-expression).
    """

    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1)
    pattern: str | None = Field(
        default=None,
        description=(
            "Regex pattern for string validation. Must be valid Python regex "
            "syntax and free of ReDoS-prone constructs (nested quantifiers)."
        ),
    )
    ge: float | None = Field(default=None, description="Greater than or equal.")
    le: float | None = Field(default=None, description="Less than or equal.")
    enum_values: list[str] | None = Field(default=None, description="Allowed values for enum-type fields.")

    model_config = {"extra": "forbid"}

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        """Validate the regex pattern for syntax correctness and ReDoS safety.

        Rejects:
        - Patterns that are not valid Python regular expressions.
        - Patterns containing nested quantifiers that can cause catastrophic
          backtracking (ReDoS).  Detected constructs include ``(a+)+``,
          ``(a*)*``, ``(a+)*``, ``(a|a)*``, and similar variations.
        """
        if v is None:
            return v
        # 1. Compile to verify syntax
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
        # 2. Check for ReDoS-prone nested quantifiers
        _check_redos_safety(v)
        return v

    @model_validator(mode="after")
    def validate_constraint_coherence(self) -> FieldConstraint:
        """Ensure min/max constraints are logically consistent."""
        if self.min_length is not None and self.max_length is not None:
            if self.min_length > self.max_length:
                raise ValueError(f"min_length ({self.min_length}) cannot exceed max_length ({self.max_length})")
        if self.ge is not None and self.le is not None:
            if self.ge > self.le:
                raise ValueError(f"ge ({self.ge}) cannot exceed le ({self.le})")
        return self


# Pydantic BaseModel attributes that must not be used as field names.
# Using these as field names generates syntactically valid Python but causes
# runtime bugs (shadowing Pydantic internals).
_PYDANTIC_RESERVED_ATTRS: frozenset[str] = frozenset(
    {
        "model_config",
        "model_fields",
        "model_computed_fields",
        "model_extra",
        "model_fields_set",
        "model_construct",
        "model_copy",
        "model_dump",
        "model_dump_json",
        "model_json_schema",
        "model_parametrized_name",
        "model_post_init",
        "model_rebuild",
        "model_validate",
        "model_validate_json",
        "model_validate_strings",
    }
)


_FIELD_TYPE_COMPATIBLE_PYTHON_TYPES: dict[FieldType, tuple[type, ...]] = {
    FieldType.STRING: (str,),
    FieldType.TEXT: (str,),
    FieldType.INTEGER: (int,),
    FieldType.FLOAT: (int, float),
    FieldType.BOOLEAN: (bool,),
    FieldType.UUID: (str,),
    FieldType.ENUM: (str,),
}


class FieldSchema(BaseModel):
    """Schema definition for a single field within an entity."""

    name: str = Field(min_length=1, description="Field name.")
    field_type: FieldType = Field(description="Data type of the field.")
    nullable: bool = Field(default=False, description="Whether the field accepts null values.")
    default: Any = Field(default=None, description="Default value for the field.")
    primary_key: bool = Field(default=False, description="Whether this field is the primary key.")
    unique: bool = Field(default=False, description="Whether values must be unique.")
    indexed: bool = Field(default=False, description="Whether the field should be indexed.")
    constraints: FieldConstraint | None = Field(default=None, description="Validation constraints.")
    embedding: EmbeddingConfig | None = Field(
        default=None, description="Embedding config if this field should be vectorized."
    )
    description: str | None = Field(default=None, description="Human-readable description.")

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        """Enforce safe identifier pattern on field names."""
        if not _IDENTIFIER_RE.match(v):
            raise ValueError(
                f"Field name {v!r} is not a valid identifier. "
                "Must start with a letter, contain only alphanumeric characters "
                "and underscores, and be at most 64 characters."
            )
        if keyword.iskeyword(v):
            raise ValueError(f"Field name {v!r} is a Python reserved keyword.")
        if v in _PYDANTIC_RESERVED_ATTRS:
            raise ValueError(
                f"Field name {v!r} is a Pydantic reserved attribute and would "
                "shadow BaseModel internals in generated code."
            )
        return v

    @field_validator("description")
    @classmethod
    def validate_field_description(cls, v: str | None) -> str | None:
        """Enforce maximum length on description."""
        if v is not None and len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Description too long ({len(v)} chars). Maximum is {MAX_DESCRIPTION_LENGTH} characters.")
        return v

    @model_validator(mode="after")
    def validate_field_coherence(self) -> FieldSchema:
        """Validate default type compatibility and enum constraints."""
        # Primary key must not be nullable
        if self.primary_key and self.nullable:
            raise ValueError(f"Primary key field '{self.name}' must not be nullable")

        # Enum field requires enum_values in constraints
        if self.field_type == FieldType.ENUM:
            if (
                self.constraints is None
                or self.constraints.enum_values is None
                or len(self.constraints.enum_values) == 0
            ):
                raise ValueError(f"Field '{self.name}' with field_type=ENUM requires non-empty constraints.enum_values")

        # Default value type checking (skip None defaults)
        if self.default is not None:
            allowed = _FIELD_TYPE_COMPATIBLE_PYTHON_TYPES.get(self.field_type)
            if allowed is not None and not isinstance(self.default, allowed):
                raise ValueError(
                    f"Field '{self.name}': default value {self.default!r} "
                    f"is not compatible with field_type={self.field_type.value}"
                )
        return self


class EntitySchema(BaseModel):
    """Schema definition for an entity (table, collection, node, or vector store)."""

    name: str = Field(min_length=1, description="Entity name (PascalCase recommended).")
    storage_engine: StorageEngine = Field(description="Database engine that owns this entity.")
    fields: list[FieldSchema] = Field(min_length=1, description="Fields belonging to this entity.")
    collection_name: str | None = Field(
        default=None,
        description="Override for the storage collection/table name. Defaults to entity name.",
    )
    description: str | None = Field(default=None, description="Human-readable description.")
    tags: list[str] = Field(default_factory=list, description="Arbitrary tags for categorization.")

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_entity_name(cls, v: str) -> str:
        """Enforce safe identifier pattern on entity names.

        Rejects names with newlines, quotes, control characters, and Python
        reserved keywords. This is the primary defense against prompt injection
        via schema metadata.
        """
        if not _IDENTIFIER_RE.match(v):
            raise ValueError(
                f"Entity name {v!r} is not a valid identifier. "
                "Must start with a letter, contain only alphanumeric characters "
                "and underscores, and be at most 64 characters."
            )
        if keyword.iskeyword(v):
            raise ValueError(f"Entity name {v!r} is a Python reserved keyword.")
        return v

    @field_validator("description")
    @classmethod
    def validate_entity_description(cls, v: str | None) -> str | None:
        """Enforce maximum length on description."""
        if v is not None and len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Description too long ({len(v)} chars). Maximum is {MAX_DESCRIPTION_LENGTH} characters.")
        return v

    @model_validator(mode="after")
    def validate_entity_integrity(self) -> EntitySchema:
        """Validate unique field names and exactly one primary key."""
        # Unique field names
        seen: set[str] = set()
        for f in self.fields:
            if f.name in seen:
                raise ValueError(f"Entity '{self.name}' has duplicate field name '{f.name}'")
            seen.add(f.name)

        # Exactly one primary key
        pk_fields = [f for f in self.fields if f.primary_key]
        if len(pk_fields) == 0:
            raise ValueError(f"Entity '{self.name}' must have exactly one primary key field")
        if len(pk_fields) > 1:
            pk_names = [f.name for f in pk_fields]
            raise ValueError(f"Entity '{self.name}' has multiple primary key fields: {pk_names}")
        return self
