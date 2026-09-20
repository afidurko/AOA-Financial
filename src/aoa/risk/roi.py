"""ROI edge and average-entry cost-basis helpers for live sizing.

Deterministic, no LLM. Mirrors the deep-analysis forecast-cone ROI math
(``aoa_financial.swarm.decision.forecast_roi_edges``) so the live swarm can
scale notionals the same way without importing the analysis package.
"""

from __future__ import annotations

import math
from typing import Any


def roi_edge_quality(roi_edge: float) -> float:
    """Map roi_edge → quality in [0, 1]. Non-positive edges → 0."""
    if roi_edge <= 0:
        return 0.0
    return float(roi_edge / (roi_edge + 1.0))


def forecast_roi_edges(
    forecast: dict[str, Any],
    *,
    cost_pct: float = 0.0,
) -> dict[str, float]:
    """Long/short ROI edges from a forecast cone.

    ``p10`` / ``p90`` are *prices*. Convert to returns vs ``last_price``,
    subtract friction, then edge = net_expected / worst-tail-loss.
    """
    last = float(forecast.get("last_price") or 0.0)
    expected_return = float(forecast.get("expected_return") or 0.0)
    p10_price = float(forecast.get("p10") or 0.0)
    p90_price = float(forecast.get("p90") or 0.0)
    cost = float(cost_pct)
    if not math.isfinite(last):
        last = 0.0
    if not math.isfinite(expected_return):
        expected_return = 0.0
    if not math.isfinite(p10_price):
        p10_price = 0.0
    if not math.isfinite(p90_price):
        p90_price = 0.0
    if not math.isfinite(cost):
        cost = 0.0

    # Non-positive p10/p90 ⇒ treat as near-total loss / unbounded upside so we
    # never silently zero the tail and inflate ROI edge.
    if last > 0 and p10_price > 0:
        p10_ret = p10_price / last - 1.0
    elif last > 0:
        p10_ret = -1.0
    else:
        p10_ret = 0.0
    if last > 0 and p90_price > 0:
        p90_ret = p90_price / last - 1.0
    elif last > 0:
        p90_ret = 1.0
    else:
        p90_ret = 0.0

    net_expected = expected_return - cost
    net_p10 = p10_ret - cost
    net_p90 = p90_ret - cost
    eps = 1e-9

    tail_loss_long = max(0.0, -net_p10)
    roi_edge_long = net_expected / max(tail_loss_long, eps)
    tail_loss_short = max(0.0, net_p90)
    roi_edge_short = (-net_expected) / max(tail_loss_short, eps)

    return {
        "cost_pct": cost,
        "p10_return": p10_ret,
        "p90_return": p90_ret,
        "net_expected_return": net_expected,
        "roi_edge_long": roi_edge_long,
        "roi_edge_short": roi_edge_short,
    }


def horizon_to_bars(horizon: str | None) -> int:
    """Map meshed horizon labels to a trading-day window."""
    key = str(horizon or "swing").strip().lower()
    if key in {"intraday", "day", "1d"}:
        return 5
    if key in {"position", "long", "swing_long"}:
        return 63
    return 21


def simple_forecast_cone(
    closes: list[float],
    *,
    atr: float | None = None,
    horizon_bars: int = 21,
    expected_return: float | None = None,
    confidence: float = 0.6,
) -> dict[str, float] | None:
    """Lightweight cone from closes + ATR (no Monte Carlo).

    Returns ``None`` when there is not enough price history.
    """
    if len(closes) < 2:
        return None
    last = float(closes[-1])
    if last <= 0 or not math.isfinite(last):
        return None

    h = max(1, int(horizon_bars))
    if expected_return is None:
        if len(closes) > h and closes[-h - 1] > 0:
            expected_return = last / float(closes[-h - 1]) - 1.0
        else:
            expected_return = 0.0
    if not math.isfinite(float(expected_return)):
        expected_return = 0.0

    atr_val = float(atr) if atr and atr > 0 else last * 0.02
    if not math.isfinite(atr_val) or atr_val <= 0:
        atr_val = last * 0.02
    # Approx one-sigma move over the horizon in return space.
    vol_move = (atr_val * math.sqrt(h)) / last
    vol_move = max(0.01, min(0.5, vol_move))

    # Prices must stay strictly positive — a negative p10 would otherwise be
    # treated as "missing" in forecast_roi_edges and understate tail loss.
    price_floor = last * 1e-4
    p10 = max(price_floor, last * (1.0 + float(expected_return) - vol_move))
    p90 = max(p10, last * (1.0 + float(expected_return) + vol_move))

    conf = float(confidence)
    if not math.isfinite(conf):
        conf = 0.6

    return {
        "last_price": last,
        "expected_return": float(expected_return),
        "p10": p10,
        "p90": p90,
        "confidence": max(0.05, min(0.99, conf)),
    }


def unrealized_return(avg_entry: float, mark: float) -> float:
    """Average-entry cost-basis return: mark / avg_entry - 1."""
    if avg_entry <= 0 or mark <= 0:
        return 0.0
    return mark / avg_entry - 1.0


def apply_cost_basis_sell_qty(
    *,
    held: float,
    requested_qty: float,
    unrealized: float,
    roi_quality: float,
    loss_buffer: float = 0.03,
    profit_buffer: float = 0.08,
    trim_pct: float = 0.25,
) -> int:
    """Adjust an equity sell size using average-entry cost basis.

    - Deep underwater (``unrealized < -loss_buffer``): exit the full position.
    - Above ``profit_buffer`` with weak ROI quality: ensure a minimum trim.
    - Otherwise honour the requested quantity (clamped to held).
    """
    held_i = int(max(0, math.floor(held)))
    if held_i <= 0:
        return 0
    req = int(max(0, math.floor(requested_qty)))
    req = min(req, held_i)

    if unrealized < -abs(loss_buffer):
        return held_i

    if unrealized > abs(profit_buffer) and roi_quality < 0.35:
        min_trim = max(1, int(math.floor(held_i * max(0.0, min(1.0, trim_pct)))))
        return min(held_i, max(req, min_trim))

    return req


def _finite_conviction(conviction: float) -> float:
    try:
        val = float(conviction)
    except (TypeError, ValueError):
        return 0.5
    if not math.isfinite(val):
        return 0.5
    return max(0.05, min(0.99, val if val else 0.5))


def buy_notional_roi_scale(
    *,
    closes: list[float],
    atr: float | None,
    horizon: str | None,
    conviction: float,
    cost_pct: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """Scale factor in [0, 1] for a new long, plus debug ROI payload.

    Missing history → scale 1.0 (do not starve the proposal).
    """
    cone = simple_forecast_cone(
        closes,
        atr=atr,
        horizon_bars=horizon_to_bars(horizon),
        confidence=_finite_conviction(conviction),
    )
    if cone is None:
        return 1.0, {"roi_quality": 1.0, "reason": "insufficient_history"}

    edges = forecast_roi_edges(cone, cost_pct=cost_pct)
    # Live PM notionals already embed conviction — scale by ROI edge only.
    quality = roi_edge_quality(edges["roi_edge_long"])
    if not math.isfinite(quality):
        quality = 0.0
    quality = float(max(0.0, min(1.0, quality)))
    payload = {
        **edges,
        "roi_quality": quality,
        "expected_return": cone["expected_return"],
        "confidence": cone["confidence"],
        "horizon_bars": float(horizon_to_bars(horizon)),
    }
    return quality, payload
