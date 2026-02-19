# Implementation Plan 006: Data Tolerance & Boundary Layer (`libs/ninja-boundary`)

> **Milestone**: 3 — Polyglot Persistence & Graph-RAG
> **Tickets**: (New)

## Objective
Build the **Boundary Layer** that sits between raw data and the Pydantic models. Real-world databases are messy — this layer handles coercion, missing fields, schema drift, and progressive strictness.

## Requirements
- **Type coercion**: Gracefully handle common mismatches (int↔string, flexible timestamps, null vs empty string).
- **Missing field defaults**: Convention-based defaults when fields are absent (especially for schemaless stores like Mongo).
- **Schema drift detection**: Detect when incoming data no longer matches the ASD and log warnings.
- **Progressive strictness**: Start permissive, tighten rules as patterns are observed. Log all coercions for audit.
- **Pluggable validators**: Per-entity custom validation hooks that users can define.

## Architecture
```
Raw Data (from adapter) ──→ Boundary Layer ──→ Validated Pydantic Model
                                │
                          Coercion Log
                          Drift Alerts
```

## Key Components
- **Coercion Engine**: Type-aware casting with configurable strictness levels.
- **Default Resolver**: Convention-based defaults per field type.
- **Drift Detector**: Compare incoming data shapes against ASD expectations.
- **Audit Logger**: Structured log of every coercion and drift event.
- **Strictness Tuner**: Analyze coercion logs over time and recommend stricter rules.

## File Structure
```
libs/ninja-boundary/
├── pyproject.toml
├── src/ninja_boundary/
│   ├── __init__.py
│   ├── coercion.py           # Type coercion engine
│   ├── defaults.py           # Convention-based default resolver
│   ├── drift.py              # Schema drift detection
│   ├── audit.py              # Coercion audit logger
│   ├── tuner.py              # Progressive strictness recommendations
│   └── validators.py         # Pluggable per-entity validation hooks
└── tests/
```

## Acceptance Criteria
- [ ] A Mongo document with a string `"123"` in an int field is coerced successfully.
- [ ] A missing `created_at` field gets a sensible default.
- [ ] A new unexpected field in a Mongo document triggers a drift warning.
- [ ] Coercion audit log captures every transformation with before/after values.
- [ ] Strictness tuner can analyze logs and suggest rule tightening.

## Dependencies
- Plan 002 (ASD Core Models — field type definitions)
- Plan 004 (Unified Persistence — raw data source)
