"""Fundamental snapshot + gate shared by the emulator and the Pine generator.

In TradingView the gate is expressed with ``request.financial()`` (TTM EPS,
revenue growth, margins) and evaluated on every bar. Offline we only have a
*current* snapshot from a public endpoint, so the emulator applies the gate as
a static filter and says so in the report — a current snapshot is **not**
point-in-time data and can leak survivorship/lookahead into a long backtest.
The desk therefore treats fundamentals as a *universe filter*, not a timing
signal, and grades position presets primarily on the walk-forward OOS numbers.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aoa.tradingview.presets import FundamentalFilter

_YAHOO_MODULES = "defaultKeyStatistics,financialData,summaryDetail,price"


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    trailing_pe: float | None = None
    forward_pe: float | None = None
    market_cap: float | None = None
    eps_growth_pct: float | None = None  # earnings growth YoY (quarterly)
    revenue_growth_pct: float | None = None
    net_margin_pct: float | None = None
    debt_to_equity: float | None = None
    return_on_equity_pct: float | None = None
    price_to_book: float | None = None
    free_cash_flow: float | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def gate_passes(snapshot: FundamentalSnapshot | None, gate: FundamentalFilter) -> tuple[bool, list[str]]:
    """Evaluate the gate; unknown fields are neutral (never block on missing data)."""
    if not gate.enabled:
        return True, []
    if snapshot is None:
        return True, ["fundamentals unavailable — gate skipped"]
    reasons: list[str] = []
    ok = True
    if snapshot.trailing_pe is not None:
        if snapshot.trailing_pe <= 0:
            ok = False
            reasons.append("negative trailing earnings")
        elif snapshot.trailing_pe > gate.max_trailing_pe:
            ok = False
            reasons.append(f"trailing P/E {snapshot.trailing_pe:.1f} > {gate.max_trailing_pe:g}")
    if snapshot.eps_growth_pct is not None and snapshot.eps_growth_pct < gate.min_eps_growth_pct:
        ok = False
        reasons.append(f"EPS growth {snapshot.eps_growth_pct:.1f}% < {gate.min_eps_growth_pct:g}%")
    if snapshot.revenue_growth_pct is not None and snapshot.revenue_growth_pct < gate.min_revenue_growth_pct:
        ok = False
        reasons.append(f"revenue growth {snapshot.revenue_growth_pct:.1f}% < {gate.min_revenue_growth_pct:g}%")
    if snapshot.net_margin_pct is not None and snapshot.net_margin_pct < gate.min_net_margin_pct:
        ok = False
        reasons.append(f"net margin {snapshot.net_margin_pct:.1f}% < {gate.min_net_margin_pct:g}%")
    if snapshot.debt_to_equity is not None and snapshot.debt_to_equity > gate.max_debt_to_equity:
        ok = False
        reasons.append(f"debt/equity {snapshot.debt_to_equity:.2f} > {gate.max_debt_to_equity:g}")
    return ok, reasons


# --------------------------------------------------------------------------- #
# Yahoo quoteSummary (crumb flow) — best effort, keyless
# --------------------------------------------------------------------------- #


def _raw(d: dict[str, Any] | None, key: str) -> float | None:
    if not d:
        return None
    v = d.get(key)
    if isinstance(v, dict):
        v = v.get("raw")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_yahoo_quote_summary(symbol: str, payload: dict[str, Any]) -> FundamentalSnapshot | None:
    qs = payload.get("quoteSummary") or {}
    if qs.get("error"):
        return None
    results = qs.get("result") or []
    if not results:
        return None
    r = results[0]
    ks = r.get("defaultKeyStatistics") or {}
    fd = r.get("financialData") or {}
    sd = r.get("summaryDetail") or {}
    dte = _raw(fd, "debtToEquity")
    return FundamentalSnapshot(
        symbol=symbol,
        trailing_pe=_raw(sd, "trailingPE") or _raw(ks, "trailingPE"),
        forward_pe=_raw(sd, "forwardPE") or _raw(ks, "forwardPE"),
        market_cap=_raw(sd, "marketCap") or _raw(r.get("price"), "marketCap"),
        eps_growth_pct=_pct(_raw(ks, "earningsQuarterlyGrowth")),
        revenue_growth_pct=_pct(_raw(fd, "revenueGrowth")),
        net_margin_pct=_pct(_raw(fd, "profitMargins") or _raw(ks, "profitMargins")),
        debt_to_equity=(dte / 100.0) if dte is not None else None,  # Yahoo reports percent
        return_on_equity_pct=_pct(_raw(fd, "returnOnEquity")),
        price_to_book=_raw(ks, "priceToBook"),
        free_cash_flow=_raw(fd, "freeCashflow"),
        source="yahoo",
    )


def _pct(x: float | None) -> float | None:
    return None if x is None else x * 100.0


class YahooFundamentals:
    """Fetches ``quoteSummary`` using Yahoo's cookie+crumb handshake; caches to JSON."""

    def __init__(self, cache_path: Path | str | None = None, *, timeout: float = 20.0) -> None:
        self.cache_path = Path(cache_path) if cache_path else Path("data") / "tradingview" / "fundamentals.json"
        self.timeout = timeout
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._crumb: str | None = None
        self._cache: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.cache_path.is_file():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=1, sort_keys=True), encoding="utf-8")

    def _open(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AOA-Financial"})
        with self._opener.open(req, timeout=self.timeout) as resp:  # noqa: S310
            return resp.read()

    def _ensure_crumb(self) -> str:
        if self._crumb:
            return self._crumb
        try:
            self._open("https://fc.yahoo.com")
        except urllib.error.HTTPError:
            pass  # 404 is fine — we only need the cookie
        crumb = self._open("https://query2.finance.yahoo.com/v1/test/getcrumb").decode("utf-8").strip()
        if not crumb or "<" in crumb:
            raise RuntimeError("yahoo crumb unavailable")
        self._crumb = crumb
        return crumb

    def get(self, symbol: str, *, refresh: bool = False) -> FundamentalSnapshot | None:
        key = symbol.upper()
        if not refresh and key in self._cache:
            row = self._cache[key]
            return FundamentalSnapshot(**row) if row else None
        try:
            crumb = self._ensure_crumb()
            q = urllib.parse.urlencode({"modules": _YAHOO_MODULES, "crumb": crumb})
            url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(key)}?{q}"
            payload = json.loads(self._open(url).decode("utf-8"))
            snap = parse_yahoo_quote_summary(key, payload)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError, OSError):
            snap = None
        self._cache[key] = snap.to_dict() if snap else None
        self._save()
        return snap
