"""Deep models, survival gate, trader swarm, and Hedge ensemble tests (offline)."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pytest

from aoa.crypto.assets import get_asset
from aoa.crypto.backtest import CryptoBacktester
from aoa.crypto.deep import DeepMLP, GatedReservoir
from aoa.crypto.history import DailyCandle
from aoa.crypto.survival import BracketSurvival, regime_key
from aoa.crypto.traders import (
    ARTrader,
    BaseTrader,
    DeepMLPTrader,
    HedgeEnsemble,
    MomentumHeadTrader,
    PairsTrader,
    ReservoirTrader,
    default_roster,
)
from aoa.crypto.training import extract_features


def _tape(day0: date, closes: list[float], *, span: float = 0.015) -> list[DailyCandle]:
    return [
        DailyCandle(
            day=day0 + timedelta(days=i),
            open=c * (1 - span / 3),
            high=c * (1 + span),
            low=c * (1 - span),
            close=c,
            volume=10.0,
            source="test",
        )
        for i, c in enumerate(closes)
    ]


def _trend_tape(n: int = 400, *, drift: float = 0.005) -> list[DailyCandle]:
    closes, price = [], 100.0
    for i in range(n):
        price *= 1.0 + drift + 0.004 * math.sin(i / 5.0)
        closes.append(price)
    return _tape(date(2016, 1, 1), closes)


class TestDeepMLP:
    def test_learns_a_nonlinear_function(self):
        net = DeepMLP([2, 10, 6, 1], seed=1)
        rng = random.Random(0)
        for _ in range(4000):
            x0 = rng.uniform(-1, 1)
            net.train_step([x0, 1.0], math.sin(2 * x0), lr=0.02)
        errs = [
            abs(net.predict([x0, 1.0]) - math.sin(2 * x0))
            for x0 in [i / 10 - 1 for i in range(21)]
        ]
        assert sum(errs) / len(errs) < 0.08

    def test_deterministic_by_seed_and_round_trips(self):
        a, b = DeepMLP([3, 5, 1], seed=9), DeepMLP([3, 5, 1], seed=9)
        assert a.predict([0.1, -0.2, 0.5]) == b.predict([0.1, -0.2, 0.5])
        clone = DeepMLP.from_dict(a.to_dict())
        assert clone.predict([0.1, -0.2, 0.5]) == a.predict([0.1, -0.2, 0.5])

    def test_rejects_bad_shapes(self):
        with pytest.raises(ValueError):
            DeepMLP([3])
        net = DeepMLP([3, 4, 1])
        with pytest.raises(ValueError):
            net.predict([1.0, 2.0])


class TestGatedReservoir:
    def test_error_shrinks_on_autoregressive_signal(self):
        res = GatedReservoir(2, n_state=10, seed=3)
        prev, errs = 0.0, []
        for t in range(4000):
            nxt = 0.8 * prev + 0.1 * math.sin(t / 7)
            errs.append(abs(res.train_step([prev, 1.0], nxt, lr=0.02)))
            prev = nxt
        assert sum(errs[-100:]) / 100 < 0.5 * (sum(errs[:100]) / 100)

    def test_predict_does_not_mutate_state(self):
        res = GatedReservoir(2, n_state=6, seed=1)
        res.train_step([0.5, 1.0], 0.2)
        state = list(res.state)
        res.predict([0.3, 1.0])
        assert res.state == state

    def test_round_trip_preserves_predictions(self):
        res = GatedReservoir(3, n_state=8, seed=5)
        for i in range(50):
            res.train_step([math.sin(i / 3), 0.1, 1.0], math.sin((i + 1) / 3), lr=0.02)
        clone = GatedReservoir.from_dict(res.to_dict())
        x = [0.4, 0.1, 1.0]
        assert clone.predict(x) == pytest.approx(res.predict(x))


class TestBracketSurvival:
    def test_tracks_first_passage_outcomes(self):
        tape = _trend_tape(200, drift=0.01)  # strong bull → target hit first
        surv = BracketSurvival()
        for i in range(60, len(tape)):
            feats = extract_features(tape, i)
            surv.observe_candle(tape[i])
            surv.open_virtual(feats, tape[i].close)
        total_tp = sum(s["tp"] for s in surv.outcomes.values())
        total_sl = sum(s["sl"] for s in surv.outcomes.values())
        assert total_tp > 0
        assert total_sl == 0  # a +1%/day tape never falls 26%

    def test_gate_blocks_hostile_regimes_only_with_evidence(self):
        surv = BracketSurvival()
        tape = _trend_tape(120)
        feats = extract_features(tape, 100)
        assert surv.allows(feats)  # no history → open
        key = regime_key(feats)
        surv.outcomes[key] = {"tp": 1, "sl": 30, "censored": 0}
        assert not surv.allows(feats)  # ample losing history → closed

    def test_round_trip(self):
        surv = BracketSurvival()
        tape = _trend_tape(150)
        for i in range(60, len(tape)):
            feats = extract_features(tape, i)
            surv.observe_candle(tape[i])
            surv.open_virtual(feats, tape[i].close)
        clone = BracketSurvival.from_dict(surv.to_dict())
        assert clone.outcomes == surv.outcomes
        assert clone.to_dict() == surv.to_dict()


class TestTraders:
    def test_default_roster_is_a_real_swarm(self):
        roster = default_roster(get_asset("BTC"))
        assert len(roster) >= 7
        names = [t.name for t in roster]
        assert len(set(names)) == len(names)
        assert all(isinstance(t, BaseTrader) for t in roster)

    def test_each_trader_decides_and_learns(self):
        tape = _trend_tape(300)
        feats = extract_features(tape, 250)
        next_ret = tape[251].close / tape[250].close - 1.0
        for trader in default_roster(get_asset("BTC")):
            action, conviction = trader.decide(feats)
            assert action in {"buy", "sell", "hold"}
            assert 0.0 <= conviction <= 1.0
            trader.learn(feats, next_ret)  # must not raise

    def test_pairs_trader_mean_reverts(self):
        trader = PairsTrader("ETH", window=30)
        # Stable ratio, then this asset gets suddenly cheap vs its partner.
        for _ in range(60):
            trader.update_pair(100.0, 100.0)
        tape = _trend_tape(120)
        feats = extract_features(tape, 100)
        trader.update_pair(70.0, 100.0)  # sharply cheap
        action, conviction = trader.decide(feats)
        assert action == "buy" and conviction > 0

    def test_trader_state_round_trips(self):
        tape = _trend_tape(300)
        feats = extract_features(tape, 250)
        for fresh, trained in [
            (MomentumHeadTrader(), MomentumHeadTrader()),
            (DeepMLPTrader(), DeepMLPTrader()),
            (ReservoirTrader(), ReservoirTrader()),
            (ARTrader(), ARTrader()),
        ]:
            for i in range(200, 250):
                f = extract_features(tape, i)
                trained.learn(f, tape[i + 1].close / tape[i].close - 1.0)
            fresh.load_state(trained.state_dict())
            assert fresh.decide(feats) == trained.decide(feats)


class TestHedgeEnsemble:
    def test_weights_flow_to_the_better_trader(self, tmp_path):
        class Bull(BaseTrader):
            name = "always-bull"

            def decide(self, feats):
                return "buy", 1.0

            def learn(self, feats, next_ret):
                pass

        class Bear(BaseTrader):
            name = "always-bear"

            def decide(self, feats):
                return "sell", 1.0

            def learn(self, feats, next_ret):
                pass

        ensemble = HedgeEnsemble(
            get_asset("BTC"), roster=[Bull(), Bear()], model_dir=tmp_path
        )
        tape = _trend_tape(300, drift=0.008)  # relentless bull
        ensemble.train(tape, save=False)
        assert ensemble.weights["always-bull"] > 0.75
        assert ensemble.weights["always-bear"] < 0.25

    def test_duplicate_names_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            HedgeEnsemble(
                get_asset("BTC"),
                roster=[MomentumHeadTrader(), MomentumHeadTrader()],
                model_dir=tmp_path,
            )

    def test_survival_gate_vetoes_buys(self, tmp_path):
        ensemble = HedgeEnsemble(get_asset("BTC"), model_dir=tmp_path)
        tape = _trend_tape(300)
        feats = extract_features(tape, 250)
        ensemble.survival.outcomes[regime_key(feats)] = {"tp": 0, "sl": 40, "censored": 0}
        decision = ensemble.decide_full(feats)
        assert not decision.gate_open
        assert decision.action != "buy"

    def test_state_persists_and_resumes(self, tmp_path):
        asset = get_asset("BTC")
        tape = _trend_tape(300)
        first = HedgeEnsemble(asset, model_dir=tmp_path)
        first.train(tape)
        resumed = HedgeEnsemble(asset, model_dir=tmp_path)
        assert resumed.days_learned == first.days_learned
        assert resumed.weights == pytest.approx(first.weights)
        feats = extract_features(tape, 250)
        assert resumed.decide(feats) == first.decide(feats)

    def test_ensemble_drives_the_backtester(self, tmp_path):
        asset = get_asset("BTC")
        tape = _trend_tape(500)
        ensemble = HedgeEnsemble(asset, model_dir=tmp_path)
        bt = CryptoBacktester(asset)
        result = bt.run(tape, ensemble, start=tape[0].day)
        assert result.market_days == 500
        for trade in result.trades:
            assert -26.5 <= trade.return_pct <= 32.5  # bracket still structural
