"""Alpaca brokerage implementation via the official ``alpaca-py`` SDK.

Uses ``TradingClient`` for account, positions, orders, and clock; market-data
clients for quotes, bars, most-actives, and option chains.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed, MostActivesBy, OptionsFeed
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.requests import (
    MostActivesRequest,
    OptionChainRequest,
    StockBarsRequest,
    StockLatestQuoteRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import ContractType, OrderSide, QueryOrderStatus
from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
from alpaca.trading.requests import (
    GetOptionContractsRequest,
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)

from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.constants import (
    VALID_ALPACA_BAR_ADJUSTMENTS,
    VALID_ALPACA_DATA_FEEDS,
)
from aoa.brokerage.models import (
    Account,
    AssetClass,
    Bar,
    OptionContract,
    OptionType,
    Order,
    OrderRequest,
    OrderType,
    Position,
    Quote,
    Side,
    TimeInForce,
)

T = TypeVar("T")

_TIMEFRAME_RE = re.compile(r"^(\d+)(Min|Hour|Day|Week|Month)$")
_FEED_MAP = {
    "sip": DataFeed.SIP,
    "iex": DataFeed.IEX,
    "boats": DataFeed.BOATS,
    "otc": DataFeed.OTC,
}

_ADJUSTMENT_MAP = {
    "raw": Adjustment.RAW,
    "split": Adjustment.SPLIT,
    "dividend": Adjustment.DIVIDEND,
    "all": Adjustment.ALL,
    "spin-off": Adjustment.ALL,
}


def _parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _settled_cash_from_alpaca(acct) -> float:
    """Conservative settled cash for cash-account risk sizing.

    Alpaca ``cash`` can include unsettled proceeds. Prefer the broker's
    non-marginable / withdrawable figures when present.
    """
    cash = _f(acct.cash)
    nmbp = getattr(acct, "non_marginable_buying_power", None)
    if nmbp is not None:
        settled = _f(nmbp)
        return min(cash, settled) if cash > 0 else settled
    withdrawable = getattr(acct, "cash_withdrawable", None)
    if withdrawable is not None:
        settled = _f(withdrawable)
        return min(cash, settled) if cash > 0 else settled
    return cash


def _parse_timeframe(value: str) -> TimeFrame:
    match = _TIMEFRAME_RE.fullmatch(value)
    if not match:
        return TimeFrame.Day
    amount = int(match.group(1))
    unit_key = match.group(2)
    unit_map = {
        "Min": TimeFrameUnit.Minute,
        "Hour": TimeFrameUnit.Hour,
        "Day": TimeFrameUnit.Day,
        "Week": TimeFrameUnit.Week,
        "Month": TimeFrameUnit.Month,
    }
    return TimeFrame(amount, unit_map[unit_key])


def _data_feed(name: str) -> DataFeed:
    return _FEED_MAP.get(name.lower(), DataFeed.IEX)


def _parse_adjustment(value: str) -> Adjustment:
    return _ADJUSTMENT_MAP.get(value, Adjustment.SPLIT)


def _bars_from_sdk_rows(rows) -> list[Bar]:
    bars: list[Bar] = []
    for row in rows:
        bars.append(
            Bar(
                timestamp=_ensure_utc(row.timestamp),
                open=_f(row.open),
                high=_f(row.high),
                low=_f(row.low),
                close=_f(row.close),
                volume=_f(row.volume),
            )
        )
    return bars


def _sdk_error_message(exc: APIError) -> str:
    status = exc.status_code
    base = f"Alpaca API {status}: {exc}" if status is not None else f"Alpaca API error: {exc}"
    if status == 401:
        base += (
            " Hint: Trading and market data require ALPACA_API_KEY_ID and "
            "ALPACA_API_SECRET_KEY (PK... keys from the Alpaca paper/live "
            "dashboard). Broker API OAuth (authx.alpaca.markets) is a "
            "different product and will not work here."
        )
    elif status == 403:
        base += (
            " Hint: your data subscription may not include the requested feed "
            "(try ALPACA_DATA_FEED=iex)."
        )
    return base


def _bar_from_sdk(row) -> Bar:
    return Bar(
        timestamp=_ensure_utc(row.timestamp),
        open=_f(row.open),
        high=_f(row.high),
        low=_f(row.low),
        close=_f(row.close),
        volume=_f(row.volume),
    )


class AlpacaBroker(Broker):
    def __init__(
        self,
        key_id: str,
        secret_key: str,
        *,
        live: bool = False,
        bar_feed: str = "iex",
        timeout: float = 20.0,
        data_feed: str = "",
        bar_adjustment: str = "split",
    ) -> None:
        if not key_id or not secret_key:
            raise BrokerError("Alpaca credentials are required.")
        if bar_feed not in _FEED_MAP:
            raise BrokerError(f"Unsupported Alpaca bar feed: {bar_feed}")
        del timeout  # alpaca-py manages HTTP timeouts internally
        self.is_live = live
        self.bar_feed = bar_feed
        self.name = "alpaca-live" if live else "alpaca-paper"
        self._data_feed = data_feed.strip().lower()
        self._bar_adjustment = bar_adjustment.strip().lower() or "split"
        if self._data_feed and self._data_feed not in VALID_ALPACA_DATA_FEEDS:
            raise BrokerError(
                f"Invalid Alpaca data feed {self._data_feed!r}; "
                f"expected one of {', '.join(sorted(VALID_ALPACA_DATA_FEEDS))}."
            )
        if self._bar_adjustment not in VALID_ALPACA_BAR_ADJUSTMENTS:
            raise BrokerError(
                f"Invalid bar adjustment {self._bar_adjustment!r}; "
                f"expected one of {', '.join(sorted(VALID_ALPACA_BAR_ADJUSTMENTS))}."
            )
        paper = not live
        creds = {"api_key": key_id, "secret_key": secret_key}
        self._trading = TradingClient(paper=paper, **creds)
        self._stock_data = StockHistoricalDataClient(**creds)
        self._screener = ScreenerClient(**creds)
        self._options_data = OptionHistoricalDataClient(**creds)

    def _sdk_call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        try:
            return fn(*args, **kwargs)
        except APIError as exc:
            raise BrokerError(_sdk_error_message(exc)) from exc

    def _stock_bars_request(
        self,
        symbols: list[str],
        timeframe: str,
        limit: int,
    ) -> StockBarsRequest:
        kwargs: dict = {
            "symbol_or_symbols": symbols,
            "timeframe": _parse_timeframe(timeframe),
            "limit": limit,
            "adjustment": _parse_adjustment(self._bar_adjustment),
        }
        if self._data_feed:
            kwargs["feed"] = _FEED_MAP[self._data_feed]
        return StockBarsRequest(**kwargs)

    def close(self) -> None:
        for client in (
            self._trading,
            self._stock_data,
            self._screener,
            self._options_data,
        ):
            session = getattr(client, "_session", None)
            if session is not None:
                session.close()

    def __enter__(self) -> AlpacaBroker:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- account & positions -------------------------------------------------
    def get_account(self) -> Account:
        acct = self._sdk_call(self._trading.get_account)
        return Account(
            equity=_f(acct.equity),
            cash=_f(acct.cash),
            buying_power=_f(acct.buying_power),
            settled_cash=_settled_cash_from_alpaca(acct),
            options_level=int(_f(acct.options_approved_level, 0)),
            daytrade_count=int(_f(acct.daytrade_count, 0)),
            pattern_day_trader=bool(acct.pattern_day_trader),
            currency=acct.currency or "USD",
        )

    def get_positions(self) -> list[Position]:
        rows = self._sdk_call(self._trading.get_all_positions)
        positions: list[Position] = []
        for row in rows:
            asset_class = (
                AssetClass.OPTION
                if getattr(row.asset_class, "value", row.asset_class) == "us_option"
                else AssetClass.EQUITY
            )
            positions.append(
                Position(
                    symbol=row.symbol,
                    asset_class=asset_class,
                    qty=_f(row.qty),
                    avg_entry_price=_f(row.avg_entry_price),
                    market_value=_f(row.market_value),
                    unrealized_pl=_f(row.unrealized_pl),
                    current_price=_f(row.current_price),
                )
            )
        return positions

    # --- market data ---------------------------------------------------------
    def get_quote(self, symbol: str) -> Quote:
        return self.get_quotes_many([symbol]).get(symbol.upper(), Quote(symbol=symbol, bid=0, ask=0))

    def get_quotes_many(self, symbols: list[str]) -> dict[str, Quote]:
        normalized = [s.upper() for s in symbols if s]
        if not normalized:
            return {}
        quotes = self._sdk_call(
            self._stock_data.get_stock_latest_quote,
            StockLatestQuoteRequest(
                symbol_or_symbols=normalized,
                feed=_data_feed(self.bar_feed),
            ),
        )
        out: dict[str, Quote] = {}
        for sym in normalized:
            q = quotes[sym]
            out[sym] = Quote(
                symbol=sym,
                bid=_f(q.bid_price),
                ask=_f(q.ask_price),
                bid_size=_f(q.bid_size),
                ask_size=_f(q.ask_size),
                timestamp=_ensure_utc(q.timestamp),
            )
        return out

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 120) -> list[Bar]:
        batch = self.get_bars_batch([symbol], timeframe, limit)
        return batch.get(symbol.upper(), [])

    def get_bars_batch(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        limit: int = 120,
    ) -> dict[str, list[Bar]]:
        """Fetch OHLCV bars for multiple symbols via ``get_stock_bars``."""
        uniq = list(dict.fromkeys(s.upper() for s in symbols if s))
        if not uniq:
            return {}

        request = self._stock_bars_request(uniq, timeframe, limit)
        bar_set = self._sdk_call(self._stock_data.get_stock_bars, request)
        out: dict[str, list[Bar]] = {}
        for sym in uniq:
            rows = bar_set.data.get(sym, []) if hasattr(bar_set, "data") else bar_set[sym]
            bars = _bars_from_sdk_rows(rows)
            if len(bars) > limit:
                bars = bars[-limit:]
            out[sym] = bars
        return out

    def verify_stock_bars(self, symbol: str = "AAPL", limit: int = 1) -> Bar:
        """Probe the authenticated stocks bars API.

        Unlike crypto historical data, stock bars require valid API keys. A 401/403
        from this call usually means missing or invalid ``ALPACA_API_KEY_ID`` /
        ``ALPACA_API_SECRET_KEY``.
        """
        bars = self.get_bars(symbol, timeframe="1Day", limit=limit)
        if not bars:
            raise BrokerError(
                f"Stock bars API reachable but returned no data for {symbol}. "
                "Check your market-data subscription or symbol."
            )
        return bars[-1]

    def get_most_active(self, limit: int = 25) -> list[str]:
        result = self._sdk_call(
            self._screener.get_most_actives,
            MostActivesRequest(by=MostActivesBy.VOLUME, top=limit),
        )
        return [row.symbol for row in result.most_actives if row.symbol]

    # --- options -------------------------------------------------------------
    def get_option_chain(
        self,
        underlying: str,
        expiration: str | None = None,
        option_type: str | None = None,
    ) -> list[OptionContract]:
        params: dict = {"underlying_symbol": underlying, "feed": OptionsFeed.INDICATIVE}
        if expiration:
            params["expiration_date"] = expiration
        if option_type:
            params["type"] = (
                ContractType.CALL if option_type == "call" else ContractType.PUT
            )
        snapshots = self._sdk_call(
            self._options_data.get_option_chain,
            OptionChainRequest(**params),
        )
        oi_by_symbol = self._fetch_open_interest(underlying, expiration=expiration)

        contracts: list[OptionContract] = []
        for occ_symbol, snap in snapshots.items():
            parsed = _parse_occ(occ_symbol)
            if parsed is None:
                continue
            otype, strike, expiry = parsed
            quote = snap.latest_quote
            trade = snap.latest_trade
            greeks = snap.greeks
            oi = oi_by_symbol.get(occ_symbol, 0.0)
            contracts.append(
                OptionContract(
                    symbol=occ_symbol,
                    underlying=underlying,
                    option_type=otype,
                    strike=strike,
                    expiration=expiry,
                    bid=_f(quote.bid_price) if quote else 0.0,
                    ask=_f(quote.ask_price) if quote else 0.0,
                    last=_f(trade.price) if trade else 0.0,
                    open_interest=oi or _f(getattr(snap, "open_interest", 0) or 0),
                    implied_volatility=(
                        float(snap.implied_volatility)
                        if snap.implied_volatility is not None
                        else None
                    ),
                    delta=float(greeks.delta) if greeks and greeks.delta is not None else None,
                )
            )
        contracts.sort(key=lambda c: (c.expiration, c.option_type.value, c.strike))
        return contracts

    def _fetch_open_interest(
        self, underlying: str, *, expiration: str | None = None
    ) -> dict[str, float]:
        """Open interest is on the trading API contracts endpoint, not snapshots."""
        req_kwargs: dict = {
            "underlying_symbols": [underlying],
            "status": "active",
            "limit": 1000,
        }
        if expiration:
            req_kwargs["expiration_date"] = expiration
        try:
            result = self._sdk_call(
                self._trading.get_option_contracts,
                GetOptionContractsRequest(**req_kwargs),
            )
        except BrokerError:
            return {}
        rows = getattr(result, "option_contracts", result) or []
        return {
            row.symbol: _f(row.open_interest)
            for row in rows
            if getattr(row, "symbol", None)
        }

    # --- orders --------------------------------------------------------------
    def submit_order(self, request: OrderRequest) -> Order:
        side = OrderSide.BUY if request.side is Side.BUY else OrderSide.SELL
        tif = (
            AlpacaTimeInForce.DAY
            if request.time_in_force is TimeInForce.DAY
            else AlpacaTimeInForce.GTC
        )
        common = {
            "symbol": request.symbol,
            "qty": request.qty,
            "side": side,
            "time_in_force": tif,
            "client_order_id": request.client_order_id,
        }
        if request.order_type is OrderType.LIMIT:
            sdk_request = LimitOrderRequest(
                **common,
                limit_price=request.limit_price,
            )
        else:
            sdk_request = MarketOrderRequest(**common)
        order = self._sdk_call(self._trading.submit_order, sdk_request)
        return _order_from_sdk(order)

    def list_orders(self, status: str = "open") -> list[Order]:
        status_map = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL,
        }
        rows = self._sdk_call(
            self._trading.get_orders,
            GetOrdersRequest(
                status=status_map.get(status, QueryOrderStatus.OPEN),
                limit=100,
            ),
        )
        return [_order_from_sdk(row) for row in rows]

    def cancel_order(self, order_id: str) -> None:
        self._sdk_call(self._trading.cancel_order_by_id, order_id)

    # --- clock ---------------------------------------------------------------
    def is_market_open(self) -> bool:
        clock = self._sdk_call(self._trading.get_clock)
        return bool(clock.is_open)


def _order_from_sdk(order) -> Order:
    asset_value = getattr(order.asset_class, "value", order.asset_class)
    ac = AssetClass.OPTION if asset_value == "us_option" else AssetClass.EQUITY
    side_value = getattr(order.side, "value", order.side)
    status_value = getattr(order.status, "value", order.status)
    return Order(
        id=str(order.id),
        symbol=order.symbol or "",
        qty=_f(order.qty),
        side=Side(side_value) if side_value in (s.value for s in Side) else Side.BUY,
        status=status_value or "unknown",
        asset_class=ac,
        filled_qty=_f(order.filled_qty),
        filled_avg_price=_f(order.filled_avg_price) if order.filled_avg_price else None,
        submitted_at=_parse_ts(order.submitted_at),
        raw=order.model_dump(mode="json") if hasattr(order, "model_dump") else {},
    )


def _parse_occ(symbol: str) -> tuple[OptionType, float, str] | None:
    """Parse an OCC option symbol such as ``AAPL250117C00150000``.

    Layout: ROOT (variable) + YYMMDD + C/P + strike*1000 (8 digits).
    """
    if len(symbol) < 15:
        return None
    tail = symbol[-15:]  # 6 (date) + 1 (type) + 8 (strike)
    date_part, type_char, strike_part = tail[:6], tail[6], tail[7:]
    if type_char not in ("C", "P") or not date_part.isdigit() or not strike_part.isdigit():
        return None
    try:
        yy = int(date_part[:2])
        mm = int(date_part[2:4])
        dd = int(date_part[4:6])
        expiry = datetime(2000 + yy, mm, dd, tzinfo=timezone.utc).date().isoformat()
    except ValueError:
        return None
    strike = int(strike_part) / 1000.0
    otype = OptionType.CALL if type_char == "C" else OptionType.PUT
    return otype, strike, expiry
