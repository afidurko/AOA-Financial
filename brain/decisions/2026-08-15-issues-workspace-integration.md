---
tags: [decision, workspaces, workloop]
created: 2026-08-15T21:00:00Z
---

# Issues fixed + workspace mesh integration

## Context

Triage High Priority still listed workloop upgrade (upg-009) though chain
state claimed completion without `run_upgrade_pipeline` on main. Paper
profiles still pointed at Moomoo OpenD, breaking cloud `aoa doctor`.
Knowledge-stack workspaces existed in docs but were not wired in this VM.

## Decision

1. Land workloop upgrade CLI + dry-run task (`aoa workloop upgrade`,
   `aoa tasks run workloop-upgrade`).
2. Default paper / paper-dry to `AOA_BROKER=alpaca` (Moomoo via
   `moomoo-paper` / live profiles).
3. Add `httpx2` + silence upstream `websockets.legacy` warning.
4. Run `knowledge-stack-setup` → multi-root `AOA.code-workspace` via
   `write-aoa-workspace.sh`; enrich `.cursor/environment.json` install
   with `attl init` + workspace writer; expand VS Code tasks.

## Follow-up (human)

- Rotate exposed API keys (upg-002).
- Save Cursor Cloud environment from proposed `environment.json`.
- Open `AOA.code-workspace` after local `./scripts/knowledge-stack-setup.sh`.
