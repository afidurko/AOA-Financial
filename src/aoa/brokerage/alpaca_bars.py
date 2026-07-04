"""Fetch stock and crypto OHLCV bars from Alpaca.

Crypto historical data is public (no API keys). Stock bars require
``ALPACA_API_KEY_ID`` and ``ALPACA_API_SECRET_KEY``.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest

from aoa.brokerage.alpaca import (
    _bars_from_sdk_rows,
    _crypto_window,
    _parse_adjustment,
    _parse_timeframe,
    _sdk_error_message,
)
from aoa.brokerage.base import BrokerError
from aoa.brokerage.constants import VALID_ALPACA_DATA_FEEDS
from aoa.brokerage.models import Bar

_FEED_MAP = {
    "sip": DataFeed.SIP,
    "iex": DataFeed.IEX,
    "boats": DataFeed.BOATS,
    "otc": DataFeed.OTC,
}

_STOCK_KEYS_HELP = (
    "Stock bars need Alpaca API keys. Copy .env.example to .env, then add "
    "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY from "
    "https://app.alpaca.markets/ (paper Trading API keys starting with PK)."
)


def is_crypto_symbol(symbol: str) -> bool:
    """True for Alpaca crypto pairs such as ``BTC/USD``."""
    return "/" in symbol


def partition_symbols(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Split symbols into ``(crypto_pairs, stock_tickers)``."""
    crypto: list[str] = []
    stocks: list[str] = []
    for raw in symbols:
        sym = raw.strip()
        if not sym:
            continue
        if is_crypto_symbol(sym):
            crypto.append(sym.upper())
        else:
            stocks.append(sym.upper())
    return crypto, stocks


@dataclass
class AlpacaBarsConfig:
    key_id: str = ""
    secret_key: str = ""
    data_feed: str = ""
    bar_adjustment: str = "split"
    bar_feed: str = "iex"

    @property
    def has_stock_creds(self) -> bool:
        return bool(self.key_id and self.secret_key)


class AlpacaBarsFetcher:
    """Lightweight market-data client for stocks (auth) and crypto (public)."""

    def __init__(self, cfg: AlpacaBarsConfig | None = None) -> None:
        cfg = cfg or AlpacaBarsConfig()
        self._cfg = cfg
        self._crypto = CryptoHistoricalDataClient()
        self._stock: StockHistoricalDataClient | None = None
        if cfg.has_stock_creds:
            self._stock = StockHistoricalDataClient(
                api_key=cfg.key_id,
                secret_key=cfg.secret_key,
            )

    def close(self) -> None:
        for client in (self._crypto, self._stock):
            if client is None:
                continue
            session = getattr(client, "_session", None)
            if session is not None:
                session.close()

    def __enter__(self) -> AlpacaBarsFetcher:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def fetch(
        self,
        symbols: list[str],
        *,
        timeframe: str = "1Day",
        limit: int = 7,
    ) -> dict[str, list[Bar]]:
        """Return OHLCV bars keyed by symbol (oldest first)."""
        crypto, stocks = partition_symbols(symbols)
        out: dict[str, list[Bar]] = {}
        if crypto:
            out.update(self.fetch_crypto(crypto, timeframe=timeframe, limit=limit))
        if stocks:
            out.update(self.fetch_stocks(stocks, timeframe=timeframe, limit=limit))
        return out

    def fetch_crypto(
        self,
        symbols: list[str],
        *,
        timeframe: str = "1Day",
        limit: int = 7,
    ) -> dict[str, list[Bar]]:
        uniq = list(dict.fromkeys(s.upper() for s in symbols if s))
        if not uniq:
            return {}
        start, end = _crypto_window(timeframe, limit)
        request = CryptoBarsRequest(
            symbol_or_symbols=uniq,
            timeframe=_parse_timeframe(timeframe),
            start=start,
            end=end,
        )
        try:
            bar_set = self._crypto.get_crypto_bars(request)
        except APIError as exc:
            raise BrokerError(_sdk_error_message(exc)) from exc
        return _bars_by_symbol(bar_set, uniq, limit)

    def fetch_stocks(
        self,
        symbols: list[str],
        *,
        timeframe: str = "1Day",
        limit: int = 7,
    ) -> dict[str, list[Bar]]:
        if self._stock is None:
            raise BrokerError(_STOCK_KEYS_HELP)
        uniq = list(dict.fromkeys(s.upper() for s in symbols if s))
        if not uniq:
            return {}
        kwargs: dict = {
            "symbol_or_symbols": uniq,
            "timeframe": _parse_timeframe(timeframe),
            "limit": limit,
            "adjustment": _parse_adjustment(self._cfg.bar_adjustment),
        }
        start, end = _crypto_window(timeframe, limit)
        kwargs["start"] = start
        kwargs["end"] = end
        feed = self._cfg.data_feed.strip().lower() or self._cfg.bar_feed.strip().lower()
        if feed not in VALID_ALPACA_DATA_FEEDS:
            raise BrokerError(
                f"Invalid Alpaca data feed {feed!r}; "
                f"expected one of {', '.join(sorted(VALID_ALPACA_DATA_FEEDS))}."
            )
        kwargs["feed"] = _FEED_MAP[feed]
        request = StockBarsRequest(**kwargs)
        try:
            bar_set = self._stock.get_stock_bars(request)
        except APIError as exc:
            raise BrokerError(_sdk_error_message(exc)) from exc
        return _bars_by_symbol(bar_set, uniq, limit)

    def verify_crypto(self, symbol: str = "BTC/USD", *, limit: int = 1) -> Bar:
        bars = self.fetch_crypto([symbol], limit=limit).get(symbol.upper(), [])
        if not bars:
            raise BrokerError(f"Crypto bars API returned no data for {symbol}.")
        return bars[-1]

    def verify_stocks(self, symbol: str = "SPY", *, limit: int = 1) -> Bar:
        bars = self.fetch_stocks([symbol], limit=limit).get(symbol.upper(), [])
        if not bars:
            raise BrokerError(
                f"Stock bars API reachable but returned no data for {symbol}. "
                "Check your market-data subscription or symbol."
            )
        return bars[-1]


def _bars_by_symbol(bar_set, symbols: list[str], limit: int) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    for sym in symbols:
        rows = bar_set.data.get(sym, []) if hasattr(bar_set, "data") else bar_set[sym]
        bars = _bars_from_sdk_rows(rows)
        if len(bars) > limit:
            bars = bars[-limit:]
        out[sym] = bars
    return out


def bars_config_from_env(cfg) -> AlpacaBarsConfig:
    """Build fetcher config from ``aoa.config.Config``."""
    return AlpacaBarsConfig(
        key_id=cfg.alpaca_key_id,
        secret_key=cfg.alpaca_secret_key,
        data_feed=cfg.alpaca_data_feed,
        bar_adjustment=cfg.alpaca_bar_adjustment,
        bar_feed=cfg.bar_feed,
    )
