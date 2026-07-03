"""Shared test fixtures: an in-memory fake broker and a canned-response fake LLM.

These let the full swarm run end-to-end in tests without touching Alpaca or the
Anthropic API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aoa.brokerage.base import Broker
from aoa.brokerage.models import (
    Account,
    AssetClass,
    Bar,
    OptionContract,
    OptionType,
    Order,
    OrderRequest,
    Position,
    Quote,
    Side,
)


class FakeBroker(Broker):
    name = "fake"
    is_live = False

    def __init__(self, *, equity=100_000.0, cash=100_000.0, options_level=2):
        self._account = Account(
            equity=equity,
            cash=cash,
            buying_power=cash,
            settled_cash=cash,
            options_level=options_level,
        )
        self._positions: list[Position] = []
        self._open_orders: list[Order] = []
        self.submitted: list[OrderRequest] = []
        self.market_open = True

    def get_account(self) -> Account:
        return self._account

    def get_positions(self) -> list[Position]:
        return list(self._positions)

    def set_positions(self, positions: list[Position]) -> None:
        self._positions = positions

    def get_quote(self, symbol: str) -> Quote:
        return Quote(symbol=symbol, bid=99.5, ask=100.5)

    def get_quotes_many(self, symbols: list[str]) -> dict[str, Quote]:
        return {s.upper(): self.get_quote(s.upper()) for s in symbols if s}

    def _synthetic_bars(self, limit: int) -> list[Bar]:
        # Synthetic gently-rising series with enough history for all indicators.
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        bars = []
        price = 80.0
        for i in range(limit):
            price *= 1.001 + (0.002 if i % 5 == 0 else -0.0005)
            bars.append(
                Bar(
                    timestamp=base + timedelta(days=i),
                    open=price * 0.99,
                    high=price * 1.01,
                    low=price * 0.985,
                    close=price,
                    volume=1_000_000 + i * 10,
                )
            )
        return bars

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 120) -> list[Bar]:
        return self._synthetic_bars(limit)

    def get_bars_batch(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        limit: int = 120,
    ) -> dict[str, list[Bar]]:
        return {s.upper(): self._synthetic_bars(limit) for s in symbols if s}

    def get_most_active(self, limit: int = 25) -> list[str]:
        return ["AAPL", "MSFT", "NVDA"][:limit]

    def get_option_chain(self, underlying, expiration=None, option_type=None):
        otype = OptionType.CALL if (option_type or "call") == "call" else OptionType.PUT
        return [
            OptionContract(
                symbol=f"{underlying}250117C00100000",
                underlying=underlying,
                option_type=otype,
                strike=100.0,
                expiration="2025-01-17",
                bid=2.0,
                ask=2.2,
                last=2.1,
                open_interest=500,
                implied_volatility=0.35,
                delta=0.5,
            )
        ]

    def submit_order(self, request: OrderRequest) -> Order:
        self.submitted.append(request)
        return Order(
            id=f"ord-{len(self.submitted)}",
            symbol=request.symbol,
            qty=request.qty,
            side=request.side,
            status="accepted",
            asset_class=request.asset_class,
        )

    def set_open_orders(self, orders: list[Order]) -> None:
        self._open_orders = orders

    def list_orders(self, status: str = "open") -> list[Order]:
        if status == "open":
            return list(self._open_orders)
        return []

    def cancel_order(self, order_id: str) -> None:
        pass

    def is_market_open(self) -> bool:
        return self.market_open


class FakeLLM:
    """Routes ``structured()`` calls by JSON-schema ``required`` keys."""

    _MESHING = frozenset(
        {"direction", "conviction", "horizon", "rationale", "corroboration"}
    )
    _TECHNICAL = frozenset({"direction", "conviction", "horizon", "rationale"})
    _FUNDAMENTAL = frozenset({"direction", "conviction", "event_risk", "rationale"})
    _OPTIONS = frozenset({"strategy", "rationale", "conviction"})
    _PORTFOLIO = frozenset({"proposals", "portfolio_commentary"})
    _RISK = frozenset({"vetoes", "assessment"})
    _SCANNER = frozenset({"candidates"})
    _TOM = frozenset({"direction", "strength", "timeframe", "rationale", "key_observations"})
    _JULIE = frozenset({"validated", "adjusted_strength", "method_notes", "signals"})
    _ALAN = frozenset({"recommendations", "summary", "confidence"})
    _AARON = frozenset({"overall_ok", "summary", "user_notifications", "team_status"})
    _NEWS = frozenset({"direction", "conviction", "summary", "key_events", "macro_risk"})
    _SENTIMENT = frozenset(
        {"direction", "conviction", "sentiment_score", "summary", "drivers"}
    )
    _RESEARCH_FACILITATOR = frozenset({"prevailing_view", "conviction", "rationale"})
    _RESEARCH_DEBATE = frozenset({"argument", "key_points", "conviction"})
    _FUND_MANAGER = frozenset({"approved", "vetoes", "commentary"})
    _RISK_DEBATE = frozenset({"perspectives", "facilitator_summary", "vetoes"})

    def __init__(self, *, candidates=None):
        self.candidates = candidates if candidates is not None else [
            {"symbol": "AAPL", "reason": "trend pullback", "priority": 0.9}
        ]
        self.model = "fake"

    def complete(self, system: str, prompt: str, **kwargs) -> str:
        return "ok"

    def structured(self, system: str, prompt: str, schema: dict, **kwargs) -> dict:
        required = frozenset(schema.get("required") or ())
        if required == self._SCANNER:
            return {"candidates": self.candidates}
        if required == self._MESHING:
            return {
                "direction": "bullish",
                "conviction": 0.72,
                "horizon": "swing",
                "rationale": "technical and fundamental aligned",
                "corroboration": "strong",
                "conflicts": [],
                "key_levels": {"support": 95.0, "resistance": 110.0},
            }
        if required == self._FUNDAMENTAL:
            return {
                "direction": "bullish",
                "conviction": 0.6,
                "event_risk": "low",
                "rationale": "stable large cap",
            }
        if required == self._TECHNICAL:
            return {
                "direction": "bullish",
                "conviction": 0.75,
                "horizon": "swing",
                "rationale": "above rising 50DMA, RSI constructive",
                "support": 95.0,
                "resistance": 110.0,
                "stop_suggestion": 92.0,
            }
        if required == self._OPTIONS:
            return {
                "strategy": "long_call",
                "contract_symbol": "AAPL250117C00100000",
                "contracts": 1,
                "max_premium_per_contract": 2.5,
                "rationale": "defined-risk bullish expression",
                "conviction": 0.7,
            }
        if required == self._PORTFOLIO:
            return {
                "proposals": [
                    {
                        "symbol": "AAPL",
                        "instrument": "equity",
                        "side": "buy",
                        "target_notional": 5000,
                        "strategy": "long_equity",
                        "conviction": 0.7,
                        "rationale": "highest-conviction corroborated long",
                    }
                ],
                "portfolio_commentary": "one focused long",
            }
        if required == self._RISK_DEBATE:
            return {
                "perspectives": [
                    {"stance": "risk_seeking", "assessment": "ok", "recommendation": "hold"},
                    {"stance": "neutral", "assessment": "ok", "recommendation": "hold"},
                    {"stance": "risk_conservative", "assessment": "ok", "recommendation": "hold"},
                ],
                "facilitator_summary": "balanced risk",
                "vetoes": [],
            }
        if required == self._FUND_MANAGER:
            return {"approved": True, "vetoes": [], "commentary": "fund manager approved"}
        if required == self._RISK:
            return {"vetoes": [], "assessment": "prudent"}
        if required == self._RESEARCH_FACILITATOR:
            return {
                "prevailing_view": "bullish",
                "conviction": 0.65,
                "rationale": "bull case stronger",
            }
        if required == self._RESEARCH_DEBATE:
            return {
                "argument": "constructive setup",
                "key_points": ["momentum", "sentiment"],
                "conviction": 0.7,
            }
        if required == self._SENTIMENT:
            return {
                "direction": "bullish",
                "conviction": 0.55,
                "sentiment_score": 0.4,
                "summary": "positive headline tone",
                "drivers": ["earnings optimism"],
            }
        if required == self._NEWS:
            return {
                "direction": "neutral",
                "conviction": 0.4,
                "summary": "no major catalysts",
                "key_events": ["sector rotation"],
                "macro_risk": "low",
            }
        if required == self._TOM:
            return {
                "direction": "up",
                "strength": 0.72,
                "timeframe": "swing",
                "rationale": "Higher highs with rising 50DMA support",
                "key_observations": ["volume confirmation", "pullback held"],
            }
        if required == self._JULIE:
            return {
                "validated": True,
                "adjusted_strength": 0.68,
                "method_notes": "RSI regime supports Tom's uptrend read",
                "signals": ["sma_cross_bullish", "rsi_constructive"],
            }
        if required == self._ALAN:
            return {
                "recommendations": [
                    {
                        "symbol": "AAPL",
                        "action": "consider_long",
                        "conviction": 0.7,
                        "rationale": "Tom and Julie aligned on bullish swing setup",
                    }
                ],
                "summary": "One high-quality corroborated long candidate",
                "confidence": 0.72,
            }
        if required == self._AARON:
            return {
                "overall_ok": True,
                "summary": "Team completed health, code audit, and decision brief.",
                "user_notifications": [],
                "team_status": [
                    {"name": "Tom", "role": "Trend Analyst", "completed": True, "notes": "ok"},
                    {
                        "name": "Julie",
                        "role": "Algorithm Specialist & Code Clarity",
                        "completed": True,
                        "notes": "Validated Tom's read.",
                    },
                    {
                        "name": "Bob",
                        "role": "Systems Health & Code Integrity",
                        "completed": True,
                        "notes": "Code quality checks passed.",
                    },
                    {"name": "Alan", "role": "Decision Aggregator & Code Oversight", "completed": True, "notes": "Decision brief ready."},
                    {"name": "Aaron", "role": "CEO", "completed": True, "notes": "ok"},
                ],
            }
        raise ValueError(f"FakeLLM: unhandled schema required keys {sorted(required)!r}")


@pytest.fixture
def fake_broker():
    return FakeBroker()


@pytest.fixture
def fake_llm():
    return FakeLLM()


def make_position(symbol="AAPL", qty=100, asset_class=AssetClass.EQUITY, price=100.0):
    return Position(
        symbol=symbol,
        asset_class=asset_class,
        qty=qty,
        avg_entry_price=price,
        market_value=qty * price * (100 if asset_class is AssetClass.OPTION else 1),
        unrealized_pl=0.0,
        current_price=price,
    )


__all__ = ["FakeBroker", "FakeLLM", "make_position", "Side"]
