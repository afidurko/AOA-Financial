"""Crypto history store, merging, and calendar-walk tests (offline)."""

from __future__ import annotations

from datetime import date, timedelta

from aoa.crypto.assets import ASSETS, TRAINING_EPOCH, get_asset
from aoa.crypto.history import (
    CalendarDay,
    DailyCandle,
    HistoryStore,
    calendar_walk,
    merge_histories,
)


def _candle(day: date, close: float, source: str = "test") -> DailyCandle:
    return DailyCandle(
        day=day,
        open=close * 0.99,
        high=close * 1.02,
        low=close * 0.97,
        close=close,
        volume=100.0,
        source=source,
    )


def _run(day0: date, closes: list[float], source: str = "test") -> list[DailyCandle]:
    return [_candle(day0 + timedelta(days=i), c, source) for i, c in enumerate(closes)]


class TestAssets:
    def test_registry_contains_the_four_core_assets(self):
        assert set(ASSETS) == {"BTC", "ETH", "SOL", "XRP"}

    def test_epoch_predates_every_asset(self):
        assert TRAINING_EPOCH == date(2007, 7, 17)
        for asset in ASSETS.values():
            assert asset.first_market > TRAINING_EPOCH
            if asset.genesis:
                assert asset.genesis <= asset.first_market

    def test_get_asset_is_case_insensitive_and_raises_on_unknown(self):
        assert get_asset("btc").code == "BTC"
        try:
            get_asset("DOGE")
            raise AssertionError("expected KeyError")
        except KeyError:
            pass


class TestMerge:
    def test_earliest_source_wins_on_conflict(self):
        early = _run(date(2020, 1, 1), [1.0, 2.0, 3.0], source="early")
        late = _run(date(2020, 1, 2), [20.0, 30.0, 40.0], source="late")
        merged = merge_histories(late, early)
        by_day = {c.day: c for c in merged}
        assert by_day[date(2020, 1, 2)].source == "early"
        assert by_day[date(2020, 1, 4)].source == "late"
        assert [c.day for c in merged] == sorted(c.day for c in merged)

    def test_merge_handles_empty(self):
        assert merge_histories([], []) == []


class TestStore:
    def test_save_load_round_trip(self, tmp_path):
        store = HistoryStore(tmp_path)
        asset = get_asset("BTC")
        candles = _run(date(2015, 1, 1), [100.0, 110.0, 105.0])
        store.save(asset, candles)
        loaded = store.load(asset)
        assert loaded == candles

    def test_load_missing_returns_empty(self, tmp_path):
        store = HistoryStore(tmp_path)
        assert store.load(get_asset("SOL")) == []


class TestCalendarWalk:
    def test_walk_labels_pre_genesis_pre_market_and_gaps(self):
        asset = get_asset("BTC")  # genesis 2009-01-03, first market 2010-07-17
        candles = [
            _candle(date(2010, 7, 18), 0.07),
            # 2010-07-19 missing → gap
            _candle(date(2010, 7, 20), 0.08),
        ]
        days = list(
            calendar_walk(asset, candles, start=date(2008, 12, 31), end=date(2010, 7, 20))
        )
        by_day = {d.day: d for d in days}
        assert by_day[date(2008, 12, 31)].status == "pre-genesis"
        assert by_day[date(2009, 6, 1)].status == "pre-market"
        assert by_day[date(2010, 7, 16)].status == "pre-market"
        assert by_day[date(2010, 7, 18)].status == "market"
        assert by_day[date(2010, 7, 19)].status == "gap"
        assert by_day[date(2010, 7, 20)].status == "market"
        # Every calendar day is present exactly once.
        assert len(days) == (date(2010, 7, 20) - date(2008, 12, 31)).days + 1

    def test_walk_from_epoch_counts_the_whole_preera(self):
        asset = get_asset("BTC")
        candles = [_candle(date(2010, 7, 18), 0.07)]
        days = list(calendar_walk(asset, candles, end=date(2010, 7, 18)))
        assert days[0] == CalendarDay(day=TRAINING_EPOCH, candle=None, status="pre-genesis")
        statuses = {d.status for d in days}
        assert statuses == {"pre-genesis", "pre-market", "market"}
