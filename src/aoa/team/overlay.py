"""Build chart-overlay payloads from Jim/Cindy reports + price history."""

from __future__ import annotations

from typing import Any

from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import (
    CompanyAnalysisReport,
    DecisionBrief,
    ShortTermReport,
)


def build_chart_overlays(
    *,
    snapshots: dict[str, SymbolSnapshot],
    short_term: list[ShortTermReport],
    company_analyses: list[CompanyAnalysisReport],
    decision: DecisionBrief | None = None,
    max_bars: int = 60,
) -> list[dict[str, Any]]:
    """Per-symbol series for the Jim/Cindy overlay tab."""
    jim_by = {j.symbol.upper(): j for j in short_term}
    cindy_by = {c.symbol.upper(): c for c in company_analyses}
    rec_by = {}
    if decision:
        rec_by = {
            str(r.get("symbol", "")).upper(): r
            for r in decision.recommendations
            if r.get("symbol")
        }
    symbols = sorted(
        set(snapshots) | set(jim_by) | set(cindy_by) | set(rec_by)
    )
    out: list[dict[str, Any]] = []
    for sym in symbols:
        snap = snapshots.get(sym)
        bars = _bar_series(snap, max_bars=max_bars) if snap else []
        jim = jim_by.get(sym)
        cindy = cindy_by.get(sym)
        if not bars and not jim and not cindy:
            continue
        out.append(
            {
                "symbol": sym,
                "bars": bars,
                "jim": jim.to_context() if jim else None,
                "cindy": cindy.to_context() if cindy else None,
                "alan": rec_by.get(sym),
            }
        )
    return out


def _bar_series(snap: SymbolSnapshot | None, *, max_bars: int) -> list[dict[str, Any]]:
    if snap is None:
        return []
    bars = snap.bars or snap.bars_by_timeframe.get("1Day") or []
    tail = bars[-max_bars:]
    series: list[dict[str, Any]] = []
    for i, bar in enumerate(tail):
        series.append(
            {
                "i": i,
                "t": getattr(bar, "timestamp", None) or getattr(bar, "ts", None),
                "o": float(bar.open) if getattr(bar, "open", None) is not None else None,
                "h": float(bar.high) if getattr(bar, "high", None) is not None else None,
                "l": float(bar.low) if getattr(bar, "low", None) is not None else None,
                "c": float(bar.close),
            }
        )
    if series:
        return series
    last = snap.last_close()
    if last:
        return [{"i": 0, "t": None, "o": last, "h": last, "l": last, "c": float(last)}]
    return []
