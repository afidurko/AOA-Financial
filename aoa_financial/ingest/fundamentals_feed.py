"""Live fundamentals feed (provider-agnostic).

Fetches real company fundamentals and normalises them to the store's schema
(``pe_ratio``, ``pb_ratio``, ``dividend_yield``, ``revenue_growth``,
``profit_margin``, ``debt_to_equity``, ``roe``, ``free_cash_flow``).

Three providers are supported, selected by which API key is present in the
environment (or forced via ``AOA_FUNDAMENTALS_PROVIDER``):

    Alpha Vantage   ALPHAVANTAGE_API_KEY   (OVERVIEW endpoint)
    FMP             FMP_API_KEY            (ratios-ttm endpoint)
    Finnhub         FINNHUB_API_KEY        (stock/metric endpoint)

If no key is configured, or the network/SDK is unavailable, or the provider
rate-limits, the feed degrades to the deterministic synthetic generator so the
pipeline is never blocked.

Testability: every network provider isolates its single HTTP call in
``_raw(ticker)``; the pure normalisation lives in ``_normalize(raw)``. Tests
mock ``_raw`` (or the module-level ``_get_json``) and never touch the network.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Optional

from ..config import EPOCH_START

# Canonical fields stored for every security.
FIELDS = ("pe_ratio", "pb_ratio", "dividend_yield", "revenue_growth",
          "profit_margin", "debt_to_equity", "roe", "free_cash_flow")


def _to_float(x) -> Optional[float]:
    """Parse provider values that may be ``None``, ``"None"``, ``"-"`` or ``""``."""
    if x is None:
        return None
    try:
        s = str(x).strip()
        if s in ("", "-", "None", "null", "N/A", "NaN"):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _get_json(url: str, params: Optional[dict] = None,
              timeout: float = 10.0):
    """Single shared HTTP-JSON helper. Returns parsed JSON or ``None``.

    Centralised so tests can monkeypatch one function and so every network
    failure mode (no ``requests``, timeout, non-200, bad JSON) collapses to
    ``None`` rather than raising into the pipeline.
    """
    try:
        import requests
    except Exception:
        return None
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


# -- providers ------------------------------------------------------------
class FundamentalsProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def _raw(self, ticker: str):
        raise NotImplementedError

    def _normalize(self, raw) -> Optional[Dict[str, Optional[float]]]:
        raise NotImplementedError

    def fetch(self, ticker: str) -> Optional[Dict[str, Optional[float]]]:
        raw = self._raw(ticker)
        if not raw:
            return None
        data = self._normalize(raw)
        if not data:
            return None
        # Drop the row entirely if nothing usable came back.
        if all(v is None for v in data.values()):
            return None
        return {k: data.get(k) for k in FIELDS}


class AlphaVantageProvider(FundamentalsProvider):
    name = "alphavantage"
    URL = "https://www.alphavantage.co/query"

    def available(self) -> bool:
        return bool(os.environ.get("ALPHAVANTAGE_API_KEY"))

    def _raw(self, ticker: str):
        key = os.environ.get("ALPHAVANTAGE_API_KEY")
        data = _get_json(self.URL, {"function": "OVERVIEW", "symbol": ticker,
                                    "apikey": key})
        # Empty dict / rate-limit "Note"/"Information" => treat as no data.
        if not data or "Symbol" not in data:
            return None
        return data

    def _normalize(self, raw) -> Dict[str, Optional[float]]:
        return {
            "pe_ratio": _to_float(raw.get("PERatio")),
            "pb_ratio": _to_float(raw.get("PriceToBookRatio")),
            "dividend_yield": _to_float(raw.get("DividendYield")),
            "revenue_growth": _to_float(raw.get("QuarterlyRevenueGrowthYOY")),
            "profit_margin": _to_float(raw.get("ProfitMargin")),
            "debt_to_equity": None,  # not exposed by OVERVIEW
            "roe": _to_float(raw.get("ReturnOnEquityTTM")),
            "free_cash_flow": None,
        }


class FMPProvider(FundamentalsProvider):
    name = "fmp"
    URL = "https://financialmodelingprep.com/api/v3/ratios-ttm/{sym}"

    def available(self) -> bool:
        return bool(os.environ.get("FMP_API_KEY"))

    def _raw(self, ticker: str):
        key = os.environ.get("FMP_API_KEY")
        data = _get_json(self.URL.format(sym=ticker), {"apikey": key})
        if isinstance(data, list) and data:
            return data[0]
        return None

    def _normalize(self, raw) -> Dict[str, Optional[float]]:
        return {
            "pe_ratio": _to_float(raw.get("peRatioTTM")),
            "pb_ratio": _to_float(raw.get("priceToBookRatioTTM")),
            "dividend_yield": _to_float(raw.get("dividendYieldTTM")),
            "revenue_growth": None,  # in a separate growth endpoint
            "profit_margin": _to_float(raw.get("netProfitMarginTTM")),
            "debt_to_equity": _to_float(raw.get("debtEquityRatioTTM")),
            "roe": _to_float(raw.get("returnOnEquityTTM")),
            "free_cash_flow": _to_float(raw.get("freeCashFlowPerShareTTM")),
        }


class FinnhubProvider(FundamentalsProvider):
    name = "finnhub"
    URL = "https://finnhub.io/api/v1/stock/metric"

    def available(self) -> bool:
        return bool(os.environ.get("FINNHUB_API_KEY"))

    def _raw(self, ticker: str):
        key = os.environ.get("FINNHUB_API_KEY")
        data = _get_json(self.URL, {"symbol": ticker, "metric": "all",
                                    "token": key})
        if isinstance(data, dict) and data.get("metric"):
            return data["metric"]
        return None

    def _normalize(self, raw) -> Dict[str, Optional[float]]:
        def pct(x):
            v = _to_float(x)
            return None if v is None else v / 100.0  # Finnhub gives percents
        return {
            "pe_ratio": _to_float(raw.get("peTTM")),
            "pb_ratio": _to_float(raw.get("pbQuarterly")),
            "dividend_yield": pct(raw.get("dividendYieldIndicatedAnnual")),
            "revenue_growth": pct(raw.get("revenueGrowthTTMYoy")),
            "profit_margin": pct(raw.get("netProfitMarginTTM")),
            "debt_to_equity": _to_float(raw.get("totalDebt/totalEquityQuarterly")),
            "roe": pct(raw.get("roeTTM")),
            "free_cash_flow": _to_float(raw.get("freeCashFlowPerShareTTM")),
        }


class SyntheticProvider(FundamentalsProvider):
    """Always-available fallback using the deterministic generator."""
    name = "synthetic"

    def available(self) -> bool:
        return True

    def fetch(self, ticker: str) -> Optional[Dict[str, Optional[float]]]:
        from .synthetic import SyntheticGenerator
        series = SyntheticGenerator(epoch_start=EPOCH_START).generate(ticker)
        return {k: series.fundamentals.get(k) for k in FIELDS}


_REGISTRY = {
    "alphavantage": AlphaVantageProvider,
    "fmp": FMPProvider,
    "finnhub": FinnhubProvider,
    "synthetic": SyntheticProvider,
}


def get_provider(name: Optional[str] = None) -> FundamentalsProvider:
    """Resolve a provider.

    Precedence: explicit ``name`` -> ``AOA_FUNDAMENTALS_PROVIDER`` env ->
    first real provider whose API key is present -> synthetic fallback.
    """
    name = name or os.environ.get("AOA_FUNDAMENTALS_PROVIDER")
    if name:
        cls = _REGISTRY.get(name.lower())
        if cls is None:
            raise ValueError(f"unknown fundamentals provider: {name}")
        return cls()
    for cls in (AlphaVantageProvider, FMPProvider, FinnhubProvider):
        p = cls()
        if p.available():
            return p
    return SyntheticProvider()


def fetch_fundamentals(ticker: str, provider: Optional[str] = None) -> dict:
    """Fetch fundamentals for ``ticker`` with automatic fallback.

    Returns a dict with ``provider`` (the source actually used) plus the
    normalised fundamental fields. A real provider that fails (no network,
    rate-limited, unknown symbol) transparently falls back to synthetic.
    """
    p = get_provider(provider)
    data = p.fetch(ticker.upper())
    source = p.name
    if data is None and p.name != "synthetic":
        data = SyntheticProvider().fetch(ticker.upper())
        source = "synthetic"
    return {"provider": source, **(data or {})}
