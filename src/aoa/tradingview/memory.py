"""Persistent neural memory for the TradingView desk.

The desk learns *which preset works where*. Memory is a small Hebbian mesh:

* **nodes** — desk agents, presets, symbols, timeframes.
* **synapses** — one weight per ``preset × symbol@timeframe`` edge. Each
  backtest outcome produces a bounded reward in ``[-1, 1]``; the synapse moves
  toward it with learning-rate ``eta`` (EWMA / delta rule) and every
  consolidation decays all weights by ``decay`` so stale evidence fades.
* **aggregates** — preset, symbol and timeframe trust derived from synapses.
* **episodes** — the last ``max_episodes`` run summaries (what ran, when, how).
* **lessons** — short textual rules distilled from the aggregates for the LLM
  members (same shape as :mod:`aoa.plasticity`).
* **connectome** — the fly-brain KC→MBON weights and dopamine trace so the
  motor mapping also survives restarts.

The store is a JSON file (``AOA_TRADINGVIEW_MEMORY_PATH`` or
``data/tradingview/memory.json``). It never contains secrets or orders.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MEMORY_PATH = Path("data") / "tradingview" / "memory.json"
_LESSON_WEIGHT = re.compile(r"\s*\([+-]?\d+(?:\.\d+)?\)")


def memory_path() -> Path:
    override = os.environ.get("AOA_TRADINGVIEW_MEMORY_PATH")
    return Path(override) if override else DEFAULT_MEMORY_PATH


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def reward_from_metrics(metrics: dict[str, Any]) -> float:
    """Squash backtest metrics into a bounded reward.

    Combines SQN (statistical quality), profit factor and drawdown so that a
    preset is only rewarded when it is *both* profitable and stable. Too few
    trades → near-zero reward (no evidence either way).
    """
    n = int(metrics.get("total_trades", 0) or 0)
    if n < 3:
        return 0.0
    sqn = float(metrics.get("sqn", 0.0) or 0.0)
    pf = metrics.get("profit_factor", 0.0)
    pf = 5.0 if pf in (None, float("inf")) else min(float(pf), 5.0)
    dd = abs(float(metrics.get("max_drawdown_pct", 0.0) or 0.0))
    evidence = min(1.0, n / 30.0)
    score = 0.5 * math.tanh(sqn / 2.5) + 0.5 * math.tanh(math.log(pf) if pf > 0 else -3.0)
    penalty = min(0.5, dd / 60.0)
    return max(-1.0, min(1.0, evidence * (score - penalty)))


@dataclass
class DeskMemory:
    synapses: dict[str, dict[str, Any]] = field(default_factory=dict)
    episodes: list[dict[str, Any]] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    connectome: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    consolidations: int = 0
    updated_at: str = ""
    eta: float = 0.3
    decay: float = 0.97
    max_episodes: int = 200

    # ------------------------------------------------------------------ keys
    @staticmethod
    def key(preset: str, symbol: str, timeframe: str) -> str:
        return f"{preset}|{symbol.upper()}|{timeframe}"

    # --------------------------------------------------------------- learning
    def learn(
        self,
        preset: str,
        symbol: str,
        timeframe: str,
        reward: float,
        *,
        metrics: dict[str, Any] | None = None,
        source: str = "",
    ) -> float:
        """Delta-rule update of one synapse toward ``reward``; returns the new weight."""
        k = self.key(preset, symbol, timeframe)
        row = self.synapses.get(k) or {
            "preset": preset,
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "weight": 0.0,
            "samples": 0,
            "last_reward": 0.0,
        }
        w = float(row["weight"])
        r = max(-1.0, min(1.0, float(reward)))
        w = w + self.eta * (r - w)
        row["weight"] = round(w, 6)
        row["samples"] = int(row["samples"]) + 1
        row["last_reward"] = round(r, 6)
        row["updated_at"] = _now()
        if metrics:
            row["last_metrics"] = {
                key: metrics.get(key)
                for key in ("total_trades", "sqn", "profit_factor", "net_profit_pct", "max_drawdown_pct", "win_rate_pct")
            }
        if source:
            row["source"] = source
        self.synapses[k] = row
        return w

    def recall(self, preset: str, symbol: str, timeframe: str) -> float:
        row = self.synapses.get(self.key(preset, symbol, timeframe))
        return float(row["weight"]) if row else 0.0

    def decay_all(self) -> None:
        stale = []
        for k, row in self.synapses.items():
            row["weight"] = round(float(row["weight"]) * self.decay, 6)
            if abs(row["weight"]) < 1e-3 and int(row.get("samples", 0)) > 5:
                stale.append(k)
        for k in stale:
            del self.synapses[k]

    # ------------------------------------------------------------- aggregates
    def _aggregate(self, field_name: str) -> dict[str, float]:
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for row in self.synapses.values():
            key = str(row[field_name])
            sums[key] = sums.get(key, 0.0) + float(row["weight"])
            counts[key] = counts.get(key, 0) + 1
        return {k: round(sums[k] / counts[k], 4) for k in sums}

    def preset_trust(self) -> dict[str, float]:
        return dict(sorted(self._aggregate("preset").items(), key=lambda kv: kv[1], reverse=True))

    def symbol_trust(self) -> dict[str, float]:
        return dict(sorted(self._aggregate("symbol").items(), key=lambda kv: kv[1], reverse=True))

    def timeframe_trust(self) -> dict[str, float]:
        return dict(sorted(self._aggregate("timeframe").items(), key=lambda kv: kv[1], reverse=True))

    def best_edges(self, n: int = 10) -> list[dict[str, Any]]:
        rows = sorted(self.synapses.values(), key=lambda r: float(r["weight"]), reverse=True)
        return [dict(r) for r in rows[:n]]

    def worst_edges(self, n: int = 10) -> list[dict[str, Any]]:
        rows = sorted(self.synapses.values(), key=lambda r: float(r["weight"]))
        return [dict(r) for r in rows[:n]]

    # ---------------------------------------------------------------- episodes
    def add_episode(self, kind: str, summary: dict[str, Any]) -> None:
        self.episodes.append({"at": _now(), "kind": kind, **summary})
        if len(self.episodes) > self.max_episodes:
            self.episodes = self.episodes[-self.max_episodes :]

    def touch_agent(self, name: str, role: str, note: str = "") -> None:
        row = self.agents.get(name) or {"name": name, "role": role, "runs": 0}
        row["runs"] = int(row.get("runs", 0)) + 1
        row["last_seen"] = _now()
        if note:
            row["last_note"] = note
        self.agents[name] = row

    # ----------------------------------------------------------------- lessons
    def distill_lessons(self, *, max_lessons: int = 10) -> list[str]:
        lessons: list[str] = []
        pt = self.preset_trust()
        if pt:
            best = next(iter(pt.items()))
            worst = list(pt.items())[-1]
            if best[1] > 0.15:
                lessons.append(f"Preset {best[0]} has the strongest out-of-sample trust ({best[1]:+.2f}).")
            if worst[1] < -0.15:
                lessons.append(f"Preset {worst[0]} is losing trust ({worst[1]:+.2f}); do not deploy without re-validation.")
        tt = self.timeframe_trust()
        for tf, w in tt.items():
            if w < -0.2:
                lessons.append(f"Timeframe {tf} presets underperform after costs ({w:+.2f}); costs dominate at this horizon.")
            elif w > 0.2:
                lessons.append(f"Timeframe {tf} presets hold up out-of-sample ({w:+.2f}).")
        for row in self.best_edges(3):
            if float(row["weight"]) > 0.25:
                lessons.append(
                    f"{row['preset']} on {row['symbol']}@{row['timeframe']} is a favourable edge ({float(row['weight']):+.2f})."
                )
        for row in self.worst_edges(2):
            if float(row["weight"]) < -0.25:
                lessons.append(
                    f"Avoid {row['preset']} on {row['symbol']}@{row['timeframe']} ({float(row['weight']):+.2f})."
                )
        merged: list[str] = []
        seen: set[str] = set()
        for text in lessons + self.lessons:
            # Fresh lessons win; an older copy that differs only by its weight is a duplicate.
            key = _LESSON_WEIGHT.sub("", text)
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
            if len(merged) >= max_lessons:
                break
        self.lessons = merged
        return merged

    def consolidate(self) -> None:
        self.decay_all()
        self.distill_lessons()
        self.consolidations += 1
        self.updated_at = _now()

    # ------------------------------------------------------------------- views
    def to_context(self) -> dict[str, Any]:
        return {
            "synapses": len(self.synapses),
            "episodes": len(self.episodes),
            "consolidations": self.consolidations,
            "updated_at": self.updated_at,
            "preset_trust": self.preset_trust(),
            "symbol_trust": dict(list(self.symbol_trust().items())[:12]),
            "timeframe_trust": self.timeframe_trust(),
            "best_edges": self.best_edges(5),
            "lessons": list(self.lessons),
            "agents": self.agents,
        }

    def to_prompt_block(self) -> str:
        if not self.synapses and not self.lessons:
            return ""
        lines = ["TradingView desk memory (out-of-sample trust; bias, not hard rules):"]
        for text in self.lessons[:6]:
            lines.append(f"- {text}")
        pt = self.preset_trust()
        if pt:
            lines.append("Preset trust: " + ", ".join(f"{k} {v:+.2f}" for k, v in list(pt.items())[:6]))
        return "\n".join(lines)

    # ------------------------------------------------------------ persistence
    def to_json(self) -> dict[str, Any]:
        return {
            "version": 1,
            "synapses": self.synapses,
            "episodes": self.episodes,
            "lessons": self.lessons,
            "connectome": self.connectome,
            "agents": self.agents,
            "consolidations": self.consolidations,
            "updated_at": self.updated_at,
            "eta": self.eta,
            "decay": self.decay,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DeskMemory:
        return cls(
            synapses=dict(data.get("synapses") or {}),
            episodes=list(data.get("episodes") or []),
            lessons=[str(x) for x in data.get("lessons") or []],
            connectome=dict(data.get("connectome") or {}),
            agents=dict(data.get("agents") or {}),
            consolidations=int(data.get("consolidations", 0) or 0),
            updated_at=str(data.get("updated_at", "")),
            eta=float(data.get("eta", 0.3) or 0.3),
            decay=float(data.get("decay", 0.97) or 0.97),
        )

    @classmethod
    def load(cls, path: Path | str | None = None) -> DeskMemory:
        p = Path(path) if path else memory_path()
        if not p.is_file():
            return cls()
        try:
            return cls.from_json(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return cls()

    def save(self, path: Path | str | None = None) -> Path:
        p = Path(path) if path else memory_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = self.updated_at or _now()
        p.write_text(json.dumps(self.to_json(), indent=1, sort_keys=True, default=str), encoding="utf-8")
        return p
