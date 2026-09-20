"""US equity universe across exchanges from the Nasdaq Trader symbol directory.

Sources (public, keyless):

* ``https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`` — NASDAQ
  listings (market categories Q = Global Select, G = Global Market, S = Capital Market).
* ``https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`` — everything
  else with the primary exchange code: ``N`` NYSE, ``A`` NYSE American,
  ``P`` NYSE Arca, ``Z`` Cboe BZX, ``V`` IEX.

Filters drop ETFs, test issues, delinquent/bankrupt NASDAQ statuses, and
derivative share classes (warrants, units, rights, preferreds) so the result
is a list of common stocks. A frozen fallback list keeps the lane usable
offline.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

EXCHANGE_NAMES = {
    "NASDAQ": "NASDAQ",
    "N": "NYSE",
    "A": "NYSE American",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}

_DERIVATIVE_HINTS = (
    " warrant",
    " warrants",
    " unit",
    " units",
    " right",
    " rights",
    "preferred",
    "depositary shares each representing a 1/",
    "% notes",
    "notes due",
    "debentures",
    "trust preferred",
    "subordinated",
)

FALLBACK_UNIVERSE: tuple[tuple[str, str, str], ...] = (
    ("AAPL", "Apple Inc.", "NASDAQ"),
    ("MSFT", "Microsoft Corporation", "NASDAQ"),
    ("NVDA", "NVIDIA Corporation", "NASDAQ"),
    ("AMZN", "Amazon.com, Inc.", "NASDAQ"),
    ("GOOGL", "Alphabet Inc.", "NASDAQ"),
    ("META", "Meta Platforms, Inc.", "NASDAQ"),
    ("TSLA", "Tesla, Inc.", "NASDAQ"),
    ("AMD", "Advanced Micro Devices, Inc.", "NASDAQ"),
    ("INTC", "Intel Corporation", "NASDAQ"),
    ("NFLX", "Netflix, Inc.", "NASDAQ"),
    ("JPM", "JPMorgan Chase & Co.", "NYSE"),
    ("XOM", "Exxon Mobil Corporation", "NYSE"),
    ("KO", "The Coca-Cola Company", "NYSE"),
    ("JNJ", "Johnson & Johnson", "NYSE"),
    ("PG", "The Procter & Gamble Company", "NYSE"),
    ("V", "Visa Inc.", "NYSE"),
    ("UNH", "UnitedHealth Group Incorporated", "NYSE"),
    ("HD", "The Home Depot, Inc.", "NYSE"),
    ("BAC", "Bank of America Corporation", "NYSE"),
    ("WMT", "Walmart Inc.", "NYSE"),
    ("CVX", "Chevron Corporation", "NYSE"),
    ("PFE", "Pfizer Inc.", "NYSE"),
    ("DIS", "The Walt Disney Company", "NYSE"),
    ("CAT", "Caterpillar Inc.", "NYSE"),
    ("BA", "The Boeing Company", "NYSE"),
    ("GE", "GE Aerospace", "NYSE"),
    ("F", "Ford Motor Company", "NYSE"),
    ("T", "AT&T Inc.", "NYSE"),
    ("UBER", "Uber Technologies, Inc.", "NYSE"),
    ("PLTR", "Palantir Technologies Inc.", "NASDAQ"),
    ("IMO", "Imperial Oil Limited", "NYSE American"),
    ("BTG", "B2Gold Corp.", "NYSE American"),
    ("NG", "NovaGold Resources Inc.", "NYSE American"),
    ("UUUU", "Energy Fuels Inc.", "NYSE American"),
    ("LODE", "Comstock Inc.", "NYSE American"),
)


@dataclass(frozen=True)
class UniverseEntry:
    symbol: str
    name: str
    exchange: str

    def to_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "name": self.name, "exchange": self.exchange}


def _fetch_text(url: str, *, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "AOA-Financial/tradingview-desk"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def _is_common_stock(symbol: str, name: str) -> bool:
    if not symbol or not symbol.isalpha():
        return False  # drops ``.``/``$``/``-`` share-class and derivative suffixes
    lower = name.lower()
    return not any(hint in lower for hint in _DERIVATIVE_HINTS)


def parse_nasdaq_listed(text: str) -> list[UniverseEntry]:
    out: list[UniverseEntry] = []
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("File Creation Time")]
    if not lines:
        return out
    header = lines[0].split("|")
    idx = {name: i for i, name in enumerate(header)}
    for ln in lines[1:]:
        parts = ln.split("|")
        if len(parts) < len(header):
            continue
        symbol = parts[idx.get("Symbol", 0)].strip()
        name = parts[idx.get("Security Name", 1)].strip()
        if parts[idx.get("Test Issue", 3)].strip() == "Y":
            continue
        if parts[idx.get("Financial Status", 4)].strip() not in ("N", ""):
            continue
        if parts[idx.get("ETF", 6)].strip() == "Y":
            continue
        if not _is_common_stock(symbol, name):
            continue
        out.append(UniverseEntry(symbol, name, "NASDAQ"))
    return out


def parse_other_listed(text: str) -> list[UniverseEntry]:
    out: list[UniverseEntry] = []
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("File Creation Time")]
    if not lines:
        return out
    header = lines[0].split("|")
    idx = {name: i for i, name in enumerate(header)}
    for ln in lines[1:]:
        parts = ln.split("|")
        if len(parts) < len(header):
            continue
        symbol = parts[idx.get("ACT Symbol", 0)].strip()
        name = parts[idx.get("Security Name", 1)].strip()
        exch = parts[idx.get("Exchange", 2)].strip()
        if parts[idx.get("ETF", 4)].strip() == "Y":
            continue
        if parts[idx.get("Test Issue", 6)].strip() == "Y":
            continue
        if not _is_common_stock(symbol, name):
            continue
        out.append(UniverseEntry(symbol, name, EXCHANGE_NAMES.get(exch, exch)))
    return out


def select_universe(
    entries: list[UniverseEntry],
    *,
    n: int = 2000,
    exchanges: tuple[str, ...] | None = None,
) -> list[UniverseEntry]:
    """Pick ``n`` names spread evenly across the alphabet and across exchanges."""
    pool = [e for e in entries if not exchanges or e.exchange in exchanges]
    pool.sort(key=lambda e: e.symbol)
    if n <= 0 or len(pool) <= n:
        return pool
    by_exchange: dict[str, list[UniverseEntry]] = {}
    for e in pool:
        by_exchange.setdefault(e.exchange, []).append(e)
    total = len(pool)
    picked: list[UniverseEntry] = []
    for _exch, rows in sorted(by_exchange.items()):
        quota = max(1, round(n * len(rows) / total))
        stride = len(rows) / quota
        picked.extend(rows[min(int(i * stride), len(rows) - 1)] for i in range(quota))
    chosen = {e.symbol: e for e in picked}
    if len(chosen) < n:
        # Quota rounding can under-fill; top up evenly from what is left.
        rest = [e for e in pool if e.symbol not in chosen]
        need = n - len(chosen)
        stride = len(rest) / need if need else 1.0
        for i in range(need):
            e = rest[min(int(i * stride), len(rest) - 1)]
            chosen[e.symbol] = e
    return sorted(chosen.values(), key=lambda e: e.symbol)[:n]


def load_universe(
    *,
    n: int = 2000,
    exchanges: tuple[str, ...] | None = None,
    cache_path: Path | str | None = None,
    refresh: bool = False,
    offline: bool = False,
) -> tuple[list[UniverseEntry], dict[str, Any]]:
    """Return ``(entries, meta)``; downloads Nasdaq Trader files unless cached/offline."""
    cache = Path(cache_path) if cache_path else Path("data") / "tradingview" / "universe.json"
    meta: dict[str, Any] = {"source": "", "fetched_at": "", "total_listed": 0}
    entries: list[UniverseEntry] = []
    if cache.is_file() and not refresh:
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            entries = [UniverseEntry(**row) for row in payload.get("entries", [])]
            meta.update(payload.get("meta", {}))
            meta["source"] = payload.get("meta", {}).get("source", "cache")
        except (json.JSONDecodeError, TypeError):
            entries = []
    if not entries and not offline:
        try:
            nasdaq = parse_nasdaq_listed(_fetch_text(NASDAQ_LISTED_URL))
            other = parse_other_listed(_fetch_text(OTHER_LISTED_URL))
            entries = nasdaq + other
            meta = {
                "source": "nasdaqtrader",
                "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                "total_listed": len(entries),
                "by_exchange": _count_by_exchange(entries),
            }
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"meta": meta, "entries": [e.to_dict() for e in entries]}), encoding="utf-8"
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            meta["error"] = str(exc)
            entries = []
    if not entries:
        entries = [UniverseEntry(*row) for row in FALLBACK_UNIVERSE]
        meta["source"] = meta.get("source") or "fallback"
        meta["total_listed"] = len(entries)
        meta["by_exchange"] = _count_by_exchange(entries)
    chosen = select_universe(entries, n=n, exchanges=exchanges)
    meta["selected"] = len(chosen)
    meta["selected_by_exchange"] = _count_by_exchange(chosen)
    return chosen, meta


def _count_by_exchange(entries: list[UniverseEntry]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in entries:
        out[e.exchange] = out.get(e.exchange, 0) + 1
    return dict(sorted(out.items()))
