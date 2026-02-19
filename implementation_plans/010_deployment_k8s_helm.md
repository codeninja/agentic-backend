# Implementation Plan 010: K8s/Helm Deployment Pipeline

> **Milestone**: 4 — Composition & Deployment
> **Tickets**: (New)

## Objective
Generate standardized Kubernetes manifests and Helm charts from the ASD. `ninjastack deploy` should take a project from local dev to a running K8s cluster with all polyglot engines provisioned.

## Requirements
- **ASD-driven deployment**: The deployment manifest is derived from the ASD — if you declared Postgres + Mongo + Neo4j, all three get provisioned.
- **Helm charts**: One chart per app, with dependency charts for infrastructure (databases, vector stores).
- **Docker image generation**: Auto-generate Dockerfiles for each app in `apps/`.
- **Environment management**: Dev, staging, production configs via Helm values.
- **CI/CD integration**: Generate GitHub Actions workflows for build → test → deploy.

## Generated Artifacts
- `infrastructure/helm/` — Helm chart with values per environment.
- `infrastructure/docker/` — Dockerfiles for each app.
- `infrastructure/k8s/` — Raw manifests (for non-Helm users).
- `.github/workflows/deploy.yml` — CI/CD pipeline.

## File Structure
```
libs/ninja-deploy/
├── pyproject.toml
├── src/ninja_deploy/
│   ├── __init__.py
│   ├── helm_generator.py     # ASD → Helm chart
│   ├── docker_generator.py   # ASD → Dockerfiles
│   ├── k8s_generator.py      # ASD → raw manifests
│   ├── ci_generator.py       # Generate GitHub Actions
│   └── templates/
│       ├── helm/
│       ├── docker/
│       └── github-actions/
└── tests/
```

## Acceptance Criteria
- [ ] Given an ASD declaring Postgres + Milvus, generate a Helm chart with both provisioned.
- [ ] Generated Dockerfiles build successfully for each app.
- [ ] `ninjastack deploy` runs `helm upgrade --install` against a target cluster.
- [ ] CI/CD workflow runs tests, builds images, and deploys on merge to main.

## Dependencies
- Plan 002 (ASD Core Models — infrastructure declarations)
- Plan 003 (Code Generation — deployment is a generation target)
- Plan 004 (Unified Persistence — connection config)
