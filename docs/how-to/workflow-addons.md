# Workflow & integration add-ons

Suggestions after a full retest battery. None of these are required for
trading paper/dry-run; they compound agent + human throughput.

## Already landed (use these)

| Add-on | How |
|--------|-----|
| Open-quant stress scales | `aoa openquant stress --scale smoke\|million\|billion\|trillion [--workers N]` |
| Loop task | `aoa tasks run openquant-stress` (smoke; `AOA_OPENQUANT_STRESS_SCALE`, `AOA_OPENQUANT_STRESS_ITERATIONS`) |
| Heavy-scale guard | billion/trillion in the loop task require `AOA_OPENQUANT_STRESS_ALLOW_HEAVY=1` |
| Symmetric-cov check | ERC / risk-contribution reject non-symmetric Σ |
| Ship conflict scan | `src`, `tests`, `scripts`, `docs`, `pyproject.toml`, `requirements.txt`, `loop-prompts.yaml` |
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
8. **Trillion-class overnight job** — `aoa openquant stress --scale trillion --workers 4`
   (3×10⁹ checks). Full 10¹² only with `--iterations 1000000000000`.
9. **NumPy / PyPy inverse-vol kernel** — shards + inlined pair math make 3×10⁹
   practical; a vectorized kernel is still needed for a literal 10¹² overnight.
10. **PSD covariance gate** — `_validate_cov` now requires symmetry; next is a
    cheap Cholesky / eigenvalue check so ERC cannot run on indefinite Σ.
11. **httpx fallback CI job** — install without `[web]` so `aoa.httpcompat`
    exercises the `httpx` (not `httpx2`) import path.
12. **Clone open-quant-live-book sibling** — `scripts/open-quant-live-book-setup.sh`
    so `aoa openquant status` reports `sibling_present: true` and mesh docs
    resolve locally.
13. **Conflict-scan pre-commit** — run the same `rg` as `aoa ship discover` on
    commit so leftover `<<<<<<<` never leave the laptop.
14. **Doctor news wiring** — replace `NullNewsFeed` on paper-dry once OpenD
    headlines are confirmed, so doctor stops warning on every offline run.

## Human gates (unchanged)

- Rotate exposed API keys; set real `ANTHROPIC_API_KEY` for LLM swarm.
- Start Moomoo OpenD (or switch broker) before live paper trading cycles.
- Draft PRs still need human merge unless you explicitly authorize the agent.
