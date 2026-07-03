"""Options strategist agent.

Given a directional thesis and a live option chain, proposes a single, cash-
account-appropriate options structure (long call / long put / covered call /
cash-secured put) or declines. Naked short options are never proposed — the risk
manager additionally enforces this.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction
from aoa.brokerage.base import Broker
from aoa.brokerage.models import OptionContract
from aoa.llm.client import LLMError

_CASH_STRATEGIES = ["long_call", "long_put", "covered_call", "cash_secured_put", "none"]

_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy": {"type": "string", "enum": _CASH_STRATEGIES},
        "contract_symbol": {"type": "string"},
        "contracts": {"type": "integer"},
        "max_premium_per_contract": {"type": "number"},
        "rationale": {"type": "string"},
        "conviction": {"type": "number"},
    },
    "required": ["strategy", "rationale", "conviction"],
    "additionalProperties": False,
}


class OptionsStrategistAgent(Agent):
    name = "options_strategist"
    system_prompt = (
        "You are an options strategist for a CASH account. Permitted structures are "
        "ONLY: long_call, long_put, covered_call, cash_secured_put, or none. You may "
        "NEVER propose naked short options or anything requiring margin. Given a "
        "directional thesis and a filtered option chain (with bid/ask, OI, IV, "
        "delta), pick at most one contract that best expresses the view with "
        "defined risk. Prefer liquid contracts (tight spread, real open interest) "
        "and avoid deep OTM lottery tickets. For a bullish view use long_call (or "
        "cash_secured_put to get paid to enter); for bearish use long_put. If the "
        "chain is illiquid or the edge is thin, return strategy 'none'."
    )

    def __init__(self, llm, broker: Broker) -> None:
        super().__init__(llm)
        self.broker = broker

    def propose(
        self,
        underlying: str,
        direction: Direction,
        conviction: float,
        underlying_price: float,
    ) -> dict | None:
        if direction is Direction.NEUTRAL or conviction < 0.55:
            return None
        otype = "call" if direction is Direction.BULLISH else "put"
        chain = self.broker.get_option_chain(underlying, option_type=otype)
        contracts = _filter_chain(chain, underlying_price)
        if not contracts:
            return None
        chain_ctx = [
            {
                "symbol": c.symbol,
                "type": c.option_type.value,
                "strike": c.strike,
                "expiration": c.expiration,
                "bid": c.bid,
                "ask": c.ask,
                "mid": c.mid,
                "open_interest": c.open_interest,
                "iv": c.implied_volatility,
                "delta": c.delta,
            }
            for c in contracts
        ]
        prompt = (
            f"Underlying: {underlying} @ {underlying_price}\n"
            f"Directional thesis: {direction.value} (conviction {conviction:.2f})\n"
            f"Filtered {otype} chain (JSON):\n{json.dumps(chain_ctx, default=str)}\n\n"
            "Propose at most one cash-account options structure as JSON. If nothing "
            "is attractive, set strategy to 'none'."
        )
        try:
            r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError:
            return None
        if r.get("strategy") in (None, "none"):
            return None
        # Resolve the chosen contract for downstream sizing/pricing.
        chosen = next((c for c in contracts if c.symbol == r.get("contract_symbol")), None)
        if chosen is None:
            return None
        r["underlying"] = underlying
        r["_contract"] = chosen  # consumed by the orchestrator, then stripped
        return r


def _filter_chain(
    chain: list[OptionContract], underlying_price: float, *, width: float = 0.15
) -> list[OptionContract]:
    """Keep liquid, near-the-money contracts with a real two-sided market."""
    if not chain:
        return []
    lo = underlying_price * (1 - width)
    hi = underlying_price * (1 + width)
    out = [c for c in chain if lo <= c.strike <= hi and _is_liquid_contract(c)]
    # Keep the nearest expiration cluster (the chain is sorted by expiration).
    if out:
        nearest_exp = out[0].expiration
        out = [c for c in out if c.expiration == nearest_exp]
    return out[:20]


def _is_liquid_contract(contract: OptionContract) -> bool:
    if contract.bid <= 0 or contract.ask <= 0:
        return False
    if contract.open_interest >= 10:
        return True
    # Alpaca's indicative feed often omits OI — accept tight two-sided quotes.
    if contract.open_interest == 0 and contract.mid > 0:
        spread_pct = (contract.ask - contract.bid) / contract.mid
        return spread_pct <= 0.15
    return False
