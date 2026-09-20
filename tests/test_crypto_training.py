"""Day-by-day trainer, pattern memory, and persistence tests (offline)."""

from __future__ import annotations

import math
from datetime import date, timedelta

from aoa.crypto.assets import get_asset
from aoa.crypto.history import DailyCandle
from aoa.crypto.training import (
    N_FEATURES,
    DayByDayTrainer,
    PatternMemory,
    extract_features,
)


def _tape(day0: date, closes: list[float]) -> list[DailyCandle]:
    return [
        DailyCandle(
            day=day0 + timedelta(days=i),
            open=c * 0.995,
            high=c * 1.01,
            low=c * 0.985,
            close=c,
            volume=50.0,
            source="test",
        )
        for i, c in enumerate(closes)
    ]


def _trending_tape(n: int = 400, *, up: bool = True) -> list[DailyCandle]:
    """A deterministic trending series with a mild wobble."""
    closes: list[float] = []
    price = 100.0
    for i in range(n):
        drift = 0.004 if up else -0.004
        wobble = 0.006 * math.sin(i / 3.0)
        price *= 1.0 + drift + wobble
        closes.append(price)
    return _tape(date(2016, 1, 1), closes)


class TestFeatures:
    def test_no_lookahead_features_match_prefix(self):
        tape = _trending_tape(120)
        full = extract_features(tape, 100)
        prefix = extract_features(tape[:101], 100)
        assert full == prefix

    def test_vector_shape_and_bounds(self):
        tape = _trending_tape(120)
        feats = extract_features(tape, 100)
        vec = feats.vector()
        assert len(vec) == N_FEATURES
        assert all(-1.0 <= v <= 1.0 for v in vec)

    def test_streak_sign_tracks_direction(self):
        up = _tape(date(2020, 1, 1), [1, 2, 3, 4, 5, 6])
        down = _tape(date(2020, 1, 1), [6, 5, 4, 3, 2, 1])
        assert extract_features(up, 5).streak > 0
        assert extract_features(down, 5).streak < 0


class TestPatternMemory:
    def test_observe_accumulates_and_round_trips(self):
        tape = _trending_tape(150)
        mem = PatternMemory(asset="BTC")
        for i in range(50, 149):
            feats = extract_features(tape, i)
            next_ret = tape[i + 1].close / tape[i].close - 1.0
            mem.observe(feats, next_ret)
        assert mem.market_days == 99
        clone = PatternMemory.from_dict(mem.to_dict())
        assert clone.to_dict() == mem.to_dict()
        assert clone.summary()["market_days"] == 99

    def test_edge_requires_evidence(self):
        mem = PatternMemory(asset="BTC")
        tape = _trending_tape(120)
        feats = extract_features(tape, 100)
        assert mem.edge(feats) == 0.0  # empty memory has no opinion


class TestTrainer:
    def test_training_walks_the_full_calendar(self, tmp_path):
        asset = get_asset("BTC")
        tape = _tape(date(2010, 7, 18), [0.07 * (1.01**i) for i in range(200)])
        trainer = DayByDayTrainer(asset, model_dir=tmp_path)
        report = trainer.train(tape, start=date(2007, 7, 17))
        assert report.days_walked == (tape[-1].day - date(2007, 7, 17)).days + 1
        assert report.pre_genesis_days > 0
        assert report.pre_market_days > 0
        assert report.market_days == 200
        assert report.adapter_updates > 150

    def test_head_learns_a_persistent_uptrend(self, tmp_path):
        asset = get_asset("ETH")
        tape = _trending_tape(400, up=True)
        trainer = DayByDayTrainer(asset, model_dir=tmp_path)
        trainer.train(tape, start=tape[0].day)
        feats = extract_features(tape, len(tape) - 1)
        assert trainer.predict(feats) > 0  # learned the drift

    def test_state_persists_and_resumes(self, tmp_path):
        asset = get_asset("BTC")
        tape = _trending_tape(300)
        first = DayByDayTrainer(asset, model_dir=tmp_path)
        first.train(tape, start=tape[0].day)
        market_days = first.memory.market_days

        resumed = DayByDayTrainer(asset, model_dir=tmp_path)
        assert resumed.memory.market_days == market_days
        feats = extract_features(tape, len(tape) - 1)
        assert abs(resumed.predict(feats) - first.predict(feats)) < 1e-9

    def test_combined_signal_returns_valid_action(self, tmp_path):
        asset = get_asset("BTC")
        tape = _trending_tape(300)
        trainer = DayByDayTrainer(asset, model_dir=tmp_path)
        trainer.train(tape, start=tape[0].day)
        feats = extract_features(tape, len(tape) - 1)
        action, conviction = trainer.combined_signal(feats)
        assert action in {"buy", "sell", "hold"}
        assert 0.0 <= conviction <= 1.0
