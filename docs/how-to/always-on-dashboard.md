# Always-on dashboard (LaunchAgent + Tailscale)

Keep the AOA web dashboard running on your Mac after reboot, and open it from
your phone or other machines over a **private** Tailscale network.

## Prerequisites

1. Python 3.10+ venv with AOA installed:

```bash
cd ~/Documents/AOA-Financial
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"
```

2. `.env` configured (API keys, OpenD, etc.) — see [fresh-clone.md](fresh-clone.md).

3. **OpenD** (Moomoo) running on the Mac when you need live broker data.

## One command (recommended)

```bash
./scripts/setup-always-on.sh
```

This:

1. Installs a **LaunchAgent** so `aoa serve` starts at login and restarts if it crashes
2. Ensures `AOA_WEB_HOST=0.0.0.0` in `.env` (binds on all interfaces for tailnet access)
3. Installs **Tailscale** via Homebrew if missing (macOS)
4. Prints local and Tailscale dashboard URLs

## Step by step

### LaunchAgent only (local always-on)

```bash
./scripts/install-aoa-launchagent.sh
```

| Command | Purpose |
|---------|---------|
| `./scripts/install-aoa-launchagent.sh --status` | Check agent state |
| `./scripts/install-aoa-launchagent.sh --reload` | Reload after `.env` changes |
| `./scripts/install-aoa-launchagent.sh --uninstall` | Remove auto-start |

Logs:

- `~/Library/Logs/aoa-serve.log`
- `~/Library/Logs/aoa-serve.err.log`

Local health check:

```bash
curl -sf http://127.0.0.1:8080/health && echo OK
```

### Tailscale only (remote URL)

```bash
./scripts/setup-tailscale-access.sh
```

On each device (Mac, iPhone, iPad):

1. Install [Tailscale](https://tailscale.com/download)
2. Sign in with the **same account**
3. Open the printed URL, e.g. `http://100.x.x.x:8080/` or MagicDNS hostname

Re-print URLs anytime:

```bash
./scripts/setup-tailscale-access.sh --print-url
```

## Architecture

```
┌──────────────── Mac (always on) ─────────────────┐
│  LaunchAgent → aoa serve :8080 (0.0.0.0)         │
│  OpenD (Moomoo) :11111                           │
│  Obsidian + AOA-Vault (optional Login Item)      │
└───────────────────────┬──────────────────────────┘
                        │ Tailscale tailnet (private)
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      iPhone         iPad         laptop
   http://100.x…:8080
```

Trading execution and OpenD stay on the Mac. Tailscale only exposes the
dashboard HTTP port to **your** devices — not the public internet.

## Security notes

- Default Tailscale setup is **tailnet-only**. No port forwarding required.
- The AOA dashboard has **no built-in login**. Anyone on your tailnet who knows
  the URL can view it. Restrict tailnet membership in the Tailscale admin console.
- Do not expose port 8080 on your public router unless you add separate auth.

## Linux / VPS

Use systemd or Docker instead of LaunchAgent:

```bash
docker compose up -d web
# or
sudo cp deploy/aoa-web.service /etc/systemd/system/
sudo systemctl enable --now aoa-web.service
```

Install Tailscale on the server, then `./scripts/setup-tailscale-access.sh --print-url`.

**Note:** Moomoo OpenD normally runs on your Mac, not a cloud VPS. Remote
dashboard viewing works; live Moomoo trading from a VPS requires OpenD reachable
from that host (unusual).

## Related

- [fresh-clone.md](fresh-clone.md) — first-time install
- [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md) — vault + MCP
- [README.md](../../README.md#docker-deployment) — Docker daemon mode
