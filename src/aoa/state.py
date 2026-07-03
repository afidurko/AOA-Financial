"""Persistent state that must survive process restarts.

Two pieces of state cannot live only in memory:

1. **The daily-loss baseline** — the equity the day started at, which the
   kill switch compares against. If this reset on every restart, an intraday
   restart would silently disarm the kill switch.
2. **The settlement ledger** — proceeds from sells that have not yet settled
   (cash accounts settle T+1). Spending unsettled proceeds and then selling
   again triggers good-faith violations, so the swarm must subtract unsettled
   cash from what it treats as available — and that tracking must persist.

Both are stored together in a small JSON file (default ``journal/state.json``).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def next_business_day(d: date) -> date:
    """The next weekday after ``d`` (US T+1 settlement, ignoring market holidays).

    Ignoring holidays settles at most a day or two early, which is the less
    conservative direction; acceptable for an approximate good-faith guard.
    """
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:  # Saturday=5, Sunday=6
        nd += timedelta(days=1)
    return nd


class StateStore:
    def __init__(self, path: str | Path = "journal/state.json") -> None:
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")

    # --- daily-loss baseline -------------------------------------------------
    def starting_equity_for_today(self, current_equity: float, today: date | None = None) -> float:
        """Return the equity the day started at, persisting it on the first call
        of a new day. Subsequent calls (including after a restart) return the
        stored baseline so the kill switch stays armed."""
        key = (today or date.today()).isoformat()
        baseline = self._data.get("baseline")
        if baseline and baseline.get("date") == key:
            return float(baseline["equity"])
        self._data["baseline"] = {"date": key, "equity": float(current_equity)}
        self._save()
        return float(current_equity)

    # --- settlement ledger ---------------------------------------------------
    def record_sale(self, amount: float, trade_day: date | None = None) -> str:
        """Record sale proceeds as unsettled until the next business day.
        Returns the settlement date (ISO)."""
        settle = next_business_day(trade_day or date.today()).isoformat()
        self._data.setdefault("settlements", []).append(
            {"settle_date": settle, "amount": round(float(amount), 2)}
        )
        self._save()
        return settle

    def unsettled_cash(self, today: date | None = None) -> float:
        """Total proceeds not yet settled as of ``today``. Prunes settled rows."""
        key = (today or date.today()).isoformat()
        settlements = self._data.get("settlements", [])
        remaining = [s for s in settlements if str(s.get("settle_date", "")) > key]
        if len(remaining) != len(settlements):
            self._data["settlements"] = remaining
            self._save()
        return round(sum(float(s["amount"]) for s in remaining), 2)
