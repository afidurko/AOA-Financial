---
tags: [type/decision, workspaces, moomoo]
---

# Decision — mesh Moomoo skills into knowledge-stack workspaces

**Date:** 2026-08-15

## Decision

Treat Moomoo OpenD skills (`moomooapi`, `install-moomoo-opend`) as first-class
members of the AOA knowledge stack, alongside Obsidian / Spine companions.

## Consequences

1. `./scripts/knowledge-stack-setup.sh` verifies Moomoo skills and refreshes `AOA.code-workspace`.
2. `brain/mesh/repos.yaml` lists vendored Moomoo skill paths under `local:`.
3. Agents open multi-root workspaces via `AOA.code-workspace` when siblings exist.
4. Trading execution remains in AOA; Moomoo skills are the OpenAPI assistant layer.
