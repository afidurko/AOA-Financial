"""FinancePy-backed options analytics for Andrea's pre-execution risk plans.

When the optional ``financepy`` extra is installed, Andrea receives deterministic
Black-Scholes fair values, Greeks, and protective-put hedge quotes alongside
broker chain data. Without FinancePy the helpers return ``None`` and Andrea
falls back to LLM-only reasoning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aoa.brokerage.models import OptionContract

try:
    from financepy.market.curves.discount_curve_flat import DiscountCurveFlat
    from financepy.models.black_scholes import BlackScholes, BlackScholesTypes
    from financepy.products.equity.equity_vanilla_option import EquityVanillaOption
    from financepy.utils import Date as FpDate
    from financepy.utils.error import FinError
    from financepy.utils.global_types import OptionTypes

    HAS_FINANCEPY = True
except ImportError:  # pragma: no cover - exercised when financepy extra absent
    HAS_FINANCEPY = False
    FinError = Exception  # type: ignore[misc, assignment]


def build_andrea_quant_context(
    symbol: str,
    spot: float | None,
    *,
    options_idea: dict | None = None,
    option_chain: list[OptionContract] | None = None,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
) -> dict[str, Any] | None:
    """Return structured quant metrics for Andrea, or ``None`` if unavailable."""
    if not HAS_FINANCEPY or not spot or spot <= 0:
        return None

    value_dt = _today_fp_date()
    discount_curve = DiscountCurveFlat(value_dt, risk_free_rate)
    dividend_curve = DiscountCurveFlat(value_dt, dividend_yield)

    out: dict[str, Any] = {
        "source": "financepy",
        "spot": round(spot, 4),
        "risk_free_rate": risk_free_rate,
        "dividend_yield": dividend_yield,
    }

    if options_idea and option_chain:
        contract = _find_contract(option_chain, options_idea.get("contract_symbol"))
        if contract:
            proposed = _analyze_contract(
                contract,
                spot,
                value_dt,
                discount_curve,
                dividend_curve,
            )
            if proposed:
                out["proposed_option"] = proposed

    hedge = _protective_put_quote(option_chain or [], spot, value_dt, discount_curve, dividend_curve)
    if hedge:
        out["protective_put_hedge"] = hedge

    if len(out) <= 4:
        return None
    return out


def _find_contract(chain: list[OptionContract], symbol: str | None) -> OptionContract | None:
    if not symbol:
        return None
    sym = str(symbol).upper()
    return next((c for c in chain if c.symbol.upper() == sym), None)


def _analyze_contract(
    contract: OptionContract,
    spot: float,
    value_dt: Any,
    discount_curve: Any,
    dividend_curve: Any,
) -> dict[str, Any] | None:
    expiry = _parse_iso_date(contract.expiration)
    if value_dt >= expiry:
        return None
    opt_type = (
        OptionTypes.EUROPEAN_CALL
        if contract.option_type.value == "call"
        else OptionTypes.EUROPEAN_PUT
    )
    vol = contract.implied_volatility if contract.implied_volatility and contract.implied_volatility > 0 else 0.30
    model = BlackScholes(vol, BlackScholesTypes.ANALYTICAL)
    option = EquityVanillaOption(expiry, contract.strike, opt_type)

    try:
        fair = _f(option.value(value_dt, spot, discount_curve, dividend_curve, model))
        delta = _f(option.delta(value_dt, spot, discount_curve, dividend_curve, model))
        gamma = _f(option.gamma(value_dt, spot, discount_curve, dividend_curve, model))
        theta = _f(option.theta(value_dt, spot, discount_curve, dividend_curve, model))
        vega = _f(option.vega(value_dt, spot, discount_curve, dividend_curve, model))
    except FinError:
        return None

    market_mid = contract.mid
    mispricing_pct = None
    if fair and market_mid > 0:
        mispricing_pct = round((market_mid - fair) / market_mid * 100, 2)

    return {
        "symbol": contract.symbol,
        "type": contract.option_type.value,
        "strike": contract.strike,
        "expiration": contract.expiration,
        "market_mid": round(market_mid, 4),
        "model_fair_value": fair,
        "mispricing_pct": mispricing_pct,
        "implied_vol_used": round(vol, 4),
        "greeks": {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
        },
        "broker_delta": contract.delta,
    }


def _protective_put_quote(
    chain: list[OptionContract],
    spot: float,
    value_dt: Any,
    discount_curve: Any,
    dividend_curve: Any,
    *,
    otm_pct: float = 0.05,
) -> dict[str, Any] | None:
    """Estimate cost of a ~5% OTM protective put for hedge sizing."""
    puts = [c for c in chain if c.option_type.value == "put" and c.mid > 0]
    if not puts:
        return None

    target_strike = spot * (1.0 - otm_pct)
    puts.sort(key=lambda c: (abs(c.strike - target_strike), c.expiration))
    contract = puts[0]

    analysis = _analyze_contract(contract, spot, value_dt, discount_curve, dividend_curve)
    if not analysis:
        return None
    premium_per_share = contract.mid
    contract_cost = round(premium_per_share * 100, 2)
    hedge_pct_of_spot = round(premium_per_share / spot * 100, 3) if spot > 0 else None

    return {
        **analysis,
        "hedge_purpose": f"protective put ~{otm_pct * 100:.0f}% OTM",
        "premium_per_contract_usd": contract_cost,
        "hedge_cost_pct_of_spot": hedge_pct_of_spot,
    }


def _today_fp_date() -> Any:
    today = datetime.now(timezone.utc).date()
    return FpDate(today.day, today.month, today.year)


def _parse_iso_date(iso: str) -> Any:
    parts = iso.split("-")
    if len(parts) != 3:
        raise ValueError(f"expected YYYY-MM-DD, got {iso!r}")
    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    return FpDate(d, m, y)


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        return round(v, 6) if v == v else None  # NaN check
    except (TypeError, ValueError):
        return None
