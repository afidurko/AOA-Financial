# Workloop dependency upgrade pipeline

Periodic refresh of Python dependencies using the workloop **UpgradeStage**
logic, without running the full discover→merge cycle.

## Command

```bash
# Safe check (default for loop task — verify only, no pip upgrade):
aoa tasks run workloop-upgrade

# Actually upgrade dev+web extras then reverify:
aoa workloop upgrade

# Explicit dry-run:
aoa workloop upgrade --dry-run
```

Pipeline: **baseline verify** (ruff + pytest) → **pip install -e ".[dev,web]" --upgrade`** → **reverify**.

## Loop automation

| Task | When | Upgrades? |
|------|------|-----------|
| `aoa tasks run workloop-upgrade` | Weekly cron / after merge batch | No (`AOA_WORKLOOP_UPGRADE_DRY_RUN=true` default) |
| `aoa workloop upgrade` | Manual or post-L2 when deps stale | Yes |

Example cron (Sundays 12:00 UTC):

```cron
0 12 * * 0 cd /path/to/AOA-Financial && pip install -e ".[dev,web]" -q && aoa workloop upgrade >> logs/workloop-upgrade.log 2>&1
```

## Workloop full cycle

The full `aoa workloop run` still runs upgrade between `verify` and `reverify` after
Aaron-approved code changes. This command is for **dependency-only** maintenance.

Related: [loop-automation-schedule.md](loop-automation-schedule.md) · `src/aoa/workloop/upgrade.py`
