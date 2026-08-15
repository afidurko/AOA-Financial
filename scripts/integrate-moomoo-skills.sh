#!/usr/bin/env bash
# Confirm vendored Moomoo OpenD skills are present and index them for the vault mesh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh" 2>/dev/null || true
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh" 2>/dev/null || true

fail=0
for rel in \
  .cursor/skills/moomooapi/SKILL.md \
  .cursor/skills/install-moomoo-opend/SKILL.md \
  .claude/skills/moomooapi/SKILL.md \
  .claude/skills/install-moomoo-opend/SKILL.md
do
  if [[ -f "$ROOT/$rel" ]]; then
    echo "  ✓ $rel"
  else
    echo "  ✗ missing $rel"
    fail=$((fail + 1))
  fi
done

VAULT_DIR=""
if declare -F resolve_vault_dir >/dev/null 2>&1; then
  VAULT_DIR="$(resolve_vault_dir "$ROOT" 2>/dev/null || true)"
fi
if [[ -n "${VAULT_DIR}" && -d "$VAULT_DIR" ]]; then
  mkdir -p "$VAULT_DIR/Knowledge"
  cat >"$VAULT_DIR/Knowledge/Moomoo OpenD Skills Reference.md" <<'EOF'
---
tags: [type/reference, moomoo, skills]
---

# Moomoo OpenD Skills

Vendored in AOA-Financial from
https://openapi.moomoo.com/skills/opend-skills.zip

| Skill | Path | Use |
|-------|------|-----|
| `moomooapi` | `.cursor/skills/moomooapi/` | Quotes, orders, options, crypto via OpenD |
| `install-moomoo-opend` | `.cursor/skills/install-moomoo-opend/` | Install/upgrade OpenD + `moomoo-api` |

Defaults: paper trading (`TrdEnv.SIMULATE`), OpenD at `127.0.0.1:11111`.

See also: `docs/how-to/moomoo-setup.md`, `.cursor/skills/MOOMOO-SKILLS.md`.
EOF
  echo "  ✓ vault Knowledge/Moomoo OpenD Skills Reference.md"
fi

"$ROOT/scripts/write-aoa-workspace.sh" >/dev/null
echo "  ✓ AOA.code-workspace refreshed"

if [[ "$fail" -gt 0 ]]; then
  echo "Moomoo skills incomplete — re-run from .cursor/skills/MOOMOO-SKILLS.md"
  exit 1
fi
echo "Moomoo skills OK."
