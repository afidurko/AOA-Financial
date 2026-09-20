#!/usr/bin/env python3
"""Mass stress/fuzz campaign for the crypto + connectome + swarm lane.

Runs randomized property checks against every invariant the lane promises:

  bracket    — bracket math: target/stop geometry for fuzzed prices & policies
  features   — feature extraction stays finite/bounded on hostile tapes
  backtest   — accounting identity, bracket bounds, curve integrity on random tapes
  deep       — DeepMLP / GatedReservoir: finite params, round-trip equality
  connectome — random graphs: finite potentials, plasticity caps, round-trips
  survival   — first-passage bookkeeping identity (opens == resolved + pending)
  ensemble   — Hedge weights normalized/finite, persistence stability
  history    — merge ordering / earliest-source-wins under fuzz

Every individual assertion is counted as one check. Usage:

  python3 scripts/crypto_stress.py --scale 1        # quick (~1 min)
  python3 scripts/crypto_stress.py --scale 50       # big campaign
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import tempfile
import time
from datetime import date, timedelta

sys.path.insert(0, "src")

from aoa.connectome.engine import Connectome  # noqa: E402
from aoa.crypto.assets import get_asset  # noqa: E402
from aoa.crypto.backtest import BracketPolicy, CryptoBacktester  # noqa: E402
from aoa.crypto.deep import DeepMLP, GatedReservoir  # noqa: E402
from aoa.crypto.history import DailyCandle, merge_histories  # noqa: E402
from aoa.crypto.survival import BracketSurvival  # noqa: E402
from aoa.crypto.traders import HedgeEnsemble  # noqa: E402
from aoa.crypto.training import DayByDayTrainer, extract_features  # noqa: E402

CHECKS = 0
FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILURES.append(msg)
        if len(FAILURES) <= 25:
            print(f"  FAIL: {msg}", flush=True)


def _finite(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def random_tape(rng: random.Random, n: int, *, hostile: bool = False) -> list[DailyCandle]:
    """A random daily tape; hostile mode injects gaps, crashes, and spikes."""
    day0 = date(2015, 1, 1)
    price = rng.uniform(0.01, 50_000)
    candles: list[DailyCandle] = []
    day = day0
    for _ in range(n):
        drift = rng.gauss(0.0005, 0.04)
        if hostile and rng.random() < 0.02:
            drift = rng.choice([-0.6, -0.4, 0.5, 1.5])  # crash / moon day
        price = max(1e-6, price * (1 + drift))
        span = abs(rng.gauss(0.0, 0.03)) + (0.15 if hostile and rng.random() < 0.05 else 0.0)
        gap = rng.gauss(0.0, 0.05) if hostile else rng.gauss(0.0, 0.005)
        o = max(1e-6, price * (1 + gap))
        hi = max(o, price) * (1 + span)
        lo = min(o, price) * (1 - span)
        candles.append(
            DailyCandle(day=day, open=o, high=hi, low=lo, close=price, volume=rng.uniform(0, 1e6))
        )
        day += timedelta(days=1 if not hostile or rng.random() > 0.03 else rng.randint(2, 9))
    return candles


# --------------------------------------------------------------------- suites
def suite_bracket(rng: random.Random, iters: int) -> None:
    for _ in range(iters):
        tp = rng.uniform(0.01, 3.0)
        sl = rng.uniform(0.01, 0.99)
        price = rng.uniform(1e-6, 1e7)
        br = BracketPolicy(take_profit_pct=tp, stop_loss_pct=sl).attach(price)
        check(br.take_profit > price, f"target not above entry (tp={tp}, p={price})")
        check(br.stop_loss < price, f"stop not below entry (sl={sl}, p={price})")
        check(
            abs(br.take_profit / price - (1 + tp)) < 1e-9
            and abs(br.stop_loss / price - (1 - sl)) < 1e-9,
            "bracket arithmetic drift",
        )


def suite_features(rng: random.Random, iters: int) -> None:
    for it in range(iters):
        tape = random_tape(rng, rng.randint(2, 160), hostile=True)
        idx = rng.randint(1, len(tape) - 1)
        feats = extract_features(tape, idx)
        if feats is None:
            check(idx < 1, "features None for valid index")
            continue
        vec = feats.vector()
        check(all(_finite(v) for v in vec), f"non-finite feature vector (iter {it})")
        check(all(-1.0 - 1e-9 <= v <= 1.0 + 1e-9 for v in vec), f"feature out of bounds (iter {it})")
        check(0.0 <= feats.vol_shock <= 1.0, "vol_shock out of range")
        check(0.0 <= feats.drawdown <= 1.0, "drawdown out of range")
        check(0.0 <= feats.capitulation <= 1.0, "capitulation out of range")


def suite_backtest(rng: random.Random, iters: int) -> None:
    asset = get_asset("BTC")
    for it in range(iters):
        tape = random_tape(rng, rng.randint(80, 400), hostile=(it % 2 == 0))
        with tempfile.TemporaryDirectory() as td:
            trainer = DayByDayTrainer(asset, model_dir=td)
            bt = CryptoBacktester(asset, warmup_days=30)
            try:
                result = bt.run(tape, trainer, start=tape[0].day)
            except ValueError:
                check(len(tape) < 32, f"unexpected ValueError on {len(tape)} candles")
                continue
        check(
            abs(result.ending_equity - result.starting_cash * (1 + result.total_return_pct / 100))
            < 1e-6 * max(1.0, result.ending_equity),
            f"accounting identity broken (iter {it})",
        )
        check(len(result.equity_curve) == result.market_days, "equity curve length mismatch")
        check(result.ending_equity >= 0, f"negative equity (iter {it})")
        check(_finite(result.ending_equity), "non-finite equity")
        tp_pct = result.policy.take_profit_pct * 100
        sl_pct = result.policy.stop_loss_pct * 100
        for t in result.trades:
            check(t.exit_day >= t.entry_day, "exit before entry")
            check(_finite(t.return_pct), "non-finite trade return")
            if t.exit_reason == "take-profit":
                # Gap-ups may fill above the target (at the open), never below.
                check(
                    t.return_pct >= tp_pct - 0.01,
                    f"take-profit fill below target: {t.return_pct:.2f}% (iter {it})",
                )
            elif t.exit_reason == "stop-loss":
                # Gap-downs may fill below the stop (at the open), never above.
                check(
                    t.return_pct <= -sl_pct + 0.01,
                    f"stop-loss fill better than stop: {t.return_pct:.2f}% (iter {it})",
                )


def suite_deep(rng: random.Random, iters: int) -> None:
    for it in range(iters):
        n_in = rng.randint(1, 24)
        hidden = [rng.randint(1, 24) for _ in range(rng.randint(0, 3))]
        net = DeepMLP([n_in, *hidden, 1], seed=rng.randint(0, 10**6))
        for _ in range(30):
            x = [rng.gauss(0, 1) for _ in range(n_in)]
            net.train_step(x, rng.gauss(0, 0.5), lr=0.02)
        x = [rng.gauss(0, 1) for _ in range(n_in)]
        p = net.predict(x)
        check(_finite(p), f"MLP non-finite prediction (iter {it})")
        clone = DeepMLP.from_dict(net.to_dict())
        check(abs(clone.predict(x) - p) < 1e-12, "MLP round-trip mismatch")

        res = GatedReservoir(n_in, n_state=rng.randint(1, 20), seed=rng.randint(0, 10**6))
        for _ in range(30):
            res.train_step([rng.gauss(0, 1) for _ in range(n_in)], rng.gauss(0, 0.5), lr=0.02)
        p2 = res.predict(x)
        check(_finite(p2), f"reservoir non-finite prediction (iter {it})")
        clone2 = GatedReservoir.from_dict(res.to_dict())
        check(abs(clone2.predict(x) - p2) < 1e-9, "reservoir round-trip mismatch")
        check(all(_finite(s) for s in res.state), "reservoir state non-finite")


def suite_connectome(rng: random.Random, iters: int) -> None:
    for it in range(iters):
        n = rng.randint(2, 14)
        names = [f"N{i}" for i in range(n)]
        wiring = {
            pre: {
                post: rng.uniform(-20, 20)
                for post in rng.sample(names, k=rng.randint(1, min(4, n)))
            }
            for pre in rng.sample(names, k=rng.randint(1, n))
        }
        present = sorted({p for p in wiring} | {q for posts in wiring.values() for q in posts})
        motor = {"go": tuple(rng.sample(present, k=rng.randint(1, len(present))))}
        net = Connectome(wiring, motor_groups=motor, threshold=rng.uniform(5, 60))
        baseline = {k: dict(v) for k, v in net.synapses.items()}
        for _ in range(5):
            stim = {rng.choice(present): rng.uniform(0, 100) for _ in range(rng.randint(1, 4))}
            ro = net.run(stim, steps=rng.randint(1, 20))
            check(all(_finite(d) for d in ro.drives.values()), "non-finite motor drive")
            check(all(d >= 0 for d in ro.drives.values()), "negative motor drive")
            net.reward(rng.uniform(-1, 1), lr=rng.uniform(0.01, 0.5))
        for pre, posts in net.synapses.items():
            for post, w in posts.items():
                w0 = abs(baseline[pre][post])
                check(_finite(w), "non-finite synapse weight")
                check(
                    abs(w) <= w0 * 3.0 + 1e-6,
                    f"plasticity cap exceeded: |{w:.3f}| > 3×{w0:.3f} (iter {it})",
                )
        clone = Connectome.from_dict(net.to_dict())
        check(clone.synapses == net.synapses, "connectome round-trip mismatch")


def suite_survival(rng: random.Random, iters: int) -> None:
    for it in range(iters):
        surv = BracketSurvival(horizon_days=rng.randint(5, 90))
        tape = random_tape(rng, rng.randint(60, 200), hostile=True)
        opened = 0
        for i in range(30, len(tape)):
            feats = extract_features(tape, i)
            surv.observe_candle(tape[i])
            if feats is not None:
                surv.open_virtual(feats, tape[i].close)
                opened += 1
        resolved = sum(s["tp"] + s["sl"] + s["censored"] for s in surv.outcomes.values())
        pending = len(surv._pending)
        check(resolved + pending == opened, f"survival bookkeeping broken (iter {it})")
        clone = BracketSurvival.from_dict(surv.to_dict())
        check(clone.outcomes == surv.outcomes, "survival round-trip mismatch")


def suite_ensemble(rng: random.Random, iters: int) -> None:
    asset = get_asset("BTC")
    for it in range(iters):
        tape = random_tape(rng, rng.randint(80, 250), hostile=(it % 3 == 0))
        with tempfile.TemporaryDirectory() as td:
            ens = HedgeEnsemble(asset, model_dir=td)
            ens.train(tape, save=True)
            total = sum(ens.weights.values())
            check(abs(total - 1.0) < 1e-6, f"weights not normalized: {total} (iter {it})")
            check(all(_finite(w) and w >= 0 for w in ens.weights.values()), "bad weight")
            feats = extract_features(tape, len(tape) - 2)
            if feats is not None:
                a1, c1 = ens.decide(feats)
                a2, c2 = HedgeEnsemble(asset, model_dir=td).decide(feats)
                check(a1 == a2, f"ensemble resume action drift: {a1} vs {a2} (iter {it})")
                check(abs(c1 - c2) < 1e-9, f"ensemble resume conviction drift (iter {it})")


def suite_history(rng: random.Random, iters: int) -> None:
    for it in range(iters):
        tapes = [random_tape(rng, rng.randint(1, 50)) for _ in range(rng.randint(1, 4))]
        merged = merge_histories(*tapes)
        days = [c.day for c in merged]
        check(days == sorted(set(days)), f"merge not sorted/unique (iter {it})")
        earliest = min((t[0].day, i) for i, t in enumerate(tapes))[1]
        for c in tapes[earliest]:
            m = next((x for x in merged if x.day == c.day), None)
            check(m is not None and m.close == c.close, "earliest source did not win")


SUITES = {
    "bracket": (suite_bracket, 20_000),
    "features": (suite_features, 400),
    "backtest": (suite_backtest, 30),
    "deep": (suite_deep, 120),
    "connectome": (suite_connectome, 150),
    "survival": (suite_survival, 60),
    "ensemble": (suite_ensemble, 6),
    "history": (suite_history, 400),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="Iteration multiplier per suite.")
    ap.add_argument("--seed", type=int, default=None, help="Base RNG seed (default: random).")
    ap.add_argument("--only", default="", help="Comma list of suites to run.")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.SystemRandom().randint(0, 2**31)
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    t0 = time.time()
    print(f"crypto stress campaign — scale={args.scale} seed={seed}", flush=True)
    for name, (fn, base_iters) in SUITES.items():
        if only and name not in only:
            continue
        iters = max(1, int(base_iters * args.scale))
        rng = random.Random(seed ^ hash(name) & 0x7FFFFFFF)
        n0, f0, s0 = CHECKS, len(FAILURES), time.time()
        fn(rng, iters)
        print(
            f"  {name:<11} iters={iters:>8,} checks={CHECKS - n0:>12,} "
            f"failures={len(FAILURES) - f0:>3} ({time.time() - s0:.1f}s)",
            flush=True,
        )
    dt = time.time() - t0
    print(f"\nTOTAL: {CHECKS:,} checks, {len(FAILURES)} failures in {dt:,.1f}s", flush=True)
    if FAILURES:
        print("first failures:")
        for f in FAILURES[:25]:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
