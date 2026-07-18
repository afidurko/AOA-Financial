"""Load and maintain the brain/ second-brain workspace."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

_REQUIRED = (
    "_CLAUDE.md",
    "README.md",
    "spine/ATTL.md",
    "spine/Algorithms.md",
    "spine/Team-Mesh.md",
    "mesh/index.yaml",
    "mesh/repos.yaml",
    "captures",
    "decisions",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_brain_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path.cwd()
    return root / "brain"


def ensure_brain_workspace(repo_root: Path | None = None) -> Path:
    """Ensure brain/ skeleton exists; return brain root path."""
    brain = default_brain_root(repo_root)
    (brain / "captures").mkdir(parents=True, exist_ok=True)
    (brain / "decisions").mkdir(parents=True, exist_ok=True)
    (brain / "spine").mkdir(parents=True, exist_ok=True)
    (brain / "mesh").mkdir(parents=True, exist_ok=True)
    return brain


@dataclass
class BrainStore:
    """Read/write mesh graph and captures under brain/."""

    root: Path
    mesh: dict[str, Any] = field(default_factory=dict)
    repos: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def open(cls, repo_root: Path | None = None) -> BrainStore:
        brain = ensure_brain_workspace(repo_root)
        store = cls(root=brain)
        store.reload()
        return store

    def reload(self) -> None:
        self.mesh = _load_yaml(self.root / "mesh" / "index.yaml")
        self.repos = _load_yaml(self.root / "mesh" / "repos.yaml")

    @property
    def mode(self) -> str:
        return str(self.mesh.get("mode") or "auto-12")

    @property
    def members(self) -> list[dict[str, Any]]:
        return list(self.mesh.get("members") or [])

    @property
    def algorithms(self) -> list[dict[str, Any]]:
        return list(self.mesh.get("algorithms") or [])

    def member_names(self) -> list[str]:
        return [str(m.get("name", "")) for m in self.members if m.get("name")]

    def stats(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "mode": self.mode,
            "members": len(self.members),
            "algorithms": len(self.algorithms),
            "spines": len(self.mesh.get("spines") or []),
            "repos": len(self.repos.get("repos") or []),
            "required_ok": self.required_paths_ok(),
        }

    def required_paths_ok(self) -> bool:
        for rel in _REQUIRED:
            path = self.root / rel
            if rel in {"captures", "decisions"}:
                if not path.is_dir():
                    return False
            elif not path.is_file():
                return False
        return True

    def write_capture(self, title: str, body: str, *, critical: bool = False) -> Path:
        ensure_brain_workspace(self.root.parent)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        prefix = "critical" if critical else "run"
        path = self.root / "captures" / f"{prefix}-{stamp}-{_slug(title)}.md"
        tags = "[capture, critical]" if critical else "[capture]"
        path.write_text(
            f"---\ntags: {tags}\ncreated: {_utc_now()}\n---\n\n# {title}\n\n{body.strip()}\n",
            encoding="utf-8",
        )
        return path

    def set_mode(self, mode: str) -> None:
        self.mesh["mode"] = mode
        self.mesh["updated_at"] = _utc_now()
        _dump_yaml(self.root / "mesh" / "index.yaml", self.mesh)

    def to_context(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "members": self.member_names(),
            "algorithms": [a.get("id") for a in self.algorithms],
            "repos": [r.get("name") for r in (self.repos.get("repos") or [])],
            "stats": self.stats(),
        }


def _slug(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in text.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:48] or "note"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    # Minimal fallback: not expected in normal installs
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        path.write_text(
            yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    else:  # pragma: no cover
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
