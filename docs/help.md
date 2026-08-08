# Help — related content

Companion repos and docs that help operate AOA Financial. None of these are
vendored into this tree; clone them beside the project (or use your fork) when
you need them.

## Agent harness (Slack + web)

| Resource | Role |
|----------|------|
| **[qm](https://github.com/afidurko/qm)** | Multiplayer agent harness for work — personal and shared scopes, Slack + web UI, crons, sandbox, and harness-agnostic agent loops (Pi, OpenCode, Codex, Claude Code). Upstream: [yc-software/qm](https://github.com/yc-software/qm). |

Use QM when you want Slack/channel collaboration, scoped memory, and a deployable
agent core around AOA (or other tools) without tying the deployment to one vendor
harness. Deployment and security posture live in a separate org deployment repo;
see the QM README for `qm init` and `SECURITY.md`.

```bash
git clone https://github.com/afidurko/qm.git
# or upstream: git clone https://github.com/yc-software/qm.git
```

## Market UI

| Resource | Role |
|----------|------|
| **[OpenStock](https://github.com/Open-Dev-Society/OpenStock)** | Sibling market dashboard (charts, watchlists). Link from the AOA header via `AOA_OPENSTOCK_URL`. |

Setup: [how-to/openstock-integration.md](how-to/openstock-integration.md).

## Engineering loop

| Resource | Role |
|----------|------|
| **[loop-engineering](https://github.com/afidurko/loop-engineering)** | Scaffold for daily triage, repair queue, and maker/checker skills used by `LOOP.md` / `aoa repair`. |

In-repo: [LOOP.md](../LOOP.md), [safety.md](safety.md), [how-to/fresh-clone.md](how-to/fresh-clone.md).

## Quant reference

| Resource | Role |
|----------|------|
| **[Finance](https://github.com/shashankvemuri/Finance)** | Reference library of quantitative finance Python programs (used in Tom’s knowledge context). |

## Local model runtime (optional)

| Resource | Role |
|----------|------|
| **[waste](https://github.com/afidurko/waste)** | Weight-Aware Streaming Tensor Engine — run large models (e.g. Kimi K3) by streaming weights from NVMe. Upstream: [sqliteai/waste](https://github.com/sqliteai/waste). |

Useful when you want a local OpenAI-compatible inference path for agents without
fitting the full model in RAM.
