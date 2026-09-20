"""Companion workspace mesh — sibling tools linked to AOA Financial.

Surfaces optional workspaces (OpenStock, QM, VisualHFT, hftbacktest,
antd-mobile) for ``aoa workspaces status`` and dashboard / doctor links.
Never starts those processes and never places orders.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aoa.config import Config
from aoa.visualhft.probe import FORK_URL as VISUALHFT_FORK
from aoa.visualhft.probe import HOMEPAGE as VISUALHFT_HOME
from aoa.visualhft.probe import probe_status as visualhft_probe

HFTBACKTEST_URL = "https://github.com/afidurko/hftbacktest"
ANTD_MOBILE_FORK = "https://github.com/afidurko/ant-design-mobile"
ANTD_MOBILE_HOME = "https://mobile.ant.design"


@dataclass(frozen=True)
class WorkspaceInfo:
    """One companion workspace status row."""

    id: str
    title: str
    role: str
    linked: bool
    url: str
    local_path: str
    present: bool
    docs: str
    setup: str
    offline_only: bool
    never_live: bool
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sibling(name: str, env_key: str) -> tuple[str, bool]:
    raw = os.environ.get(env_key, "").strip()
    path = Path(raw) if raw else _repo_root() / name
    present = path.is_dir() and ((path / ".git").exists() or (path / "README.md").exists())
    return str(path), present


def _hft_detail() -> dict[str, Any]:
    """Probe optional hftbacktest extra + vendored orderbook lane."""
    try:
        from aoa.hftbacktest import HAS_HFTBACKTEST
        from aoa.hftbacktest import probe_status as probe_hft

        hft = probe_hft()
        hft_installed = bool(HAS_HFTBACKTEST and hft.get("installed"))
    except ImportError:
        hft = {
            "installed": False,
            "hint": 'pip install -e ".[hftbacktest]"',
            "upstream": HFTBACKTEST_URL,
            "offline_only": True,
        }
        hft_installed = False

    try:
        from aoa.orderbook import probe_status as probe_book

        book = probe_book()
    except ImportError:
        book = {"installed": False, "ok": False, "offline_only": True}

    return {
        "installed": hft_installed or bool(book.get("ok")),
        "hftbacktest": hft,
        "orderbook": book,
    }


def probe_workspaces(cfg: Config | None = None) -> list[WorkspaceInfo]:
    """Return status for each companion workspace."""
    cfg = cfg or Config.from_env(load_dotenv=False)
    vh_probe = visualhft_probe()
    hft = _hft_detail()
    os_path, os_ok = _sibling("OpenStock", "OPENSTOCK_DIR")
    qm_path, qm_ok = _sibling("qm", "QM_DIR")
    vh_path, vh_ok = _sibling("VisualHFT", "VISUALHFT_DIR")
    hft_path, hft_ok = _sibling("hftbacktest", "HFTBACKTEST_DIR")
    adm_path, adm_ok = _sibling("ant-design-mobile", "ANTD_MOBILE_DIR")

    return [
        WorkspaceInfo(
            id="openstock",
            title="OpenStock",
            role="Market UI / watchlists (sibling Next.js app)",
            linked=bool(cfg.openstock_url),
            url=cfg.openstock_url,
            local_path=os_path,
            present=os_ok,
            docs="docs/how-to/openstock-integration.md",
            setup="scripts/openstock-setup.sh",
            offline_only=False,
            never_live=True,
            detail={},
        ),
        WorkspaceInfo(
            id="qm",
            title="QM",
            role="Multiplayer agent harness (Slack + web)",
            linked=bool(cfg.qm_url),
            url=cfg.qm_url,
            local_path=qm_path,
            present=qm_ok,
            docs="docs/how-to/qm-integration.md",
            setup="scripts/qm-setup.sh",
            offline_only=False,
            never_live=True,
            detail={},
        ),
        WorkspaceInfo(
            id="visualhft",
            title="VisualHFT",
            role="Live L2 microstructure desktop + Python study ports",
            linked=bool(cfg.visualhft_url),
            url=cfg.visualhft_url,
            local_path=vh_path,
            present=vh_ok,
            docs="docs/how-to/visualhft-integration.md",
            setup="scripts/visualhft-setup.sh",
            offline_only=True,
            never_live=True,
            detail={
                "homepage": VISUALHFT_HOME,
                "fork": VISUALHFT_FORK,
                "python_lane": vh_probe,
                "rest_trigger_hint": (
                    "Point VisualHFT REST actions at AOA_CUSTOM_APP_WEBHOOK_URL "
                    "(alerts only — never auto-executes trades)"
                ),
            },
        ),
        WorkspaceInfo(
            id="hftbacktest",
            title="hftbacktest",
            role="Optional tick L2/L3 engine + vendored orderbook (offline)",
            linked=bool(hft.get("installed")),
            url=HFTBACKTEST_URL,
            local_path=hft_path,
            present=hft_ok or bool((hft.get("orderbook") or {}).get("ok")),
            docs="docs/how-to/hftbacktest-integration.md",
            setup='pip install -e ".[hftbacktest]"  # orderbook is vendored',
            offline_only=True,
            never_live=True,
            detail=hft,
        ),
        WorkspaceInfo(
            id="antd-mobile",
            title="ant-design-mobile",
            role="Mobile UI kit + built-in /m phone shell",
            linked=bool(cfg.antd_mobile_url),
            url=cfg.antd_mobile_url,
            local_path=adm_path,
            present=adm_ok,
            docs="docs/how-to/antd-mobile-integration.md",
            setup="scripts/antd-mobile-setup.sh",
            offline_only=False,
            never_live=True,
            detail={
                "homepage": ANTD_MOBILE_HOME,
                "fork": ANTD_MOBILE_FORK,
                "mobile_path": "/m",
                "hint": "aoa serve → open /m on phone (Tailscale or LAN)",
            },
        ),
    ]


def workspaces_report(cfg: Config | None = None) -> dict[str, Any]:
    """JSON-serializable mesh summary for CLI / API."""
    rows = probe_workspaces(cfg)
    return {
        "workspaces": [w.to_dict() for w in rows],
        "count": len(rows),
        "linked": sum(1 for w in rows if w.linked),
        "present": sum(1 for w in rows if w.present),
        "never_live": True,
        "hint": "aoa workspaces status --json",
    }
