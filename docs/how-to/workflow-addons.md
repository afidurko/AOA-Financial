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

## Mesh & security add-ons (2026-09-20 loop run)

Landed this run:

| Add-on | How |
|--------|-----|
| Neural endpoint mesh | `aoa mesh status\|sync\|recall` — unified graph + persistent run memory (`docs/design/neural-endpoint-mesh.md`) |
| ATTL memory feed | every `aoa attl run` reinforces mesh weights under `data/{env}/mesh/memory.json` |
| Loopback-by-default dashboard | `AOA_WEB_HOST` now defaults to `127.0.0.1`; keep `0.0.0.0` in `.env` for tailnet |
| Safe LoRA checkpoints | `torch.load(..., weights_only=True)` in `aoa.adapt.torch_lora` |
| LLM URL scheme gate | `AOA_LLM_BASE_URL` must be `http(s)://` |

Recommended next:

1. **Mesh health on the dashboard** — surface `aoa mesh status --json`
   (health, weakest nodes) as a web panel; alert via ntfy when health < 0.4.
2. **Feed ship/repair outcomes into mesh memory** — today only ATTL records;
   `ship proofread` and `repair gate` outcomes would sharpen node weights.
3. **Live endpoint probes** — optional `aoa mesh probe` reachability checks
   (OpenD, LLM, dashboard) recorded as mesh runs; keeps memory honest.
4. **Security scan automation** — weekly `bandit -r src -ll` + `pip-audit` in
   CI or a Cursor Automation; this run caught 4 fixable findings that way.
5. **Environment CVE hygiene** — upgrade `pyjwt`, `urllib3`, `setuptools`,
   `pip`, `wheel` in the cloud image (pip-audit flags known CVEs; none are
   project-pinned deps).
6. **hftbacktest lane in cloud** — `pip install -e ".[dev,web]"` skips the
   L2 replay lane (`aoa hft smoke` prints "not installed" and exits 0).
   Either add `hftbacktest` to `.cursor/environment.json` install or accept
   the silent skip; installing took ~20 s and the smoke passes.
7. **Flake watch** — nightly automation running the pytest suite 3×
   back-to-back; this run's 3× sweep was clean (568×3, zero flakes).
8. **Web API smoke task** — a `aoa tasks run web-smoke` step (TestClient →
   `/health`, `/api/config`) so tier1 exercises the dashboard wiring without
   booting uvicorn.

## Human gates (unchanged)

- Rotate exposed API keys; set real `ANTHROPIC_API_KEY` for LLM swarm.
- Start Moomoo OpenD (or switch broker) before live paper trading cycles.
- Draft PRs still need human merge unless you explicitly authorize the agent.
