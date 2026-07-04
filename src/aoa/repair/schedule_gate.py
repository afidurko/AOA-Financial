"""Preflight gate for Tier 1 / Tier 2 loop automations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path


class GateAction(str, Enum):
    PAUSE = "pause"
    SKIP = "skip"
    TRIAGE_OK = "triage-ok"
    L1_ONLY = "l1-only"
    L2_ALLOWED = "l2-allowed"


@dataclass(frozen=True)
class LoopCaps:
    max_runs_per_day: int
    max_tokens_per_day: int


DEFAULT_CAPS: dict[str, LoopCaps] = {
    "daily-triage": LoopCaps(max_runs_per_day=2, max_tokens_per_day=100_000),
    "fable-repair": LoopCaps(max_runs_per_day=4, max_tokens_per_day=200_000),
}

_LOG_ROW = re.compile(
    r"^\|\s*(?P<ts>[^|]+)\|\s*(?P<loop>[^|]+)\|\s*(?P<level>[^|]+)\|\s*(?P<outcome>[^|]+)\|\s*(?P<notes>[^|]*)\|\s*$"
)
_TOKEN_EST = re.compile(r"tokens_estimate=(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class GateResult:
    action: GateAction
    reason: str
    paused: bool
    l2_automation_enabled: bool
    fixable_items: tuple[str, ...]
    runs_24h: dict[str, int]
    tokens_24h: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "paused": self.paused,
            "l2_automation_enabled": self.l2_automation_enabled,
            "fixable_items": list(self.fixable_items),
            "runs_24h": self.runs_24h,
            "tokens_24h": self.tokens_24h,
        }


def evaluate_gate(
    *,
    repo_root: Path,
    l2_automation_enabled: bool | None = None,
    now: datetime | None = None,
    mode: str = "full",
) -> GateResult:
    root = repo_root
    state_path = root / "STATE.md"
    log_path = root / "loop-run-log.md"
    queue_path = _default_queue_path(root)

    paused = is_paused(state_path)
    if l2_automation_enabled is None:
        l2_automation_enabled = l2_enabled_in_state(state_path)

    runs_24h = count_runs_by_loop(log_path, now=now)
    tokens_24h = sum_tokens_by_loop(log_path, now=now)
    fixable = fixable_queue_titles(queue_path)

    if paused:
        return GateResult(
            action=GateAction.PAUSE,
            reason="loop-pause-all is active in STATE.md",
            paused=True,
            l2_automation_enabled=l2_automation_enabled,
            fixable_items=fixable,
            runs_24h=runs_24h,
            tokens_24h=tokens_24h,
        )

    triage_caps = DEFAULT_CAPS["daily-triage"]
    repair_caps = DEFAULT_CAPS["fable-repair"]
    triage_runs = runs_24h.get("daily-triage", 0)
    repair_runs = runs_24h.get("fable-repair", 0)
    triage_tokens = tokens_24h.get("daily-triage", 0)
    repair_tokens = tokens_24h.get("fable-repair", 0)

    if mode in {"full", "triage"}:
        if triage_runs >= triage_caps.max_runs_per_day:
            return GateResult(
                action=GateAction.SKIP,
                reason="daily-triage run cap reached for last 24h",
                paused=False,
                l2_automation_enabled=l2_automation_enabled,
                fixable_items=fixable,
                runs_24h=runs_24h,
                tokens_24h=tokens_24h,
            )
        if triage_tokens >= int(triage_caps.max_tokens_per_day * 0.8):
            return GateResult(
                action=GateAction.SKIP,
                reason="daily-triage token budget ≥80%",
                paused=False,
                l2_automation_enabled=l2_automation_enabled,
                fixable_items=fixable,
                runs_24h=runs_24h,
                tokens_24h=tokens_24h,
            )

    if mode == "triage":
        return GateResult(
            action=GateAction.TRIAGE_OK,
            reason="tier-1 triage may proceed",
            paused=False,
            l2_automation_enabled=l2_automation_enabled,
            fixable_items=fixable,
            runs_24h=runs_24h,
            tokens_24h=tokens_24h,
        )

    if mode in {"full", "repair"}:
        if not l2_automation_enabled:
            return GateResult(
                action=GateAction.L1_ONLY,
                reason="L2 automation not enabled (L1 report-only)",
                paused=False,
                l2_automation_enabled=False,
                fixable_items=fixable,
                runs_24h=runs_24h,
                tokens_24h=tokens_24h,
            )

        if not fixable:
            return GateResult(
                action=GateAction.L1_ONLY,
                reason="no fixable items in repair queue",
                paused=False,
                l2_automation_enabled=True,
                fixable_items=fixable,
                runs_24h=runs_24h,
                tokens_24h=tokens_24h,
            )

        if repair_runs >= repair_caps.max_runs_per_day:
            return GateResult(
                action=GateAction.L1_ONLY,
                reason="fable-repair run cap reached for last 24h",
                paused=False,
                l2_automation_enabled=True,
                fixable_items=fixable,
                runs_24h=runs_24h,
                tokens_24h=tokens_24h,
            )
        if repair_tokens >= int(repair_caps.max_tokens_per_day * 0.8):
            return GateResult(
                action=GateAction.L1_ONLY,
                reason="fable-repair token budget ≥80%",
                paused=False,
                l2_automation_enabled=True,
                fixable_items=fixable,
                runs_24h=runs_24h,
                tokens_24h=tokens_24h,
            )

        return GateResult(
            action=GateAction.L2_ALLOWED,
            reason=f"fixable queue items: {', '.join(fixable[:3])}",
            paused=False,
            l2_automation_enabled=True,
            fixable_items=fixable,
            runs_24h=runs_24h,
            tokens_24h=tokens_24h,
        )

    return GateResult(
        action=GateAction.TRIAGE_OK,
        reason="tier-1 triage may proceed",
        paused=False,
        l2_automation_enabled=l2_automation_enabled,
        fixable_items=fixable,
        runs_24h=runs_24h,
        tokens_24h=tokens_24h,
    )


def is_paused(state_path: Path) -> bool:
    if not state_path.is_file():
        return False
    text = state_path.read_text(encoding="utf-8")
    if "loop-pause-all" not in text.lower():
        return False
    for line in text.splitlines():
        lower = line.lower()
        if "loop-pause-all" in lower and not lower.strip().startswith("_"):
            return True
    return False


def l2_enabled_in_state(state_path: Path) -> bool:
    if not state_path.is_file():
        return False
    in_section = False
    for line in state_path.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("## loop automation"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and re.search(r"l2\s*:\s*enabled", line, re.IGNORECASE):
            return True
    return False


def count_runs_by_loop(log_path: Path, *, now: datetime | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=24)
    for row in _iter_log_rows(log_path):
        ts = _parse_ts(row["ts"])
        if ts is None or ts < cutoff:
            continue
        loop = row["loop"].strip()
        counts[loop] = counts.get(loop, 0) + 1
    return counts


def sum_tokens_by_loop(log_path: Path, *, now: datetime | None = None) -> dict[str, int]:
    totals: dict[str, int] = {}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=24)
    for row in _iter_log_rows(log_path):
        ts = _parse_ts(row["ts"])
        if ts is None or ts < cutoff:
            continue
        loop = row["loop"].strip()
        match = _TOKEN_EST.search(row["notes"])
        if match:
            totals[loop] = totals.get(loop, 0) + int(match.group(1))
    return totals


def fixable_queue_titles(queue_path: Path) -> tuple[str, ...]:
    if not queue_path.is_file():
        return ()
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    titles: list[str] = []
    for item in data.get("items", []):
        if not item.get("fixable"):
            continue
        if str(item.get("status", "queued")) not in {"queued", "in_progress"}:
            continue
        title = str(item.get("title", "")).strip()
        if title:
            titles.append(title)
    return tuple(titles)


def _default_queue_path(repo_root: Path) -> Path:
    env = "paper-dry"
    env_file = repo_root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("AOA_ENV="):
                env = line.split("=", 1)[1].strip().strip('"').strip("'") or env
                break
    return repo_root / "data" / env / "repair" / "queue.json"


def _iter_log_rows(log_path: Path):
    if not log_path.is_file():
        return
    for line in log_path.read_text(encoding="utf-8").splitlines():
        match = _LOG_ROW.match(line.strip())
        if not match:
            continue
        yield match.groupdict()


def _parse_ts(raw: str) -> datetime | None:
    text = raw.strip()
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(text.replace(" UTC", ""), fmt.replace(" UTC", ""))
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
