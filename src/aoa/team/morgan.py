"""Morgan — market context, equity volume, and options flow analyst."""

from __future__ import annotations

import json

from aoa.agents.base import Agent
from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.models import OptionContract
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import MarketContextReport, OptionsVolumeHighlight

_SCHEMA = {
    "type": "object",
    "properties": {
        "volume_regime": {"type": "string", "enum": ["elevated", "normal", "thin"]},
        "volume_ratio": {"type": "number"},
        "liquidity_note": {"type": "string"},
        "options_volume_note": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": [
        "volume_regime",
        "volume_ratio",
        "liquidity_note",
        "options_volume_note",
        "summary",
    ],
    "additionalProperties": False,
}


class MorganAgent(Agent):
    name = "morgan"
    display_name = "Morgan"
    role = "Market & Volume Analyst"

    system_prompt = (
        "You are Morgan, the market and volume analyst on an autonomous trading team. "
        "Given OHLCV equity snapshots and computed options-flow hints, characterize:\n"
        "1) Equity volume regime (elevated, normal, thin) vs the 20-day average.\n"
        "2) Liquidity implications for cash-account trading.\n"
        "3) Options activity — which expiration dates and strike prices show the "
        "heaviest volume, whether flow clusters near/at-the-money, and if options "
        "volume confirms or contradicts the equity trend.\n"
        "Be concise and factual — cite only metrics present in the input."
    )

    def __init__(self, llm, broker: Broker | None = None) -> None:
        super().__init__(llm)
        self.broker = broker

    def analyze_contexts(self, snapshots: dict[str, SymbolSnapshot]) -> list[MarketContextReport]:
        return [self.analyze_symbol(snap) for snap in snapshots.values()]

    def analyze_symbol(self, snap: SymbolSnapshot) -> MarketContextReport:
        baseline = _volume_baseline(snap)
        options_scan = _scan_options_volume(self.broker, snap)

        if snap.error or not snap.has_technicals:
            return MarketContextReport(
                symbol=snap.symbol,
                volume_regime="thin",
                volume_ratio=baseline.get("volume_ratio"),
                liquidity_note="Insufficient market data.",
                summary=f"{snap.symbol}: data unavailable.",
                options_volume_note=options_scan.get("note", "Options data unavailable."),
                options_highlights=_highlights_from_scan(options_scan),
                options_by_expiration=dict(options_scan.get("by_expiration") or {}),
            )

        prompt = (
            f"Symbol snapshot:\n{json.dumps(snap.to_context(), default=str)}\n"
            f"Computed equity volume hints:\n{json.dumps(baseline, default=str)}\n"
            f"Computed options volume hints:\n{json.dumps(options_scan, default=str)}\n"
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        ratio = r.get("volume_ratio")
        if ratio is None:
            ratio = baseline.get("volume_ratio")
        return MarketContextReport(
            symbol=snap.symbol,
            volume_regime=str(r.get("volume_regime", baseline.get("regime", "normal"))),
            volume_ratio=float(ratio) if ratio is not None else None,
            liquidity_note=str(r.get("liquidity_note", "")),
            summary=str(r.get("summary", "")),
            options_volume_note=_options_note_from_scan(r, options_scan),
            options_highlights=_highlights_from_scan(options_scan),
            options_by_expiration=dict(options_scan.get("by_expiration") or {}),
        )


def _volume_baseline(snap: SymbolSnapshot) -> dict:
    daily = snap.technicals.get("1Day") or snap.technicals.get("1day") or {}
    vm = daily.get("volume_metrics") or {}
    ratio = vm.get("volume_ratio")
    regime = "normal"
    if ratio is not None:
        if ratio >= 1.5:
            regime = "elevated"
        elif ratio < 0.7:
            regime = "thin"
    return {
        "volume_ratio": ratio,
        "latest_volume": vm.get("latest_volume"),
        "avg_volume_20d": vm.get("avg_volume_20d"),
        "regime": regime,
    }


def _scan_options_volume(broker: Broker | None, snap: SymbolSnapshot) -> dict:
    """Aggregate options volume by expiration date and highlight active strikes."""
    if broker is None:
        return {"available": False, "note": "No broker configured for options scan."}

    price = snap.reference_price()
    if not price or price <= 0:
        return {"available": False, "note": "No reference price for options scan."}

    try:
        chain = broker.get_option_chain(snap.symbol)
    except (BrokerError, Exception):  # noqa: BLE001 — degrade gracefully
        return {"available": False, "note": f"{snap.symbol}: options chain unavailable."}

    filtered = _filter_options_chain(chain, price)
    if not filtered:
        return {
            "available": True,
            "note": f"{snap.symbol}: no liquid near-the-money options with volume.",
            "by_expiration": {},
            "highlights": [],
            "total_volume": 0.0,
        }

    by_expiration: dict[str, float] = {}
    highlights: list[dict] = []
    for contract in filtered:
        vol = contract.volume or 0.0
        by_expiration[contract.expiration] = by_expiration.get(contract.expiration, 0.0) + vol
        highlights.append(
            {
                "expiration": contract.expiration,
                "strike": contract.strike,
                "option_type": contract.option_type.value,
                "volume": vol,
                "price": contract.mid,
                "open_interest": contract.open_interest,
            }
        )

    highlights.sort(key=lambda row: row["volume"], reverse=True)
    top = highlights[:8]
    note = _format_options_note(snap.symbol, by_expiration, top)
    return {
        "available": True,
        "note": note,
        "by_expiration": {k: round(v, 0) for k, v in sorted(by_expiration.items())},
        "highlights": top,
        "total_volume": round(sum(c.volume or 0.0 for c in filtered), 0),
        "spot": round(price, 2),
    }


def _filter_options_chain(
    chain: list[OptionContract], underlying_price: float, *, width: float = 0.20
) -> list[OptionContract]:
    if not chain:
        return []
    lo = underlying_price * (1 - width)
    hi = underlying_price * (1 + width)
    near = [
        c
        for c in chain
        if lo <= c.strike <= hi and (c.volume > 0 or c.open_interest >= 10 or c.mid > 0)
    ]
    if not near:
        return []
    expiries = sorted({c.expiration for c in near})[:4]
    allowed = set(expiries)
    return [c for c in near if c.expiration in allowed]


def _format_options_note(
    symbol: str, by_expiration: dict[str, float], top: list[dict]
) -> str:
    if not top:
        return f"{symbol}: no notable options volume."
    exp_parts = [
        f"{exp} ({int(vol)} contracts)"
        for exp, vol in sorted(by_expiration.items(), key=lambda kv: kv[1], reverse=True)[:3]
        if vol > 0
    ]
    strike_parts = [
        f"{row['option_type'][0].upper()}{row['strike']:.0f}@{row['expiration']} "
        f"vol={int(row['volume'])} @${row['price']:.2f}"
        for row in top[:3]
        if row.get("volume", 0) > 0
    ]
    chunks = []
    if exp_parts:
        chunks.append("busiest expiries: " + ", ".join(exp_parts))
    if strike_parts:
        chunks.append("top strikes: " + "; ".join(strike_parts))
    return f"{symbol} options — " + (" · ".join(chunks) if chunks else "light flow.")


def _options_note_from_scan(llm_result: dict, scan: dict) -> str:
    if not scan.get("available"):
        return str(scan.get("note", ""))
    return str(llm_result.get("options_volume_note", scan.get("note", "")))


def _highlights_from_scan(scan: dict) -> list[OptionsVolumeHighlight]:
    out: list[OptionsVolumeHighlight] = []
    for row in scan.get("highlights") or []:
        out.append(
            OptionsVolumeHighlight(
                expiration=str(row.get("expiration", "")),
                strike=float(row.get("strike", 0.0)),
                option_type=str(row.get("option_type", "")),
                volume=float(row.get("volume", 0.0)),
                price=float(row.get("price", 0.0)),
                open_interest=float(row.get("open_interest", 0.0)),
            )
        )
    return out
