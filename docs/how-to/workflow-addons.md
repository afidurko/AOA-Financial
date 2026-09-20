# Workflow & integration add-ons

Suggestions after a full retest battery. None of these are required for
trading paper/dry-run; they compound agent + human throughput.

## Already landed (use these)

| Add-on | How |
|--------|-----|
| Open-quant stress scales | `aoa openquant stress --scale smoke\|million\|billion\|trillion` |
| Loop task | `aoa tasks run openquant-stress` (smoke; override with `AOA_OPENQUANT_STRESS_SCALE`) |
| Workloop upgrade dry-run | `aoa tasks run workloop-upgrade` |
| Multi-root workspaces | `./scripts/knowledge-stack-setup.sh` → open `AOA.code-workspace` |
| External repo mesh | `./scripts/connect-workspace.sh /path/to/other/repo` |
| ATTL auto-12 | `aoa attl run` after triage |
| Offline doctor | `aoa doctor --offline` in CI / cloud without OpenD |

## Recommended next integrations

1. **Weekly open-quant million stress** — cron or Cursor Automation:
   `aoa openquant stress --scale million` after `aoa tasks run verify`.
2. **Cursor Environment builds** — save `.cursor/environment.json` and enable
   builds so agents skip cold `pip install`.
3. **Integrity Ten + Needs Attention** — queue Kai-critical findings to Cursor
   Needs Attention / dashboard approve-reject (see open Integrity PRs if any).
4. **iPhone push on team-health CRITICAL** — set `AOA_NTFY_TOPIC` or Pushover;
   Aaron already emits structured alerts.
5. **Task-chain auto-advance after L2 merge** — Automation B ends with
   `aoa tasks chain advance --complete <id>` so the next backlog item is queued.
6. **Companion one-shot** — `aoa workspaces setup` (or document alias) wrapping
   knowledge-stack + qm + visualhft setup scripts.
7. **Paper profile split in cloud** — keep local `paper-dry` on Moomoo; cloud
   agents export `AOA_BROKER=alpaca` so doctor/team health are not OpenD-bound.
8. **Trillion-class overnight job** — `aoa openquant stress --scale trillion`
   (~3×10⁹ checks; ~hours). Full 10¹² only with `--iterations 1000000000000`.

## Human gates (unchanged)

- Rotate exposed API keys; set real `ANTHROPIC_API_KEY` for LLM swarm.
- Start Moomoo OpenD (or switch broker) before live paper trading cycles.
- Draft PRs still need human merge unless you explicitly authorize the agent.
