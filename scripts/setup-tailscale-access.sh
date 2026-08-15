#!/usr/bin/env bash
# Install Tailscale (if needed) and print the private URL for the AOA dashboard.
# Safe default: Tailscale tailnet only (no public internet exposure).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOA_ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"
LAUNCHAGENT_PLIST="$HOME/Library/LaunchAgents/com.aoa.serve.plist"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

usage() {
  cat <<EOF
Usage: ./scripts/setup-tailscale-access.sh [--install-only|--print-url]

Ensures AOA_WEB_HOST=0.0.0.0 (reachable on your tailnet) and prints dashboard URLs.
Install Tailscale on each device that should reach the dashboard (Mac, iPhone, iPad, etc.).
EOF
}

ensure_web_bind() {
  local host
  host="$(env_read AOA_WEB_HOST "$AOA_ENV_FILE")"
  if [[ -z "$host" || "$host" == "127.0.0.1" || "$host" == "localhost" ]]; then
    [[ -f "$AOA_ENV_FILE" ]] || cp "$ROOT/.env.example" "$AOA_ENV_FILE" 2>/dev/null || true
    env_upsert AOA_WEB_HOST "0.0.0.0" "$AOA_ENV_FILE"
    echo "Set AOA_WEB_HOST=0.0.0.0 in $AOA_ENV_FILE (required for tailnet access)."
    # A running dashboard keeps the old bind address until reloaded.
    if [[ -f "$LAUNCHAGENT_PLIST" ]]; then
      "$ROOT/scripts/install-aoa-launchagent.sh" --reload 2>/dev/null || true
    fi
  else
    echo "AOA_WEB_HOST=${host} (OK for tailnet access)."
  fi
}

install_tailscale_macos() {
  if command -v tailscale >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v brew >/dev/null 2>&1; then
    echo "Install Homebrew first, or download Tailscale from https://tailscale.com/download" >&2
    exit 1
  fi
  echo "Installing Tailscale via Homebrew…"
  brew install --cask tailscale
  echo ""
  echo "Open the Tailscale app from Applications, sign in, then re-run this script."
  open -a Tailscale 2>/dev/null || true
  exit 0
}

install_tailscale_linux() {
  if command -v tailscale >/dev/null 2>&1; then
    return 0
  fi
  cat >&2 <<EOF
Tailscale CLI not found. Install from https://tailscale.com/download/linux
Then: sudo tailscale up
Re-run: ./scripts/setup-tailscale-access.sh
EOF
  exit 1
}

ensure_tailscale() {
  case "$(uname -s)" in
    Darwin) install_tailscale_macos ;;
    Linux) install_tailscale_linux ;;
    *)
      echo "Unsupported OS for auto-install. Install Tailscale manually: https://tailscale.com/download" >&2
      exit 1
      ;;
  esac
}

tailscale_ready() {
  if ! command -v tailscale >/dev/null 2>&1; then
    return 1
  fi
  tailscale status >/dev/null 2>&1
}

print_urls() {
  local port ip dns_name
  port="$(env_read AOA_WEB_PORT "$AOA_ENV_FILE")"
  port="${port:-8080}"

  echo ""
  echo "== AOA dashboard URLs =="
  echo "Local:  http://127.0.0.1:${port}/"
  echo "Health: http://127.0.0.1:${port}/health"

  if ! tailscale_ready; then
    echo ""
    echo "Tailscale is not connected yet."
    echo "  1. Open Tailscale and sign in (same account on phone + Mac)"
    echo "  2. Re-run: ./scripts/setup-tailscale-access.sh --print-url"
    return 0
  fi

  ip="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  dns_name="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Self",{}).get("DNSName","").rstrip("."))' 2>/dev/null || true)"

  echo ""
  if [[ -n "$ip" ]]; then
    echo "Tailscale IP:  http://${ip}:${port}/"
  fi
  if [[ -n "$dns_name" ]]; then
    echo "MagicDNS:    http://${dns_name}:${port}/"
  fi
  echo ""
  echo "Install Tailscale on your phone, sign in to the same account, open the URL above."
  echo "Security: URLs are private to your tailnet — not on the public internet."
  echo ""
  echo "If the dashboard was already running, reload the LaunchAgent:"
  echo "  ./scripts/install-aoa-launchagent.sh --reload"
}

case "${1:-}" in
  --install-only)
    ensure_tailscale
    ;;
  --print-url)
    ensure_web_bind
    print_urls
    ;;
  -h|--help)
    usage
    ;;
  "")
    ensure_web_bind
    if ! command -v tailscale >/dev/null 2>&1; then
      ensure_tailscale
    fi
    print_urls
    ;;
  *)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 1
    ;;
esac
