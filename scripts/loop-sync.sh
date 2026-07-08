#!/usr/bin/env bash
# Sync the loop-engineering scaffold with upstream and audit readiness.
#
# AOA-Financial was scaffolded from afidurko/loop-engineering (upstream
# cobusgreyling/loop-engineering). This wrapper runs the upstream audit tools
# without ever overwriting AOA-specific extensions (the fable-repair skill, the
# Cursor skills under .cursor/skills/, or the AOA patterns in
# patterns/registry.yaml).
#
# Usage:
#   bash scripts/loop-sync.sh audit      # readiness score + suggestions (default)
#   bash scripts/loop-sync.sh cost       # daily-triage L1 token estimate
#   bash scripts/loop-sync.sh sync       # dry-run scaffold diff vs upstream
#
# Note: the upstream audit scans .grok/.claude/.codex skill folders. AOA keeps
# its skills under .cursor/skills/, so "missing skill" warnings are expected;
# rely on `python3 -m pytest tests/test_loop_scaffold.py` and
# `python3 -m aoa.cli team health` for the authoritative in-repo scaffold check.

set -euo pipefail

REPO="${AOA_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
cmd="${1:-audit}"

require_npx() {
  if ! command -v npx >/dev/null 2>&1; then
    echo "npx not found — install Node.js to run upstream loop-engineering tools." >&2
    exit 1
  fi
}

case "$cmd" in
  audit)
    require_npx
    npx -y @cobusgreyling/loop-audit@latest "$REPO" --suggest
    ;;
  cost)
    require_npx
    npx -y @cobusgreyling/loop-cost@latest --pattern daily-triage --level L1
    ;;
  sync)
    require_npx
    echo "Dry-run: comparing in-tree scaffold against upstream starters."
    echo "AOA extensions are never overwritten (.cursor/skills/, fable-repair, AOA patterns)."
    npx -y @cobusgreyling/loop-init@latest "$REPO" --pattern daily-triage --tool claude --dry-run
    ;;
  *)
    echo "Usage: bash scripts/loop-sync.sh [audit|cost|sync]" >&2
    exit 1
    ;;
esac
