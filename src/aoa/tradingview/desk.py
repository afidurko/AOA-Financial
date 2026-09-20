"""The TradingView desk — a sub-team that lives *outside* the ATTL twelve.

Lead: **Julie** (algorithm specialist, twelve). Risk sign-off: **Andrea**.
Critical-only review: **Kai**. Desk members (deterministic, no LLM required):

---------  --------------------------  --------------------------------------------------
Member     Role                        Owns
---------  --------------------------  --------------------------------------------------
Dara       Data engineer               candles, universe, fundamentals snapshots, caches
Piper      Pine engineer               Pine v6 generation + lint + export
Quinn      Backtest quant              emulator runs, walk-forward, sweeps, Monte-Carlo
Mira       Memory curator              DeskMemory learning / consolidation / brain capture
Sol        Connectome motor mapper     FlyConnectome proposals (human-gated)
---------  --------------------------  --------------------------------------------------

``DeskRunner.run()`` executes one full desk cycle:

    Dara fetch → Quinn backtest (+walk-forward) → Mira learn → Sol propose → report

Reports are written to ``data/tradingview/reports/`` and summarised into
``brain/captures/`` so Nova's mesh sees them. No orders are ever placed.
"""

from __future__ import annotations

import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.brokerage.models import Bar
from aoa.tradingview.backtest import (
    EmulatorConfig,
    monte_carlo_trades,
    run_backtest,
    walk_forward,
)
from aoa.tradingview.connectome import FlyConnectome, sense_from_features
from aoa.tradingview.data import fetch_bars, guess_market, quality_issues
from aoa.tradingview.fundamentals import FundamentalSnapshot, YahooFundamentals, gate_passes
from aoa.tradingview.memory import DeskMemory, reward_from_metrics
from aoa.tradingview.pine import generate_pine, lint_pine, pine_filename
from aoa.tradingview.presets import PRESETS, Preset, get_preset, get_timeframe
from aoa.tradingview.rules import build_strategy

DESK_MEMBERS: tuple[tuple[str, str], ...] = (
    ("Dara", "Data engineer — candles, universe, fundamentals"),
    ("Piper", "Pine engineer — Pine v6 generation, lint, export"),
    ("Quinn", "Backtest quant — emulator, walk-forward, sweeps, Monte-Carlo"),
    ("Mira", "Memory curator — neural memory learning & consolidation"),
    ("Sol", "Connectome motor mapper — fly-brain proposals, human-gated"),
)
DESK_LEAD = "Julie"
DESK_RISK = "Andrea"
DESK_REVIEW = "Kai"

DEFAULT_REPORT_DIR = Path("data") / "tradingview" / "reports"
DEFAULT_PINE_DIR = Path("tradingview")


@dataclass
class DeskRow:
    preset: str
    symbol: str
    timeframe: str
    market: str
    source: str
    n_bars: int
    metrics: dict[str, Any]
    walk_forward: dict[str, Any] | None
    monte_carlo: dict[str, Any] | None
    reward: float
    weight: float
    fundamentals: dict[str, Any] | None = None
    fundamentals_ok: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market": self.market,
            "source": self.source,
            "n_bars": self.n_bars,
            "metrics": self.metrics,
            "walk_forward": self.walk_forward,
            "monte_carlo": self.monte_carlo,
            "reward": round(self.reward, 4),
            "weight": round(self.weight, 4),
            "fundamentals": self.fundamentals,
            "fundamentals_ok": self.fundamentals_ok,
            "error": self.error,
        }


