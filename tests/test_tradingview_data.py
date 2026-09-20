"""Offline tests for the desk's data providers, cache, universe and fundamentals."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aoa.brokerage.models import Bar
from aoa.tradingview import data as tvdata
from aoa.tradingview.data import (
    DataError,
    dedupe_bars,
    fetch_bars,
    guess_market,
    parse_coinbase_candles,
    parse_kraken_ohlc,
    parse_yahoo_chart,
    read_cache,
    synthetic_bars,
    to_coinbase_product,
    to_kraken_pair,
    write_cache,
)
from aoa.tradingview.fundamentals import (
    FundamentalSnapshot,
    YahooFundamentals,
    gate_passes,
    parse_yahoo_quote_summary,
)
from aoa.tradingview.presets import FundamentalFilter, get_timeframe
from aoa.tradingview.universe import (
    FALLBACK_UNIVERSE,
    UniverseEntry,
    load_universe,
    parse_nasdaq_listed,
    parse_other_listed,
    select_universe,
)

# --------------------------------------------------------------------------- #
# parsers
# --------------------------------------------------------------------------- #


def test_parse_yahoo_chart_skips_null_rows() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1700000000, 1700086400, 1700172800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [1.0, None, 3.0],
                                "high": [1.5, 2.5, 3.5],
                                "low": [0.5, 1.5, 2.5],
                                "close": [1.2, 2.2, 3.2],
                                "volume": [100, 200, None],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }
    bars = parse_yahoo_chart(payload)
    assert len(bars) == 2
    assert bars[0].timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert bars[1].volume == 0.0 and bars[1].close == 3.2
    assert parse_yahoo_chart({"chart": {"result": []}}) == []
    with pytest.raises(DataError):
        parse_yahoo_chart({"chart": {"error": {"code": "Not Found"}}})


def test_parse_kraken_and_coinbase() -> None:
    kraken = {"error": [], "result": {"XXBTZUSD": [[1700000000, "1", "2", "0.5", "1.5", "1.2", "10", 3]], "last": 1}}
    bars = parse_kraken_ohlc(kraken)
    assert len(bars) == 1 and bars[0].volume == 10.0 and bars[0].high == 2.0
    with pytest.raises(DataError):
        parse_kraken_ohlc({"error": ["EQuery:Unknown asset pair"]})
    # coinbase rows: [time, low, high, open, close, volume], newest first
    cb = parse_coinbase_candles([[1700086400, 9, 11, 10, 10.5, 5], [1700000000, 8, 10, 9, 9.5, 4]])
    assert [b.open for b in cb] == [9.0, 10.0]  # sorted oldest first
    assert cb[0].low == 8.0 and cb[0].high == 10.0


# --------------------------------------------------------------------------- #
# synthetic + cache
# --------------------------------------------------------------------------- #


def test_synthetic_bars_are_seeded_and_well_formed() -> None:
    tf = get_timeframe("5")
    a = synthetic_bars("X", tf, n=300, seed=1)
    b = synthetic_bars("X", tf, n=300, seed=1)
    c = synthetic_bars("X", tf, n=300, seed=2)
    assert [x.close for x in a] == [x.close for x in b] != [x.close for x in c]
    for bar in a:
        assert bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
        assert bar.volume > 0
    assert (a[1].timestamp - a[0].timestamp).total_seconds() == 300
    # unseeded is still deterministic per (symbol, timeframe)
    assert synthetic_bars("Y", tf, n=5)[0].close == synthetic_bars("Y", tf, n=5)[0].close


def test_cache_roundtrip_and_dedupe(tmp_path) -> None:
    tf = get_timeframe("1D")
    bars = synthetic_bars("X", tf, n=10, seed=1)
    p = tmp_path / "x.csv"
    write_cache(p, bars)
    again = read_cache(p)
    assert [b.close for b in again] == [b.close for b in bars]
    assert again[0].timestamp == bars[0].timestamp
    assert read_cache(tmp_path / "missing.csv") == []
    dup = Bar(bars[3].timestamp, 1, 1, 1, 1, 1)
    merged = dedupe_bars([*bars, dup])
    assert len(merged) == 10 and merged[3].close == 1  # later row wins, order by time
    p.write_text("timestamp,open\nbad,row\n", encoding="utf-8")
    assert read_cache(p) == []


def test_symbol_mapping_helpers() -> None:
    assert guess_market("BTC-USD") == "crypto" and guess_market("ETHUSDT") == "crypto"
    assert guess_market("AAPL") == "equity" and guess_market("BTC") == "crypto"
    assert to_kraken_pair("BTC-USD") == "XBTUSD" and to_kraken_pair("ETH/USD") == "ETHUSD"
    assert to_coinbase_product("BTCUSD") == "BTC-USD" and to_coinbase_product("ETH/USD") == "ETH-USD"


def test_fetch_bars_synthetic_and_provider_fallback(tmp_path, monkeypatch) -> None:
    bars, src = fetch_bars("AAPL", "1D", source="synthetic", limit=50, seed=1)
    assert src == "synthetic" and len(bars) == 50
    with pytest.raises(DataError):
        fetch_bars("AAPL", "1D", source="nope")

    calls: list[str] = []

    def fake_yahoo(symbol, tf, *, range_=None):
        calls.append(symbol)
        return synthetic_bars(symbol, tf, n=20, seed=5)

    monkeypatch.setattr(tvdata, "fetch_yahoo", fake_yahoo)
    bars, src = fetch_bars("AAPL", "1D", source="yahoo", cache_dir=tmp_path)
    assert src == "yahoo" and len(bars) == 20 and calls == ["AAPL"]
    assert (tmp_path / "yahoo" / "AAPL_1D.csv").is_file()
    # cache hit without refresh → no network call
    bars2, src2 = fetch_bars("AAPL", "1D", source="yahoo", cache_dir=tmp_path, refresh=False)
    assert src2 == "yahoo" and len(bars2) == 20 and calls == ["AAPL"]

    def boom(*a, **k):
        raise DataError("HTTP 429")

    monkeypatch.setattr(tvdata, "fetch_kraken", boom)
    monkeypatch.setattr(tvdata, "fetch_coinbase", boom)
    monkeypatch.setattr(tvdata, "fetch_yahoo", boom)
    bars3, src3 = fetch_bars("BTC-USD", "60", source="auto", cache_dir=tmp_path, synthetic_n=100)
    assert src3.startswith("synthetic (") and "kraken" in src3 and len(bars3) == 100


# --------------------------------------------------------------------------- #
# universe
# --------------------------------------------------------------------------- #

NASDAQ_TXT = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
QQQ|Invesco QQQ Trust|G|N|N|100|Y|N
ZTST|Test Issue|G|Y|N|100|N|N
BADD|Bad Delinquent Co|S|N|D|100|N|N
ACMEW|Acme Corp - Warrant|S|N|N|100|N|N
GOOG.A|Alphabet - Class A|Q|N|N|100|N|N
MSFT|Microsoft Corporation - Common Stock|Q|N|N|100|N|N
File Creation Time: 0101202400:00|||||||
"""

