#!/usr/bin/env bash
# Alpaca + AOA one-time setup helper.
# Runs checks and prints only the steps that need a human (browser login, API keys).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok() { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!${NC} %s\n" "$*"; }
need() { printf "${RED}→ YOU:${NC} %s\n" "$*"; }

echo "=== AOA Financial — setup helper ==="
echo

# --- .env scaffold ---
if [[ ! -f .env ]]; then
  cp .env.example .env
  ok "Created .env from .env.example"
else
  ok ".env exists"
fi

# --- Python package ---
if ! python3 -c "import aoa" 2>/dev/null; then
  need "Run: pip install -e \".[dev]\""
else
  ok "Python package aoa importable"
fi

# --- Anthropic ---
if grep -q '^ANTHROPIC_API_KEY=sk-' .env 2>/dev/null; then
  ok "ANTHROPIC_API_KEY looks set in .env"
else
  need "Edit .env — set ANTHROPIC_API_KEY=sk-ant-... (from console.anthropic.com)"
fi

# --- Alpaca CLI ---
ALPACA_BIN=""
if command -v alpaca >/dev/null 2>&1; then
  ALPACA_BIN="alpaca"
elif [[ -x "$HOME/go/bin/alpaca" ]]; then
  ALPACA_BIN="$HOME/go/bin/alpaca"
  export PATH="$HOME/go/bin:$PATH"
fi

if [[ -z "$ALPACA_BIN" ]]; then
  warn "Alpaca CLI not found — installing via go..."
  if command -v go >/dev/null 2>&1; then
    go install github.com/alpacahq/cli/cmd/alpaca@latest
    export PATH="$HOME/go/bin:$PATH"
    ALPACA_BIN="$HOME/go/bin/alpaca"
    ok "Installed Alpaca CLI ($("$ALPACA_BIN" version 2>/dev/null || echo unknown))"
  else
    need "Install Go, then run: go install github.com/alpacahq/cli/cmd/alpaca@latest"
  fi
else
  ok "Alpaca CLI found ($("$ALPACA_BIN" version 2>/dev/null || echo unknown))"
fi

# --- Alpaca credentials ---
PROFILE_DIR="${ALPACA_CONFIG_DIR:-$HOME/.config/alpaca}/profiles"
HAS_CLI_PROFILE=false
if [[ -d "$PROFILE_DIR" ]] && ls "$PROFILE_DIR"/*.yaml >/dev/null 2>&1; then
  HAS_CLI_PROFILE=true
  ok "Alpaca CLI profile(s) in $PROFILE_DIR"
fi

HAS_ENV_KEYS=false
if grep -qE '^ALPACA_API_KEY_ID=PK' .env 2>/dev/null; then
  HAS_ENV_KEYS=true
  ok "ALPACA_API_KEY_ID looks set in .env"
fi

if [[ "$HAS_CLI_PROFILE" == false && "$HAS_ENV_KEYS" == false ]]; then
  echo
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Alpaca login — pick ONE method (paper trading is default)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo
  need "EASIEST — browser OAuth (paper):  alpaca profile login"
  echo "       Opens Alpaca in your browser. Sign in and approve access."
  echo "       AOA will read ~/.config/alpaca/profiles/paper.yaml automatically."
  echo
  need "OR — paste API keys:  alpaca profile login --api-key"
  echo "       Use keys from app.alpaca.markets → Paper → API Keys (PK... + secret)."
  echo "       Then optionally copy into .env as ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY."
  echo
fi

# --- Doctor ---
echo
echo "=== Running checks ==="
if python3 -m aoa.cli doctor --offline; then
  ok "Offline config OK"
else
  warn "Offline config has problems (see above)"
fi

if [[ "$HAS_CLI_PROFILE" == true || "$HAS_ENV_KEYS" == true ]]; then
  echo
  if python3 -m aoa.cli doctor; then
    ok "Live Alpaca + LLM connectivity OK — you are ready to run aoa run"
  else
    warn "Live check failed — re-run alpaca profile login or fix .env keys"
    if [[ -n "$ALPACA_BIN" ]]; then
      "$ALPACA_BIN" doctor 2>/dev/null || true
    fi
  fi
else
  warn "Skipping live connectivity until Alpaca login completes"
fi

echo
echo "Full checklist: SETUP-AWAITING-YOU.md"
echo "When done: python3 -m aoa.cli doctor && python3 -m aoa.cli run"
