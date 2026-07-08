#!/usr/bin/env bash
# Deprecated wrapper — prefer: aoa activate  (or aoa loop / aoa serve for auto-activate)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

if ! python3 -c "import aoa" 2>/dev/null; then
  echo "→ Run first: pip install -e \".[dev,web,openai]\""
  exit 1
fi

export AOA_PROFILE="${AOA_PROFILE:-paper-dry}"
exec python3 -m aoa.cli activate "$@"
