#!/usr/bin/env bash
# Example cron entries for AOA loop preflight (no LLM).
# Install: review paths, then append to crontab -e
#
#   REPO=/path/to/AOA-Financial
#   bash scripts/install_loop_cron.example.sh --print

set -euo pipefail

REPO="${AOA_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${AOA_PYTHON:-python3}"

print_crontab() {
  cat <<EOF
# AOA-Financial loop preflight (deterministic — no agent tokens)
55 13 * * * cd ${REPO} && ${PY} -m pip install -e ".[dev]" -q && ${PY} -m aoa.cli tasks run tier1 >> ${REPO}/logs/loop-tier1.log 2>&1
0 15 * * * cd ${REPO} && ${PY} -m aoa.cli tasks run tier2-check >> ${REPO}/logs/loop-tier2-check.log 2>&1
EOF
}

case "${1:-}" in
  --print)
    print_crontab
    ;;
  *)
    echo "Usage: bash scripts/install_loop_cron.example.sh --print"
    echo "Copy output into crontab -e after setting AOA_REPO if needed."
    ;;
esac
