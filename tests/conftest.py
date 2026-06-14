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

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 120) -> list[Bar]:
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
        return list(self._open_orders)

    def cancel_order(self, order_id: str) -> None:
        pass

    def is_market_open(self) -> bool:
        return self.market_open


class FakeLLM:
    """Routes ``structured()`` calls to canned responses by inspecting the schema."""

    def __init__(self, *, candidates=None):
        self.candidates = candidates if candidates is not None else [
            {"symbol": "AAPL", "reason": "trend pullback", "priority": 0.9}
        ]
        self.model = "fake"

    def complete(self, system: str, prompt: str, **kwargs) -> str:
        return "ok"

    def structured(self, system: str, prompt: str, schema: dict, **kwargs) -> dict:
        props = set(schema.get("properties", {}).keys())
        if "candidates" in props:
            return {"candidates": self.candidates}
        if "event_risk" in props:  # fundamental
            return {
                "direction": "bullish",
                "conviction": 0.6,
                "event_risk": "low",
                "rationale": "stable large cap",
            }
        if "support" in props or "horizon" in props:  # technical
            return {
                "direction": "bullish",
                "conviction": 0.75,
                "horizon": "swing",
                "rationale": "above rising 50DMA, RSI constructive",
                "support": 95.0,
                "resistance": 110.0,
                "stop_suggestion": 92.0,
            }
        if "strategy" in props and "max_premium_per_contract" in props:  # options
            return {
                "strategy": "long_call",
                "contract_symbol": "AAPL250117C00100000",
                "contracts": 1,
                "max_premium_per_contract": 2.5,
                "rationale": "defined-risk bullish expression",
                "conviction": 0.7,
            }
        if "proposals" in props:  # portfolio
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
        if "vetoes" in props:  # risk
            return {"vetoes": [], "assessment": "prudent"}
        return {}


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
