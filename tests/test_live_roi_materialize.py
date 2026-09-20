"""Live-swarm ROI sizing + average-entry cost-basis gates in MaterializeStage."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from aoa.brokerage.models import AssetClass, Bar, Position, Quote, Side
from aoa.config import RiskLimits
from aoa.data.market_data import SymbolSnapshot
from aoa.risk.roi import (
    apply_cost_basis_sell_qty,
    buy_notional_roi_scale,
    forecast_roi_edges,
    roi_edge_quality,
    simple_forecast_cone,
    unrealized_return,
)
from aoa.swarm.blackboard import Blackboard
from aoa.swarm.stages import _materialize_proposals


def _bars(closes: list[float]) -> list[Bar]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out: list[Bar] = []
    for i, c in enumerate(closes):
        out.append(
            Bar(
                timestamp=base + timedelta(days=i),
                open=c * 0.99,
                high=c * 1.01,
                low=c * 0.98,
                close=c,
                volume=1_000_000,
            )
        )
    return out


def _snap(symbol: str, closes: list[float], *, atr: float = 2.0, price: float | None = None) -> SymbolSnapshot:
    mark = price if price is not None else closes[-1]
    return SymbolSnapshot(
        symbol=symbol,
        quote=Quote(symbol=symbol, bid=mark - 0.5, ask=mark + 0.5),
        bars=_bars(closes),
        technicals={"1Day": {"atr_14": atr, "last_close": closes[-1]}},
    )


def _pos(symbol: str, qty: float, avg: float, mark: float) -> Position:
    return Position(
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        qty=qty,
        avg_entry_price=avg,
        market_value=qty * mark,
        unrealized_pl=qty * (mark - avg),
        current_price=mark,
    )


def test_simple_cone_clamps_non_positive_p10():
    # Deeply negative expected return + wide vol would otherwise emit p10 < 0.
    closes = [100.0] * 30
    cone = simple_forecast_cone(
        closes, atr=50.0, horizon_bars=63, expected_return=-0.9
    )
    assert cone is not None
    assert cone["p10"] > 0
    assert cone["p90"] >= cone["p10"]
    edges = forecast_roi_edges(cone, cost_pct=0.0)
    # Clamped p10 near zero ⇒ ~-100% tail, so long edge must stay finite and small.
    assert edges["p10_return"] < -0.99
    assert math.isfinite(edges["roi_edge_long"])
    assert roi_edge_quality(edges["roi_edge_long"]) < 0.5


def test_forecast_roi_edges_treats_missing_p10_as_total_loss():
    roi = forecast_roi_edges(
        {
            "last_price": 100.0,
            "expected_return": 0.05,
            "p10": -10.0,  # invalid
            "p90": 120.0,
        },
        cost_pct=0.0,
    )
    assert abs(roi["p10_return"] - (-1.0)) < 1e-12
    # net 5% / ~100% tail ⇒ edge ~0.05
    assert abs(roi["roi_edge_long"] - 0.05) < 1e-9


def test_materialize_journals_when_scaled_notional_below_one_share(tmp_path):
    from aoa.journal.store import Journal

    closes = [120.0 - i * 0.05 for i in range(40)]  # mild down → weak scale
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, atr=8.0, price=100.0)
    journal = Journal(tmp_path / "j.jsonl")
    props = _materialize_proposals(
        [
            {
                "symbol": "AAPL",
                "instrument": "equity",
                "side": "buy",
                "target_notional": 50,  # tiny; after ROI scale floors to 0 shares
                "conviction": 0.5,
                "rationale": "tiny",
            }
        ],
        bb,
        journal=journal,
        risk=RiskLimits(transaction_cost_pct=0.02),
    )
    assert props == []
    events = [e["event"] for e in journal.tail(20)]
    assert "proposal.skipped" in events or "proposal.roi_scale" in events

    fc = {
        "last_price": 100.0,
        "expected_return": 0.05,
        "p10": 90.0,
        "p90": 120.0,
        "confidence": 0.7,
    }
    roi = forecast_roi_edges(fc, cost_pct=0.01)
    assert abs(roi["p10_return"] - (-0.10)) < 1e-9
    assert abs(roi["roi_edge_long"] - (0.04 / 0.11)) < 1e-9
    assert roi_edge_quality(roi["roi_edge_long"]) > 0


def test_simple_forecast_cone_and_buy_scale():
    closes = [100.0 + i * 0.5 for i in range(40)]
    cone = simple_forecast_cone(closes, atr=2.0, horizon_bars=21)
    assert cone is not None
    assert cone["last_price"] == closes[-1]
    scale, payload = buy_notional_roi_scale(
        closes=closes, atr=2.0, horizon="swing", conviction=0.8, cost_pct=0.0
    )
    assert 0 < scale <= 1
    assert "roi_quality" in payload


def test_buy_scale_zero_on_negative_edge():
    # Falling series → expected return negative → long ROI quality 0.
    closes = [120.0 - i * 0.8 for i in range(40)]
    scale, payload = buy_notional_roi_scale(
        closes=closes, atr=1.0, horizon="swing", conviction=0.9, cost_pct=0.0
    )
    assert scale == 0.0
    assert payload["roi_quality"] == 0.0


def test_unrealized_and_cost_basis_sell_rules():
    assert abs(unrealized_return(100.0, 90.0) - (-0.10)) < 1e-9
    # Deep loss → full exit.
    assert apply_cost_basis_sell_qty(
        held=40, requested_qty=5, unrealized=-0.10, roi_quality=0.9
    ) == 40
    # Profit + weak ROI → at least 25% trim.
    qty = apply_cost_basis_sell_qty(
        held=40, requested_qty=2, unrealized=0.12, roi_quality=0.1, trim_pct=0.25
    )
    assert qty == 10
    # Otherwise honour request.
    assert apply_cost_basis_sell_qty(
        held=40, requested_qty=7, unrealized=0.02, roi_quality=0.8
    ) == 7


def test_materialize_scales_buy_notional_by_roi():
    closes = [100.0 + i * 0.4 for i in range(40)]
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, atr=2.0, price=100.0)
    raw = [
        {
            "symbol": "AAPL",
            "instrument": "equity",
            "side": "buy",
            "target_notional": 10_000,
            "conviction": 0.8,
            "rationale": "test",
        }
    ]
    full = _materialize_proposals(raw, bb, risk=RiskLimits())
    weak = _materialize_proposals(
        raw,
        bb,
        risk=RiskLimits(transaction_cost_pct=0.04, slippage_pct=0.02),
    )
    assert len(full) == 1 and full[0].side is Side.BUY
    assert len(weak) == 1 and weak[0].side is Side.BUY
    assert weak[0].qty < full[0].qty


def test_materialize_skips_buy_on_non_positive_roi():
    closes = [120.0 - i * 0.8 for i in range(40)]
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, atr=1.0, price=closes[-1])
    props = _materialize_proposals(
        [
            {
                "symbol": "AAPL",
                "instrument": "equity",
                "side": "buy",
                "target_notional": 5000,
                "conviction": 0.9,
                "rationale": "falling",
            }
        ],
        bb,
        risk=RiskLimits(),
    )
    assert props == []


def test_materialize_reentry_still_skips_held_buy():
    closes = [100.0 + i * 0.5 for i in range(40)]
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, price=100.0)
    bb.positions = [_pos("AAPL", 10, 95.0, 100.0)]
    props = _materialize_proposals(
        [
            {
                "symbol": "AAPL",
                "instrument": "equity",
                "side": "buy",
                "target_notional": 5000,
                "conviction": 0.8,
                "rationale": "add",
            }
        ],
        bb,
        risk=RiskLimits(),
    )
    assert props == []


def test_materialize_sell_full_exit_when_underwater():
    closes = [100.0] * 30
    mark = 90.0
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, atr=2.0, price=mark)
    bb.positions = [_pos("AAPL", 40, avg=100.0, mark=mark)]
    props = _materialize_proposals(
        [
            {
                "symbol": "AAPL",
                "instrument": "equity",
                "side": "sell",
                "target_notional": 450,  # would be ~5 shares without gate
                "conviction": 0.5,
                "rationale": "trim",
            }
        ],
        bb,
        risk=RiskLimits(cost_basis_loss_buffer=0.03),
    )
    assert len(props) == 1
    assert props[0].side is Side.SELL
    assert props[0].qty == 40


def test_materialize_sell_min_trim_when_profit_and_weak_roi():
    # Flat/down closes → weak long ROI; mark well above avg entry.
    closes = [110.0 - i * 0.2 for i in range(40)]
    mark = 120.0
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, atr=3.0, price=mark)
    bb.positions = [_pos("AAPL", 40, avg=100.0, mark=mark)]
    props = _materialize_proposals(
        [
            {
                "symbol": "AAPL",
                "instrument": "equity",
                "side": "sell",
                "target_notional": 240,  # ~2 shares at 120
                "conviction": 0.4,
                "rationale": "weak edge trim",
            }
        ],
        bb,
        risk=RiskLimits(
            cost_basis_profit_buffer=0.08,
            cost_basis_trim_pct=0.25,
        ),
    )
    assert len(props) == 1
    assert props[0].qty == 10


def test_materialize_normalizes_symbol_case_for_reentry_and_sells():
    from aoa.brokerage.models import Order

    closes = [100.0 + i * 0.5 for i in range(40)]
    bb = Blackboard()
    bb.snapshots["AAPL"] = _snap("AAPL", closes, price=90.0)
    bb.positions = [_pos("aapl", 40, avg=100.0, mark=90.0)]
    assert (
        _materialize_proposals(
            [
                {
                    "symbol": "AAPL",
                    "instrument": "equity",
                    "side": "buy",
                    "target_notional": 5000,
                    "conviction": 0.8,
                    "rationale": "add",
                }
            ],
            bb,
            risk=RiskLimits(),
        )
        == []
    )
    sells = _materialize_proposals(
        [
            {
                "symbol": "AAPL",
                "instrument": "equity",
                "side": "sell",
                "target_notional": 450,
                "conviction": 0.5,
                "rationale": "exit",
            }
        ],
        bb,
        risk=RiskLimits(cost_basis_loss_buffer=0.03),
    )
    assert len(sells) == 1 and sells[0].qty == 40

    bb2 = Blackboard()
    bb2.snapshots["AAPL"] = _snap("AAPL", closes, price=100.0)
    bb2.open_orders = [Order(id="o1", symbol="aapl", qty=5, side=Side.BUY, status="new")]
    assert (
        _materialize_proposals(
            [
                {
                    "symbol": "AAPL",
                    "instrument": "equity",
                    "side": "buy",
                    "target_notional": 5000,
                    "conviction": 0.8,
                    "rationale": "pending",
                }
            ],
            bb2,
            risk=RiskLimits(),
        )
        == []
    )
