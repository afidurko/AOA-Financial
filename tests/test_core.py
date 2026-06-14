"""Stdlib-only test suite covering the full pipeline.

Run with:  python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from datetime import date

# Force the deterministic offline analyst so tests never hit the network.
os.environ["AOA_FORCE_OFFLINE"] = "1"

from aoa_financial.config import Config
from aoa_financial.databases.store import MarketStore, Bar
from aoa_financial.ingest.synthetic import SyntheticGenerator
from aoa_financial.ingest.loaders import ingest_ticker
from aoa_financial.analysis import series as S
from aoa_financial.analysis import technical as TA
from aoa_financial.analysis import fundamentals as FA
from aoa_financial.analysis import forecast as FC
from aoa_financial.analysis import regimes as RG
from aoa_financial.analysis import factors as FAC
from aoa_financial.analysis import sentiment as SENT
from aoa_financial.analysis.reverse_engineer import reverse_engineer
from aoa_financial.swarm.decision import analyze_ticker, decide
from aoa_financial.swarm.agents import run_agents


class SeriesTests(unittest.TestCase):
    def test_returns_and_stats(self):
        prices = [100, 110, 121]  # +10% each step
        rets = S.simple_returns(prices)
        self.assertEqual(len(rets), 2)
        self.assertAlmostEqual(rets[0], 0.10, places=6)
        self.assertGreater(S.stdev([1, 2, 3, 4]), 0)

    def test_max_drawdown(self):
        self.assertAlmostEqual(S.max_drawdown([100, 50, 75]), -0.5, places=6)
        self.assertEqual(S.max_drawdown([1, 2, 3]), 0.0)

    def test_ols_recovers_linear(self):
        # y = 3 + 2x exactly -> intercept 3, slope 2, R^2 = 1.
        X = [[1.0, float(x)] for x in range(20)]
        y = [3 + 2 * x for x in range(20)]
        coef, r2 = S.ols(X, y)
        self.assertAlmostEqual(coef[0], 3.0, places=3)
        self.assertAlmostEqual(coef[1], 2.0, places=3)
        self.assertGreater(r2, 0.999)

    def test_sma_ema_lengths(self):
        xs = list(range(1, 51))
        self.assertEqual(len(S.sma(xs, 10)), len(xs))
        self.assertEqual(len(S.ema(xs, 10)), len(xs))
        self.assertIsNotNone(S.sma(xs, 10)[-1])


class SyntheticTests(unittest.TestCase):
    def test_deterministic_and_long(self):
        gen = SyntheticGenerator(epoch_start=date(1960, 6, 1))
        a = gen.generate("TESTX", end=date(2000, 1, 1))
        b = gen.generate("TESTX", end=date(2000, 1, 1))
        self.assertEqual([x.close for x in a.bars], [x.close for x in b.bars])
        self.assertGreater(len(a.bars), 9000)  # decades of trading days
        self.assertTrue(all(bar.high >= bar.low for bar in a.bars))
        self.assertTrue(all(bar.close > 0 for bar in a.bars))

    def test_different_tickers_differ(self):
        gen = SyntheticGenerator()
        a = gen.generate("AAA", end=date(1990, 1, 1))
        b = gen.generate("ZZZ", end=date(1990, 1, 1))
        self.assertNotEqual([x.close for x in a.bars[:50]],
                            [x.close for x in b.bars[:50]])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MarketStore(os.path.join(self.tmp.name, "m.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_ingest_and_roundtrip(self):
        report = ingest_ticker(self.store, "AAPL")
        self.assertGreater(report["bars"], 1000)
        bars = self.store.get_bars("AAPL")
        self.assertEqual(len(bars), report["bars"])
        self.assertIn("AAPL", self.store.list_securities())
        # second call is cached
        again = ingest_ticker(self.store, "AAPL")
        self.assertTrue(again["cached"])

    def test_fundamentals_and_sentiment(self):
        ingest_ticker(self.store, "MSFT")
        self.assertIsNotNone(self.store.latest_fundamentals("MSFT"))
        self.assertIsNotNone(self.store.latest_sentiment("MSFT"))


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = SyntheticGenerator().generate("ANLY", end=date(2020, 1, 1)).bars
        cls.closes = [b.close for b in cls.bars]

    def test_technical_snapshot(self):
        snap = TA.snapshot(self.bars)
        self.assertIsNotNone(snap.rsi_14)
        self.assertTrue(0 <= snap.rsi_14 <= 100)
        self.assertIsNotNone(snap.sma_200)
        self.assertLessEqual(snap.max_drawdown, 0.0)

    def test_fundamentals_score_bounded(self):
        sc = FA.score({"pe_ratio": 8, "revenue_growth": 0.3, "roe": 0.25,
                       "profit_margin": 0.2, "debt_to_equity": 0.3,
                       "free_cash_flow": 2.0, "pb_ratio": 1.0})
        self.assertTrue(-1 <= sc.composite <= 1)
        self.assertGreater(sc.composite, 0)  # high quality should score positive

    def test_forecast_shape(self):
        f = FC.forecast(self.closes, horizon_days=21)
        self.assertLessEqual(f.p10, f.p50)
        self.assertLessEqual(f.p50, f.p90)
        self.assertIn(f.direction, ("up", "down", "flat"))
        self.assertTrue(0 <= f.confidence <= 1)

    def test_regime_valid(self):
        st = RG.classify(self.bars)
        self.assertIn(st.regime, RG.REGIMES)
        self.assertTrue(0 <= st.confidence <= 1)

    def test_factor_model(self):
        fm = FAC.fit(self.bars)
        self.assertIn("momentum", fm.factors)
        self.assertTrue(0 <= fm.r_squared <= 1)
        self.assertAlmostEqual(sum(fm.contributions.values()), 1.0, places=3)

    def test_sentiment_lexicon(self):
        self.assertGreater(SENT.score_text("record profit and strong growth"), 0)
        self.assertLess(SENT.score_text("massive loss amid fraud probe"), 0)
        # negation handling
        self.assertLessEqual(SENT.score_text("not strong, missed estimates"), 0)

    def test_reverse_engineer(self):
        res = reverse_engineer("ANLY", self.bars)
        self.assertTrue(-1 <= res.forward_bias <= 1)
        self.assertEqual(len(res.dominant_drivers), 3)
        self.assertTrue(res.inferences and res.assumptions)


class SwarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MarketStore(os.path.join(self.tmp.name, "m.db"))
        ingest_ticker(self.store, "JPM")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_full_pipeline_persists(self):
        d = analyze_ticker(self.store, "JPM", run_id="t1")
        self.assertIn(d.action, ("BUY", "HOLD", "SELL"))
        self.assertTrue(-1 <= d.conviction <= 1)
        self.assertTrue(0 <= d.confidence <= 1)
        self.assertTrue(0 <= d.target_weight <= 0.15)
        self.assertTrue(any(s.agent == "llm" for s in d.signals))
        rows = self.store.get_decisions("t1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "JPM")

    def test_decide_aggregation(self):
        sigs = run_agents(
            technical={"golden_cross": True, "rsi_14": 45, "macd_hist": 0.02,
                       "mom_252d": 0.2, "annualized_vol": 0.25},
            fundamental={"composite": 0.5, "notes": ["strong growth"]},
            forecast={"expected_return": 0.05, "confidence": 0.6,
                      "horizon_days": 21, "direction": "up"},
            regime={"regime": "bull", "regime_confidence": 0.8},
            sentiment=0.4,
            analyst={"conviction": 0.6, "confidence": 0.7, "thesis": "x"})
        d = decide("TEST", sigs)
        self.assertEqual(d.action, "BUY")
        self.assertGreater(d.conviction, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
