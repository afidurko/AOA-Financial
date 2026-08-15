#!/usr/bin/env bash
# One command: auto-start aoa serve at login + Tailscale remote dashboard URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== AOA always-on setup (LaunchAgent + Tailscale) =="
echo ""

"$ROOT/scripts/install-aoa-launchagent.sh"
echo ""
"$ROOT/scripts/setup-tailscale-access.sh"

echo ""
echo "== Always-on ready =="
echo "Dashboard survives logout/reboot (LaunchAgent)."
echo "Open the Tailscale URL from any device on your tailnet."