@dataclass
class DeskReport:
    started_at: str
    finished_at: str = ""
    rows: list[DeskRow] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    pine_files: list[str] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    never_live: bool = True

    def ranked(self) -> list[DeskRow]:
        return sorted(self.rows, key=lambda r: r.reward, reverse=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "lead": DESK_LEAD,
            "risk": DESK_RISK,
            "review": DESK_REVIEW,
            "members": [{"name": n, "role": r} for n, r in DESK_MEMBERS],
            "rows": [r.to_dict() for r in self.rows],
            "ranked": [
                {"preset": r.preset, "symbol": r.symbol, "timeframe": r.timeframe, "reward": round(r.reward, 4)}
                for r in self.ranked()[:20]
            ],
            "proposals": self.proposals,
            "pine_files": self.pine_files,
            "memory": self.memory,
            "notes": self.notes,
            "never_live": self.never_live,
        }

    def summary_lines(self) -> list[str]:
        lines = [f"TradingView desk run {self.started_at} → {self.finished_at}"]
        ok_rows = [r for r in self.rows if not r.error]
        lines.append(f"rows: {len(self.rows)} (errors: {len(self.rows) - len(ok_rows)})")
        for r in self.ranked()[:10]:
            m = r.metrics
            wf = (r.walk_forward or {}).get("oos_metrics", {})
            lines.append(
                f"  {r.reward:+.3f}  {r.preset:<34} {r.symbol:<9} {r.timeframe:<3} "
                f"trades={m.get('total_trades', 0):<4} pf={_fmt(m.get('profit_factor'))} "
                f"sqn={_fmt(m.get('sqn'))} net={_fmt(m.get('net_profit_pct'))}% "
                f"dd={_fmt(m.get('max_drawdown_pct'))}% oos_net={_fmt(wf.get('net_profit_pct'))}%"
                + (
                    f" cost-gated={m['entries_blocked_by_edge']} (edge/cost≈{_fmt(m.get('median_edge_cost_ratio'))}"
                    f", need {_fmt(m.get('required_edge_cost_ratio'))})"
                    if m.get("entries_blocked_by_edge")
                    else ""
                )
            )
        for p in self.proposals[:5]:
            lines.append(f"  motor→ {p['symbol']:<9} {p['action']:<11} size={p['size_pct']:>5}% conf={p['confidence']:.2f} (human approval required)")
        lines.extend(f"  note: {n}" for n in self.notes[:6])
        return lines


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        return f"{v:.2f}"
    return str(v)


# --------------------------------------------------------------------------- #
# Worker (process-pool friendly)
# --------------------------------------------------------------------------- #


