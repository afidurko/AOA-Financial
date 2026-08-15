---
tags: [decision, workspaces, workloop]
created: 2026-08-15T21:00:00Z
---

# Issues fixed + workspace mesh integration

## Context

Triage High Priority still listed workloop upgrade (upg-009) though chain
state claimed completion without `run_upgrade_pipeline` on main.
Knowledge-stack workspaces existed in docs but were not wired in this VM.
Paper-dry must stay Moomoo-first (OpenD local); Alpaca remains opt-in for
cloud/CI without OpenD (`AOA_BROKER=alpaca`) and for `profiles/paper.env`.

## Decision

1. Land workloop upgrade CLI + dry-run task (`aoa workloop upgrade`,
   `aoa tasks run workloop-upgrade`).
2. Keep `paper-dry` on `AOA_BROKER=moomoo`; `paper` may use Alpaca; Moomoo
   simulate orders via `moomoo-paper`.
3. Add optional `httpx2` for Starlette TestClient; web tests fall back to `httpx`.
4. Wire knowledge-stack + multi-root `AOA.code-workspace`; support connecting
   external repos via `scripts/connect-workspace.sh`.
5. Enrich `.cursor/environment.json` install with `attl init` + workspace writer.

## Follow-up (human)

- Rotate exposed API keys (upg-002).
- Save Cursor Cloud environment from proposed `environment.json`.
- Open `AOA.code-workspace` after local `./scripts/knowledge-stack-setup.sh`.