OTHER_TXT = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
JPM|JPMorgan Chase & Co. Common Stock|N|JPM|N|100|N|JPM
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
IMO|Imperial Oil Limited Common Stock|A|IMO|N|100|N|IMO
BAC$L|Bank of America Depositary Shares each representing a 1/1000th|N|BACpL|N|100|N|BAC-L
ZZZ|Test|Z|ZZZ|N|100|Y|ZZZ
CBOE|Cboe Global Markets|Z|CBOE|N|100|N|CBOE
File Creation Time: 0101202400:00|||||||
"""


def test_parse_symbol_directories_filter_non_common_stock() -> None:
    nasdaq = parse_nasdaq_listed(NASDAQ_TXT)
    assert [e.symbol for e in nasdaq] == ["AAPL", "MSFT"]
    assert all(e.exchange == "NASDAQ" for e in nasdaq)
    other = parse_other_listed(OTHER_TXT)
    assert [(e.symbol, e.exchange) for e in other] == [("JPM", "NYSE"), ("IMO", "NYSE American"), ("CBOE", "Cboe BZX")]
    assert parse_nasdaq_listed("") == [] and parse_other_listed("") == []


def test_select_universe_spreads_across_exchanges() -> None:
    entries = [UniverseEntry(f"N{i:03d}", "n", "NASDAQ") for i in range(300)]
    entries += [UniverseEntry(f"Y{i:03d}", "y", "NYSE") for i in range(100)]
    entries += [UniverseEntry(f"A{i:03d}", "a", "NYSE American") for i in range(20)]
    picked = select_universe(entries, n=42)
    assert len(picked) == 42
    by = {}
    for e in picked:
        by[e.exchange] = by.get(e.exchange, 0) + 1
    assert by["NASDAQ"] > by["NYSE"] > by["NYSE American"] >= 1
    assert [e.symbol for e in picked] == sorted(e.symbol for e in picked)
    only = select_universe(entries, n=10, exchanges=("NYSE",))
    assert len(only) == 10 and all(e.exchange == "NYSE" for e in only)
    assert select_universe(entries[:5], n=10) == sorted(entries[:5], key=lambda e: e.symbol)


def test_load_universe_offline_uses_fallback_and_cache(tmp_path) -> None:
    cache = tmp_path / "universe.json"
    entries, meta = load_universe(n=10, cache_path=cache, offline=True)
    assert meta["source"] == "fallback" and len(entries) == 10
    assert meta["total_listed"] == len(FALLBACK_UNIVERSE)
    assert set(meta["selected_by_exchange"]) <= {"NASDAQ", "NYSE", "NYSE American"}
    cache.write_text(
        '{"meta": {"source": "nasdaqtrader", "total_listed": 2}, "entries": [{"symbol": "ZZ", "name": "z", "exchange": "NYSE"}, {"symbol": "AA", "name": "a", "exchange": "NASDAQ"}]}',
        encoding="utf-8",
    )
    entries2, meta2 = load_universe(n=5, cache_path=cache, offline=True)
    assert [e.symbol for e in entries2] == ["AA", "ZZ"] and meta2["source"] == "nasdaqtrader"


# --------------------------------------------------------------------------- #
# fundamentals
# --------------------------------------------------------------------------- #


def test_gate_passes_rules() -> None:
    gate = FundamentalFilter(enabled=True, max_trailing_pe=40.0, min_eps_growth_pct=0.0, min_revenue_growth_pct=5.0)
    assert gate_passes(None, gate) == (True, ["fundamentals unavailable — gate skipped"])
    assert gate_passes(None, FundamentalFilter(enabled=False)) == (True, [])
    ok, reasons = gate_passes(FundamentalSnapshot("A", trailing_pe=25.0, eps_growth_pct=10.0, revenue_growth_pct=8.0), gate)
    assert ok and reasons == []
    ok, reasons = gate_passes(FundamentalSnapshot("A", trailing_pe=80.0, eps_growth_pct=-5.0, revenue_growth_pct=2.0), gate)
    assert not ok and len(reasons) == 3
    ok, reasons = gate_passes(FundamentalSnapshot("A", trailing_pe=-3.0), gate)
    assert not ok and reasons == ["negative trailing earnings"]
    ok, _ = gate_passes(FundamentalSnapshot("A", debt_to_equity=5.0), gate)
    assert not ok
    ok, _ = gate_passes(FundamentalSnapshot("A"), gate)  # all unknown → neutral
    assert ok


def test_parse_yahoo_quote_summary() -> None:
    payload = {
        "quoteSummary": {
            "result": [
                {
                    "summaryDetail": {"trailingPE": {"raw": 28.5}, "marketCap": {"raw": 3e12}},
                    "defaultKeyStatistics": {"earningsQuarterlyGrowth": {"raw": 0.12}, "priceToBook": {"raw": 40.0}},
                    "financialData": {"revenueGrowth": {"raw": 0.05}, "profitMargins": {"raw": 0.25}, "debtToEquity": {"raw": 150.0}, "returnOnEquity": {"raw": 1.5}, "freeCashflow": 1e11},
                }
            ],
            "error": None,
        }
    }
    snap = parse_yahoo_quote_summary("AAPL", payload)
    assert snap is not None and snap.source == "yahoo"
    assert snap.trailing_pe == 28.5 and snap.eps_growth_pct == pytest.approx(12.0)
    assert snap.revenue_growth_pct == pytest.approx(5.0) and snap.net_margin_pct == pytest.approx(25.0)
    assert snap.debt_to_equity == pytest.approx(1.5) and snap.free_cash_flow == 1e11
    assert parse_yahoo_quote_summary("X", {"quoteSummary": {"error": {"code": "x"}}}) is None
    assert parse_yahoo_quote_summary("X", {"quoteSummary": {"result": []}}) is None


def test_yahoo_fundamentals_cache_avoids_network(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "f.json"
    yf = YahooFundamentals(cache)
    monkeypatch.setattr(yf, "_ensure_crumb", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    assert yf.get("AAPL") is None  # network failure → None, cached as None
    assert cache.is_file()
    yf2 = YahooFundamentals(cache)
    yf2._cache["MSFT"] = FundamentalSnapshot("MSFT", trailing_pe=30.0).to_dict()
    snap = yf2.get("msft")
    assert snap is not None and snap.trailing_pe == 30.0
    assert yf2.get("AAPL") is None
