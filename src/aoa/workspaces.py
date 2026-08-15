"""Companion workspace mesh — sibling tools linked to AOA Financial.

Surfaces optional workspaces (OpenStock, QM, VisualHFT, hftbacktest) for
``aoa workspaces status`` and dashboard / doctor links. Never starts those
processes and never places orders.
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
    # src/aoa/workspaces.py → repo root
    return Path(__file__).resolve().parents[2]


def _sibling_present(name: str, *, env_key: str) -> tuple[str, bool]:
    raw = os.environ.get(env_key, "").strip()
    path = Path(raw) if raw else _repo_root() / name
    present = path.is_dir() and ((path / ".git").exists() or (path / "README.md").exists())
    return str(path), present


def _hftbacktest_detail() -> dict[str, Any]:
    try:
        from aoa.hftbacktest import HAS_HFTBACKTEST, probe_status

        status = probe_status()
        return {
            "installed": bool(HAS_HFTBACKTEST and status.get("installed")),
            "probe": status,
        }
    except ImportError:
        return {
            "installed": False,
            "probe": {
                "installed": False,
                "hint": 'pip install -e ".[hftbacktest]" (optional PR/extra)',
                "upstream": "https://github.com/afidurko/hftbacktest",
                "offline_only": True,
            },
        }


def probe_workspaces(cfg: Config | None = None) -> list[WorkspaceInfo]:
    """Return status for each companion workspace."""
    cfg = cfg or Config.from_env(load_dotenv=False)

    os_path, os_present = _sibling_present("OpenStock", env_key="OPENSTOCK_DIR")
    qm_path, qm_present = _sibling_present("qm", env_key="QM_DIR")
    vh_path, vh_present = _sibling_present("VisualHFT", env_key="VISUALHFT_DIR")
    hft_path, hft_present = _sibling_present("hftbacktest", env_key="HFTBACKTEST_DIR")

    vh_status = visualhft_probe()
    visualhft_url = (cfg.visualhft_url or os.environ.get("AOA_VISUALHFT_URL", "")).strip()
    if not visualhft_url:
        visualhft_url = VISUALHFT_FORK

    hft_detail = _hftbacktest_detail()

    return [
        WorkspaceInfo(
            id="openstock",
            title="OpenStock",
            role="Market UI / watchlists (sibling Next.js app)",
            linked=bool(cfg.openstock_url),
            url=cfg.openstock_url,
            local_path=os_path,
            present=os_present,
            docs="docs/how-to/openstock-integration.md",
            setup="scripts/openstock-setup.sh",
            offline_only=False,
            never_live=True,
            detail={"header_link": bool(cfg.openstock_url)},
        ),
        WorkspaceInfo(
            id="qm",
            title="QM",
            role="Multiplayer agent harness (Slack + web)",
            linked=bool(cfg.qm_url),
            url=cfg.qm_url,
            local_path=qm_path,
            present=qm_present,
            docs="docs/how-to/qm-integration.md",
            setup="scripts/qm-setup.sh",
            offline_only=False,
            never_live=True,
            detail={"header_link": bool(cfg.qm_url)},
        ),
        WorkspaceInfo(
            id="visualhft",
            title="VisualHFT",
            role="Live L2 microstructure desktop + Python study ports",
            linked=bool((cfg.visualhft_url or "").strip()),
            url=visualhft_url,
            local_path=vh_path,
            present=vh_present,
            docs="docs/how-to/visualhft-integration.md",
            setup="scripts/visualhft-setup.sh",
            offline_only=True,
            never_live=True,
            detail={
                "homepage": VISUALHFT_HOME,
                "fork": VISUALHFT_FORK,
                "python_lane": vh_status,
                "rest_trigger_hint": (
                    "Point VisualHFT REST actions at AOA_CUSTOM_APP_WEBHOOK_URL "
                    "(alerts only — never auto-executes trades)"
                ),
            },
        ),
        WorkspaceInfo(
            id="hftbacktest",
            title="hftbacktest",
            role="Optional offline tick L2/L3 backtest engine",
            linked=bool(hft_detail.get("installed")),
            url="https://github.com/afidurko/hftbacktest",
            local_path=hft_path,
            present=hft_present,
            docs="docs/how-to/hftbacktest-integration.md",
            setup='pip install -e ".[hftbacktest]"',
            offline_only=True,
            never_live=True,
            detail=hft_detail,
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