def _evaluate(
    bars: list[Bar],
    preset: Preset,
    symbol: str,
    *,
    folds: int,
    monte_carlo: bool,
    fundamentals_ok: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    cfg = EmulatorConfig()
    res = run_backtest(bars, preset, symbol=symbol, cfg=cfg, fundamentals_ok=fundamentals_ok)
    wf: dict[str, Any] | None = None
    if folds > 0 and len(bars) >= 20 * (folds + 1) and preset.tunable:
        try:
            wf = walk_forward(bars, preset, symbol=symbol, folds=folds, cfg=cfg, fundamentals_ok=fundamentals_ok).to_dict()
        except ValueError:
            wf = None
    mc = monte_carlo_trades(res.trades, seed=7, position_fraction=preset.risk.qty_pct_equity / 100.0) if monte_carlo else None
    return res.metrics, wf, mc


def _evaluate_task(args: tuple[Any, ...]) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    bars, preset_name, params, symbol, folds, monte_carlo, fundamentals_ok, timeframe = args
    preset = get_preset(preset_name).with_timeframe(timeframe)
    if params:
        preset = preset.with_params(**params)
    return _evaluate(bars, preset, symbol, folds=folds, monte_carlo=monte_carlo, fundamentals_ok=fundamentals_ok)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


@dataclass
class DeskRunner:
    memory: DeskMemory = field(default_factory=DeskMemory.load)
    connectome: FlyConnectome | None = None
    source: str = "auto"
    cache_dir: Path | None = None
    report_dir: Path = DEFAULT_REPORT_DIR
    folds: int = 3
    monte_carlo: bool = True
    workers: int = 1
    fetch_pause: float = 0.0
    fundamentals: YahooFundamentals | None = None
    use_fundamentals: bool = True
    brain_root: Path | None = None
    verbose: bool = False
    label: str = "desk"  # report file prefix: desk-<stamp>.json / latest-<label>.json

    def __post_init__(self) -> None:
        if self.connectome is None:
            self.connectome = FlyConnectome.from_json(self.memory.connectome)

    # ------------------------------------------------------------------ Dara
    def fetch(self, symbol: str, timeframe: str, *, limit: int | None = None, seed: int | None = None) -> tuple[list[Bar], str]:
        bars, src = fetch_bars(
            symbol,
            timeframe,
            source=self.source,
            limit=limit,
            cache_dir=self.cache_dir,
            seed=seed,
            market=guess_market(symbol),
        )
        if self.fetch_pause and not src.startswith("synthetic"):
            time.sleep(self.fetch_pause)
        return bars, src

    def fundamentals_for(self, symbol: str, preset: Preset) -> tuple[FundamentalSnapshot | None, bool, list[str]]:
        if preset.market != "equity" or not preset.fundamentals.enabled or not self.use_fundamentals:
            return None, True, []
        if self.source == "synthetic":
            return None, True, ["synthetic run — fundamentals gate skipped"]
        if self.fundamentals is None:
            self.fundamentals = YahooFundamentals()
        snap = self.fundamentals.get(symbol)
        ok, reasons = gate_passes(snap, preset.fundamentals)
        return snap, ok, reasons

    # ----------------------------------------------------------------- Piper
    def export_pine(self, out_dir: Path | None = None, presets: list[Preset] | None = None) -> list[str]:
        out = Path(out_dir) if out_dir else DEFAULT_PINE_DIR
        out.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for preset in presets or list(PRESETS.values()):
            src = generate_pine(preset)
            problems = lint_pine(src)
            if problems:
                raise ValueError(f"{preset.name}: {problems}")
            path = out / pine_filename(preset)
            path.write_text(src, encoding="utf-8")
            written.append(str(path))
        self.memory.touch_agent("Piper", "Pine engineer", f"exported {len(written)} scripts")
        return written

    # ----------------------------------------------------------------- Quinn
    def evaluate_many(self, tasks: list[tuple[Any, ...]]) -> list[tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]]:
        if self.workers > 1 and len(tasks) > 1:
            with ProcessPoolExecutor(max_workers=self.workers) as pool:
                return list(pool.map(_evaluate_task, tasks))
        return [_evaluate_task(t) for t in tasks]

    # ------------------------------------------------------------------- run
    def run(
        self,
        symbols: list[str],
        *,
        presets: list[str] | None = None,
        timeframes: list[str] | None = None,
        limit: int | None = None,
        seed: int | None = None,
        export_pine: bool = False,
        write_report: bool = True,
        capture: bool = True,
    ) -> DeskReport:
        report = DeskReport(started_at=datetime.now(tz=timezone.utc).isoformat())
        chosen = [get_preset(n) for n in presets] if presets else list(PRESETS.values())
        assert self.connectome is not None
        self.memory.touch_agent(DESK_LEAD, "Desk lead (algorithm specialist)")
        for name, role in DESK_MEMBERS:
            self.memory.touch_agent(name, role)

        # --- Dara: gather data per (symbol, timeframe) ------------------------
        bars_cache: dict[tuple[str, str], tuple[list[Bar], str]] = {}
        tasks: list[tuple[Any, ...]] = []
        task_meta: list[dict[str, Any]] = []
        for symbol in symbols:
            market = guess_market(symbol)
            for preset in chosen:
                if preset.market != market:
                    continue
                tfs = timeframes or [preset.timeframe]
                for tf_key in tfs:
                    tf = get_timeframe(tf_key)
                    key = (symbol, tf.key)
                    if key not in bars_cache:
                        try:
                            bars_cache[key] = self.fetch(symbol, tf.key, limit=limit, seed=seed)
                        except Exception as exc:  # noqa: BLE001
                            bars_cache[key] = ([], f"error: {exc}")
                    bars, src = bars_cache[key]
                    snap, f_ok, reasons = self.fundamentals_for(symbol, preset)
                    strat_warm = build_strategy(preset.with_timeframe(tf.key)).warmup
                    skip = ""
                    if len(bars) < strat_warm + 30:
                        skip = f"insufficient bars ({len(bars)} < {strat_warm + 30})"
                    elif not src.startswith("synthetic"):
                        # Synthetic series are clean by construction; only real feeds carry
                        # unadjusted splits / bad prints that would poison the memory.
                        issues = quality_issues(bars)
                        if issues:
                            skip = "data quality: " + "; ".join(issues)
                    if skip:
                        report.rows.append(
                            DeskRow(
                                preset=preset.name, symbol=symbol, timeframe=tf.key, market=market, source=src,
                                n_bars=len(bars), metrics={}, walk_forward=None, monte_carlo=None, reward=0.0,
                                weight=self.memory.recall(preset.name, symbol, tf.key),
                                fundamentals=snap.to_dict() if snap else None, fundamentals_ok=f_ok,
                                error=skip,
                            )
                        )
                        continue
                    tasks.append((bars, preset.name, {}, symbol, self.folds, self.monte_carlo, f_ok, tf.key))
                    task_meta.append(
                        {"preset": preset, "symbol": symbol, "tf": tf.key, "market": market, "source": src,
                         "n_bars": len(bars), "snap": snap, "f_ok": f_ok, "reasons": reasons, "bars": bars}
                    )
        self.memory.touch_agent("Dara", "Data engineer", f"{len(bars_cache)} series")

        # --- Quinn: backtests --------------------------------------------------
        results = self.evaluate_many(tasks) if tasks else []
        self.memory.touch_agent("Quinn", "Backtest quant", f"{len(results)} evaluations")

        # --- Mira: learning ----------------------------------------------------
        for meta, (metrics, wf, mc) in zip(task_meta, results, strict=True):
            preset: Preset = meta["preset"]
            oos = (wf or {}).get("oos_metrics") or {}
            reward = reward_from_metrics(metrics)
            if wf:
                oos_like = {
                    "total_trades": oos.get("total_trades", 0),
                    "sqn": oos.get("mean_oos_sqn", 0.0),
                    "profit_factor": oos.get("mean_oos_profit_factor", 0.0),
                    "max_drawdown_pct": oos.get("max_drawdown_pct", 0.0),
                }
                # Out-of-sample evidence dominates; in-sample is a tie-breaker.
                reward = 0.7 * reward_from_metrics(oos_like) + 0.3 * reward
            if not meta["f_ok"]:
                reward = min(reward, 0.0)
            weight = self.memory.learn(preset.name, meta["symbol"], meta["tf"], reward, metrics=metrics, source=meta["source"])
            report.rows.append(
                DeskRow(
                    preset=preset.name, symbol=meta["symbol"], timeframe=meta["tf"], market=meta["market"],
                    source=meta["source"], n_bars=meta["n_bars"], metrics=metrics, walk_forward=wf,
                    monte_carlo=mc, reward=reward, weight=weight,
                    fundamentals=meta["snap"].to_dict() if meta["snap"] else None,
                    fundamentals_ok=meta["f_ok"],
                    error="" if meta["f_ok"] else "fundamentals gate: " + "; ".join(meta["reasons"]),
                )
            )
        self.memory.touch_agent("Mira", "Memory curator", f"{len(results)} synapses updated")
        cost_gated = [
            r for r in report.rows
            if not r.error and r.metrics.get("entries_blocked_by_edge") and r.metrics.get("total_trades", 0) == 0
        ]
        if cost_gated:
            worst = min(cost_gated, key=lambda r: r.metrics.get("median_edge_cost_ratio") or 0.0)
            report.notes.append(
                f"{len(cost_gated)} row(s) took no trades because the ATR edge never cleared fees "
                f"(e.g. {worst.preset} on {worst.symbol}@{worst.timeframe}: edge/cost≈"
                f"{_fmt(worst.metrics.get('median_edge_cost_ratio'))}, need "
                f"{_fmt(worst.metrics.get('required_edge_cost_ratio'))}). "
                "Sub-minute presets need maker-fee execution or a wider target; the gate is doing its job."
            )

        # --- Sol: connectome proposals (one per symbol, best-trusted preset) ---
        best_by_symbol: dict[str, tuple[float, dict[str, Any], dict[str, Any]]] = {}
        for meta, (metrics, _wf, _mc) in zip(task_meta, results, strict=True):
            # Never build a proposal for a real symbol from synthetic stand-in bars.
            if meta["source"].startswith("synthetic") and self.source != "synthetic":
                continue
            w = self.memory.recall(meta["preset"].name, meta["symbol"], meta["tf"])
            cur = best_by_symbol.get(meta["symbol"])
            if cur is None or w > cur[0]:
                best_by_symbol[meta["symbol"]] = (w, meta, metrics)
        for symbol, (w, meta, metrics) in sorted(best_by_symbol.items()):
            preset = meta["preset"].with_timeframe(meta["tf"])
            strat = build_strategy(preset, fundamentals_ok=meta["f_ok"])
            last_sig = None
            for bar in meta["bars"]:
                last_sig = strat.on_bar(bar)
            if last_sig is None or not last_sig.ready:
                continue
            close = meta["bars"][-1].close
            sense = sense_from_features(
                symbol, last_sig.features, close=close, atr=last_sig.atr, memory_trust=w,
                exposure=0.0, drawdown=0.0, fundamentals_ok=meta["f_ok"],
            )
            cmd = self.connectome.step(sense, preset=preset.name)
            self.connectome.reinforce(reward_from_metrics(metrics))
            row = cmd.to_dict()
            row.update({"preset": preset.name, "timeframe": meta["tf"], "memory_trust": round(w, 4), "as_of": meta["bars"][-1].timestamp.isoformat()})
            report.proposals.append(row)
        self.memory.touch_agent("Sol", "Connectome motor mapper", f"{len(report.proposals)} proposals (human-gated)")

        # --- Piper: Pine export (optional) -------------------------------------
        if export_pine:
            report.pine_files = self.export_pine(presets=chosen)

        # --- consolidate + persist ---------------------------------------------
        self.memory.connectome = self.connectome.to_json()
        self.memory.add_episode(
            "desk.run",
            {
                "symbols": symbols,
                "presets": [p.name for p in chosen],
                "timeframes": timeframes or "preset-default",
                "rows": len(report.rows),
                "source": self.source,
                "top": [
                    {"preset": r.preset, "symbol": r.symbol, "timeframe": r.timeframe, "reward": round(r.reward, 4)}
                    for r in report.ranked()[:5]
                ],
            },
        )
        self.memory.consolidate()
        report.memory = self.memory.to_context()
        report.notes.extend(self.memory.lessons[:5])
        report.notes.append("All fills are simulated; proposals require human approval; no broker calls were made.")
        report.finished_at = datetime.now(tz=timezone.utc).isoformat()
        self.memory.save()
        if write_report:
            self.write_report(report)
        if capture:
            self.write_capture(report)
        return report

    # --------------------------------------------------------------- outputs
    def write_report(self, report: DeskReport) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = report.started_at.replace(":", "").replace("-", "")[:15]
        payload = json.dumps(report.to_dict(), indent=1, default=str)
        path = self.report_dir / f"{self.label}-{stamp}.json"
        path.write_text(payload, encoding="utf-8")
        (self.report_dir / f"latest-{self.label}.json").write_text(payload, encoding="utf-8")
        if self.label == "desk":
            (self.report_dir / "latest.json").write_text(payload, encoding="utf-8")
        return path

    def write_capture(self, report: DeskReport) -> Path | None:
        try:
            from aoa.brain.store import BrainStore

            store = BrainStore.open(self.brain_root)
            body = "\n".join(report.summary_lines())
            return store.write_capture("tradingview desk run", body)
        except Exception:  # noqa: BLE001 - brain is optional in tests / CI
            return None
