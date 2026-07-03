"""Broker-neutral data models.

These dataclasses are the lingua franca between the brokerage layer and the rest
of the system. Concrete brokers translate their API payloads into these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    OPTION = "option"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    timestamp: datetime | None = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 4)
        return self.ask or self.bid

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 4) if self.ask and self.bid else 0.0


@dataclass(frozen=True)
class Bar:
    """A single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Position:
    symbol: str
    asset_class: AssetClass
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pl: float
    current_price: float

    @property
    def is_long(self) -> bool:
        return self.qty > 0


@dataclass(frozen=True)
class Account:
    equity: float
    cash: float
    buying_power: float
    # Cash settled and available for trading without violating good-faith rules.
    settled_cash: float
    # Options approval level the broker has granted (0 = none).
    options_level: int = 0
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    currency: str = "USD"


@dataclass(frozen=True)
class OptionContract:
    symbol: str  # OCC option symbol, e.g. AAPL250117C00150000
    underlying: str
    option_type: OptionType
    strike: float
    expiration: str  # ISO date YYYY-MM-DD
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    open_interest: float = 0.0
    implied_volatility: float | None = None
    delta: float | None = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 4)
        return self.last or self.ask or self.bid


@dataclass(frozen=True)
class OrderRequest:
    """A request to open or close a position. Broker-neutral.

    ``qty`` is in shares for equities and contracts for options. For options the
    ``symbol`` is the OCC option symbol.
    """

    symbol: str
    qty: float
    side: Side
    asset_class: AssetClass = AssetClass.EQUITY
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    # Protective legs for an entry (equities). When either is set the Alpaca
    # broker submits a bracket/OTO order so the stop persists between cycles.
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    client_order_id: str | None = None
    # Free-form rationale recorded in the journal (never sent to the broker).
    rationale: str = ""

    @property
    def is_protected(self) -> bool:
        return self.stop_loss_price is not None or self.take_profit_price is not None


    def notional_estimate(self, price: float) -> float:
        """Estimated dollar cost. Options are priced per-share (×100 multiplier)."""
        multiplier = 100 if self.asset_class is AssetClass.OPTION else 1
        return abs(self.qty) * price * multiplier


@dataclass(frozen=True)
class Order:
    """A submitted order as the broker reports it."""

    id: str
    symbol: str
    qty: float
    side: Side
    status: str
    asset_class: AssetClass = AssetClass.EQUITY
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    submitted_at: datetime | None = None
    raw: dict = field(default_factory=dict)
