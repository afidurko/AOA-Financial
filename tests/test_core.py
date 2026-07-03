"""Stdlib-only test suite covering the full pipeline.

Run with:  python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from datetime import date

# Force the deterministic offline analyst so tests never hit the network.
os.environ["AOA_FORCE_OFFLINE"] = "1"

from aoa_financial.analysis import factors as FAC
from aoa_financial.analysis import forecast as FC
from aoa_financial.analysis import fundamentals as FA
from aoa_financial.analysis import regimes as RG
from aoa_financial.analysis import sentiment as SENT
from aoa_financial.analysis import series as S
from aoa_financial.analysis import technical as TA
from aoa_financial.analysis.reverse_engineer import reverse_engineer
from aoa_financial.databases.store import MarketStore
from aoa_financial.ingest.loaders import ingest_ticker
from aoa_financial.ingest.synthetic import SyntheticGenerator
from aoa_financial.swarm.agents import run_agents
from aoa_financial.swarm.decision import analyze_ticker, decide


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


class BackendParityTests(unittest.TestCase):
    """The numpy and pure-Python numeric backends must agree."""

    def setUp(self):
        from aoa_financial.analysis import _backend as B
        self.B = B
        if not B.HAS_NUMPY:
            self.skipTest("numpy not installed; only pure-Python path available")
        self.prices = [b.close for b in
                       SyntheticGenerator().generate("PAR", end=date(1985, 1, 1)).bars]

    def _pure(self, fn, *a, **k):
        # Run a series.py function with numpy disabled to get the pure path.
        from aoa_financial.analysis import _backend as B
        saved = B.HAS_NUMPY
        B.HAS_NUMPY = False
        try:
            return fn(*a, **k)
        finally:
            B.HAS_NUMPY = saved

    def test_log_returns_parity(self):
        npv = S.log_returns(self.prices)
        pure = self._pure(S.log_returns, self.prices)
        self.assertEqual(len(npv), len(pure))
        for x, y in zip(npv[:200], pure[:200], strict=False):
            self.assertAlmostEqual(x, y, places=9)

    def test_stdev_parity(self):
        rets = S.log_returns(self.prices)
        self.assertAlmostEqual(S.stdev(rets), self._pure(S.stdev, rets), places=9)

    def test_sma_ema_parity(self):
        for fn in (S.sma, S.ema):
            npv = fn(self.prices, 50)
            pure = self._pure(fn, self.prices, 50)
            self.assertEqual(len(npv), len(pure))
            self.assertAlmostEqual(npv[-1], pure[-1], places=6)

    def test_factor_panel_parity(self):
        from aoa_financial.analysis import factors as FAC
        from aoa_financial.ingest.synthetic import SyntheticGenerator
        bars = SyntheticGenerator().generate("FPAR", end=date(2010, 1, 1)).bars
        npp = FAC.build_factor_panel(bars)
        pure = self._pure(FAC.build_factor_panel, bars)
        self.assertEqual(set(npp), set(pure))
        for col in npp:
            self.assertEqual(len(npp[col]), len(pure[col]))
            for a, b2 in zip(npp[col][:500], pure[col][:500], strict=False):
                self.assertAlmostEqual(a, b2, places=9)

    def test_ols_parity(self):
        X = [[1.0, float(i), float(i * i)] for i in range(120)]
        y = [2 + 0.5 * i - 0.01 * i * i for i in range(120)]
        cnp, r2np = S.ols(X, y)
        cpu, r2pu = self._pure(S.ols, X, y)
        for a, b2 in zip(cnp, cpu, strict=False):
            self.assertAlmostEqual(a, b2, places=4)
        self.assertAlmostEqual(r2np, r2pu, places=6)


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


class PandasTests(unittest.TestCase):
    """The vectorised pandas indicator suite must agree with technical.py."""

    @classmethod
    def setUpClass(cls):
        from aoa_financial.analysis import frames as FR
        cls.FR = FR
        if not FR.HAS_PANDAS:
            raise unittest.SkipTest("pandas not installed")
        cls.bars = SyntheticGenerator().generate("PDX", end=date(2015, 1, 1)).bars
        cls.df = FR.bars_to_frame(cls.bars)

    def test_roundtrip(self):
        bars2 = self.FR.frame_to_bars(self.df)
        self.assertEqual(len(bars2), len(self.bars))
        self.assertEqual(bars2[0].date, self.bars[0].date)
        self.assertAlmostEqual(bars2[-1].close, self.bars[-1].close, places=4)

    def test_indicator_parity_with_scalar(self):
        snap = TA.snapshot(self.bars)
        ind = self.FR.indicator_frame(self.df)
        last = self.FR.latest_indicators(self.df)
        # Exact rolling stats.
        self.assertAlmostEqual(last["sma_50"], snap.sma_50, places=6)
        self.assertAlmostEqual(last["sma_200"], snap.sma_200, places=6)
        self.assertAlmostEqual(last["mom_252"], snap.mom_252d, places=6)
        self.assertEqual(bool(last["golden_cross"]), bool(snap.golden_cross))
        # Recursive indicators converge over a long series.
        self.assertAlmostEqual(last["rsi_14"], snap.rsi_14, places=3)
        self.assertAlmostEqual(last["macd_hist"], snap.macd_hist, places=3)
        self.assertAlmostEqual(last["bb_pct_b"], snap.bollinger_pct_b, places=4)
        self.assertAlmostEqual(last["atr_14"], snap.atr_14, places=2)
        self.assertAlmostEqual(last["vol_252"], snap.annualized_vol, places=4)
        # max drawdown == minimum of the running-drawdown column.
        self.assertAlmostEqual(ind["drawdown"].min(), snap.max_drawdown, places=6)

    def test_correlation_panel(self):
        tmp = tempfile.TemporaryDirectory()
        store = MarketStore(os.path.join(tmp.name, "m.db"))
        for t in ("AAA", "BBB", "CCC"):
            ingest_ticker(store, t)
        panel = self.FR.close_panel(store, ["AAA", "BBB", "CCC"])
        self.assertEqual(list(panel.columns), ["AAA", "BBB", "CCC"])
        corr = self.FR.correlation_matrix(store, ["AAA", "BBB", "CCC"], window=252)
        self.assertEqual(corr.shape, (3, 3))
        self.assertAlmostEqual(corr.loc["AAA", "AAA"], 1.0, places=6)
        store.close()
        tmp.cleanup()

    def test_ingest_dataframe(self):
        from aoa_financial.ingest.loaders import ingest_dataframe
        tmp = tempfile.TemporaryDirectory()
        store = MarketStore(os.path.join(tmp.name, "m.db"))
        rep = ingest_dataframe(store, "EXT", self.df, sector="Tech")
        self.assertEqual(rep["bars"], len(self.bars))
        self.assertTrue(store.has_prices("EXT"))
        self.assertEqual(store.get_security("EXT").sector, "Tech")
        store.close()
        tmp.cleanup()


class FundamentalsFeedTests(unittest.TestCase):
    """Provider normalisation + fallback, with the network fully mocked."""

    def setUp(self):
        from aoa_financial.ingest import fundamentals_feed as FF
        self.FF = FF
        # Isolate provider-selection env between tests.
        for k in ("AOA_FUNDAMENTALS_PROVIDER", "ALPHAVANTAGE_API_KEY",
                  "FMP_API_KEY", "FINNHUB_API_KEY"):
            os.environ.pop(k, None)

    def test_to_float_handles_junk(self):
        f = self.FF._to_float
        self.assertIsNone(f("None"))
        self.assertIsNone(f("-"))
        self.assertIsNone(f(""))
        self.assertIsNone(f(None))
        self.assertEqual(f("28.4"), 28.4)
        self.assertEqual(f("0"), 0.0)

    def test_alphavantage_normalize(self):
        raw = {"Symbol": "AAPL", "PERatio": "30.5", "PriceToBookRatio": "45",
               "DividendYield": "0.0044", "QuarterlyRevenueGrowthYOY": "0.08",
               "ProfitMargin": "0.25", "ReturnOnEquityTTM": "1.5"}
        p = self.FF.AlphaVantageProvider()
        p._raw = lambda t: raw          # bypass network
        data = p.fetch("AAPL")
        self.assertEqual(data["pe_ratio"], 30.5)
        self.assertEqual(data["profit_margin"], 0.25)
        self.assertIsNone(data["debt_to_equity"])
        self.assertEqual(set(data), set(self.FF.FIELDS))

    def test_fmp_normalize(self):
        raw = {"peRatioTTM": 25, "priceToBookRatioTTM": 8,
               "dividendYieldTTM": 0.012, "netProfitMarginTTM": 0.18,
               "debtEquityRatioTTM": 1.4, "returnOnEquityTTM": 0.3,
               "freeCashFlowPerShareTTM": 5.2}
        p = self.FF.FMPProvider()
        p._raw = lambda t: raw
        data = p.fetch("AAPL")
        self.assertEqual(data["debt_to_equity"], 1.4)
        self.assertEqual(data["free_cash_flow"], 5.2)

    def test_empty_raw_returns_none(self):
        p = self.FF.AlphaVantageProvider()
        p._raw = lambda t: None
        self.assertIsNone(p.fetch("AAPL"))

    def test_get_json_no_network_returns_none(self):
        # Simulate a provider whose HTTP call fails -> falls back to synthetic.
        _ = self.FF._REGISTRY  # touch registry side effects
        orig = self.FF._get_json
        self.FF._get_json = lambda *a, **k: None
        try:
            os.environ["ALPHAVANTAGE_API_KEY"] = "dummy"
            out = self.FF.fetch_fundamentals("AAPL", provider="alphavantage")
            self.assertEqual(out["provider"], "synthetic")
            self.assertIn("pe_ratio", out)
        finally:
            self.FF._get_json = orig
            os.environ.pop("ALPHAVANTAGE_API_KEY", None)

    def test_synthetic_always_available(self):
        out = self.FF.fetch_fundamentals("AAPL", provider="synthetic")
        self.assertEqual(out["provider"], "synthetic")
        self.assertTrue(all(k in out for k in self.FF.FIELDS))

    def test_provider_autoselect(self):
        # No keys -> synthetic.
        self.assertEqual(self.FF.get_provider().name, "synthetic")
        os.environ["FMP_API_KEY"] = "x"
        self.assertEqual(self.FF.get_provider().name, "fmp")
        os.environ.pop("FMP_API_KEY", None)

    def test_refresh_fundamentals_persists(self):
        from aoa_financial.ingest.loaders import refresh_fundamentals
        tmp = tempfile.TemporaryDirectory()
        store = MarketStore(os.path.join(tmp.name, "m.db"))
        ingest_ticker(store, "AAA")
        res = refresh_fundamentals(store, "AAA", provider="synthetic")
        self.assertEqual(res["provider"], "synthetic")
        self.assertIsNotNone(store.latest_fundamentals("AAA"))
        store.close()
        tmp.cleanup()


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


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MarketStore(os.path.join(self.tmp.name, "m.db"))
        ingest_ticker(self.store, "BTX")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_runs_and_metrics_coherent(self):
        from aoa_financial.backtest.engine import backtest_ticker
        r = backtest_ticker(self.store, "BTX", horizon=21, step=63)
        self.assertGreater(r.n_periods, 20)
        self.assertTrue(0 <= r.hit_rate <= 1)
        self.assertTrue(0 <= r.win_rate <= 1)
        self.assertLessEqual(r.max_drawdown, 0.0)
        self.assertEqual(len(r.trades), r.n_periods)
        # excess is annualised: strategy CAGR - buy&hold CAGR
        self.assertAlmostEqual(r.excess_return,
                               r.strategy_cagr - r.buy_hold_cagr, places=6)
        self.assertGreater(r.years, 1.0)
        # round-trip serialisation
        d = r.to_dict(include_trades=True)
        self.assertEqual(len(d["trades"]), r.n_periods)

    def test_no_lookahead(self):
        # A decision at index i must be identical whether computed from the full
        # history or from a history truncated exactly at i+horizon -> proves the
        # decision never reads bars beyond i.
        from aoa_financial.swarm.decision import evaluate
        bars = self.store.get_bars("BTX")
        i = 300
        full_slice = bars[: i + 1]
        d1 = evaluate("BTX", full_slice, horizon=21)
        # truncating future bars off the end must not change the i-th decision
        d2 = evaluate("BTX", bars[: i + 1][: i + 1], horizon=21)
        self.assertEqual(d1.action, d2.action)
        self.assertAlmostEqual(d1.conviction, d2.conviction, places=10)

    def test_universe(self):
        from aoa_financial.backtest.engine import backtest_universe
        ingest_ticker(self.store, "BTY")
        res = backtest_universe(self.store, ["BTX", "BTY"], horizon=21, step=126)
        self.assertEqual(set(res), {"BTX", "BTY"})


class EvaluateParityTests(unittest.TestCase):
    """The refactored evaluate() must reproduce analyze_ticker's decision."""

    def test_evaluate_matches_analyze(self):
        tmp = tempfile.TemporaryDirectory()
        store = MarketStore(os.path.join(tmp.name, "m.db"))
        ingest_ticker(store, "PAR2")
        from aoa_financial.swarm.decision import analyze_ticker, evaluate
        live = analyze_ticker(store, "PAR2", persist=False, use_llm=True)
        bars = store.get_bars("PAR2")
        direct = evaluate("PAR2", bars,
                          fundamentals=store.latest_fundamentals("PAR2"),
                          stored_sentiment=store.latest_sentiment("PAR2"),
                          sector=store.get_security("PAR2").sector, use_llm=True)
        self.assertEqual(live.action, direct.action)
        self.assertAlmostEqual(live.conviction, direct.conviction, places=10)
        store.close()
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
