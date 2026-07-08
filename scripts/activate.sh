#!/usr/bin/env bash
# One command after logging into Moomoo OpenD — activates broker + local LLM + verify.
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

export AOA_PROFILE="${AOA_PROFILE:-moomoo}"
exec python3 -m aoa.cli activate "$@"
