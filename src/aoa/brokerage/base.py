"""Abstract broker interface.

Any brokerage (Alpaca today; IBKR/Tradier tomorrow) implements this contract.
The swarm only ever talks to this interface, so swapping brokers does not touch
agent or orchestration code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from aoa.brokerage.models import (
    Account,
    Bar,
    OptionContract,
    Order,
    OrderRequest,
    Position,
    Quote,
)


class BrokerError(RuntimeError):
    """Raised for any brokerage API failure."""


class Broker(ABC):
    """Information source + order executor."""

    #: Human-readable identifier, e.g. "alpaca-paper".
    name: str = "broker"

    #: Whether this connection routes orders to real money.
    is_live: bool = False

    # --- Account & positions ------------------------------------------------
    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    # --- Market data (information source) ------------------------------------
    @abstractmethod
    def get_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 120) -> list[Bar]:
        """Return recent OHLCV bars, oldest first."""

    def get_bars_batch(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        limit: int = 120,
    ) -> dict[str, list[Bar]]:
        """Return recent OHLCV bars for multiple symbols, oldest first per symbol."""
        return {
            s.upper(): self.get_bars(s, timeframe, limit)
            for s in symbols
            if s
        }

    @abstractmethod
    def get_most_active(self, limit: int = 25) -> list[str]:
        """Return symbols of the most active equities (scanner seed list)."""

    # --- Options -------------------------------------------------------------
    @abstractmethod
    def get_option_chain(
        self,
        underlying: str,
        expiration: str | None = None,
        option_type: str | None = None,
    ) -> list[OptionContract]: ...

    # --- Order execution -----------------------------------------------------
    @abstractmethod
    def submit_order(self, request: OrderRequest) -> Order: ...

    @abstractmethod
    def list_orders(self, status: str = "open") -> list[Order]: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None: ...

    # --- Market clock --------------------------------------------------------
    @abstractmethod
    def is_market_open(self) -> bool: ...
