"""Moomoo OpenAPI brokerage via locally running OpenD + ``moomoo-api`` SDK."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.models import (
    Account,
    AssetClass,
    Bar,
    OptionContract,
    Order,
    OrderRequest,
    OrderType,
    Position,
    Quote,
    Side,
    TimeInForce,
)
from aoa.brokerage.moomoo_symbols import from_moomoo_code, to_moomoo_code

_TIMEFRAME_TO_KTYPE = {
    "1Min": "K_1M",
    "3Min": "K_3M",
    "5Min": "K_5M",
    "15Min": "K_15M",
    "30Min": "K_30M",
    "1Hour": "K_60M",
    "1Day": "K_DAY",
    "1Week": "K_WEEK",
    "12Month": "K_YEAR",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class MoomooBroker(Broker):
    """Moomoo US securities account through OpenD (127.0.0.1:11111 by default)."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        trd_env: str = "SIMULATE",
        security_firm: str = "FUTUINC",
        account_id: int = 0,
        market: str = "US",
    ) -> None:
        self._host = host
        self._port = int(port)
        self._trd_env_name = trd_env.strip().upper()
        self._security_firm_name = security_firm.strip().upper()
        self._account_id = int(account_id or 0)
        self._market = market.strip().upper() or "US"
        self.is_live = self._trd_env_name == "REAL"
        self.name = "moomoo-live" if self.is_live else "moomoo-simulate"
        self._quote_ctx: Any = None
        self._trade_ctx: Any = None
        self._ft: Any = None

    def _sdk(self) -> Any:
        if self._ft is not None:
            return self._ft
        try:
            import moomoo as ft  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise BrokerError(
                "moomoo-api is not installed. Run: pip install -e \".[moomoo]\""
            ) from exc
        self._ft = ft
        return ft

    def _trd_env(self) -> Any:
        ft = self._sdk()
        return ft.TrdEnv.REAL if self._trd_env_name == "REAL" else ft.TrdEnv.SIMULATE

    def _security_firm(self) -> Any:
        ft = self._sdk()
        mapping = {
            "FUTUINC": ft.SecurityFirm.FUTUINC,
            "FUTUSECURITIES": getattr(ft.SecurityFirm, "FUTUSECURITIES", ft.SecurityFirm.FUTUINC),
            "NONE": ft.SecurityFirm.NONE,
        }
        return mapping.get(self._security_firm_name, ft.SecurityFirm.FUTUINC)

    def _quote(self) -> Any:
        if self._quote_ctx is not None:
            return self._quote_ctx
        ft = self._sdk()
        ctx = ft.OpenQuoteContext(host=self._host, port=self._port)
        self._quote_ctx = ctx
        return ctx

    def _trade(self) -> Any:
        if self._trade_ctx is not None:
            return self._trade_ctx
        ft = self._sdk()
        trd_market = getattr(ft.TrdMarket, self._market, ft.TrdMarket.US)
        ctx = ft.OpenSecTradeContext(
            filter_trdmarket=trd_market,
            host=self._host,
            port=self._port,
            security_firm=self._security_firm(),
        )
        self._trade_ctx = ctx
        return ctx

    def close(self) -> None:
        for ctx in (self._quote_ctx, self._trade_ctx):
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:  # noqa: BLE001
                    pass
        self._quote_ctx = None
        self._trade_ctx = None

    def _check_ret(self, ret: int, data: Any, action: str) -> Any:
        ft = self._sdk()
        if ret == ft.RET_OK:
            return data
        raise BrokerError(f"Moomoo {action} failed: {data}")

    # --- Account & positions -------------------------------------------------
    def get_account(self) -> Account:
        trd = self._trade()
        ret, data = trd.accinfo_query(
            trd_env=self._trd_env(),
            acc_id=self._account_id or 0,
        )
        row = self._check_ret(ret, data, "accinfo_query").iloc[0]
        cash = _f(row.get("cash"))
        power = _f(row.get("power")) or _f(row.get("max_power_short")) or cash
        equity = _f(row.get("total_assets")) or cash
        return Account(
            equity=equity,
            cash=cash,
            buying_power=power,
            settled_cash=cash,
            options_level=0,
            currency=str(row.get("currency", "USD") or "USD"),
        )

    def get_positions(self) -> list[Position]:
        trd = self._trade()
        ret, data = trd.position_list_query(
            trd_env=self._trd_env(),
            acc_id=self._account_id or 0,
        )
        df = self._check_ret(ret, data, "position_list_query")
        positions: list[Position] = []
        for _, row in df.iterrows():
            qty = _f(row.get("qty"))
            if qty == 0:
                continue
            code = str(row.get("code", ""))
            symbol = from_moomoo_code(code)
            price = _f(row.get("price"))
            positions.append(
                Position(
                    symbol=symbol,
                    asset_class=AssetClass.EQUITY,
                    qty=qty,
                    avg_entry_price=_f(row.get("cost_price")),
                    market_value=_f(row.get("market_val")) or qty * price,
                    unrealized_pl=_f(row.get("pl_val")),
                    current_price=price,
                )
            )
        return positions

    # --- Market data ---------------------------------------------------------
    def get_quote(self, symbol: str) -> Quote:
        code = to_moomoo_code(symbol, market=self._market)
        quote = self._quote()
        ret, data = quote.get_market_snapshot([code])
        df = self._check_ret(ret, data, "get_market_snapshot")
        row = df.iloc[0]
        return Quote(
            symbol=from_moomoo_code(str(row.get("code", code))),
            bid=_f(row.get("bid_price")),
            ask=_f(row.get("ask_price")),
            bid_size=_f(row.get("bid_vol")),
            ask_size=_f(row.get("ask_vol")),
            timestamp=_parse_ts(row.get("update_time")),
        )

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 120) -> list[Bar]:
        code = to_moomoo_code(symbol, market=self._market)
        quote = self._quote()
        ft = self._sdk()
        ktype_name = _TIMEFRAME_TO_KTYPE.get(timeframe, "K_DAY")
        ktype = getattr(ft.KLType, ktype_name, ft.KLType.K_DAY)
        ret, data, _ = quote.request_history_kline(
            code,
            ktype=ktype,
            max_count=max(1, min(limit, 1000)),
        )
        df = self._check_ret(ret, data, "request_history_kline")
        bars: list[Bar] = []
        for _, row in df.iterrows():
            ts = _parse_ts(row.get("time_key"))
            if ts is None:
                continue
            bars.append(
                Bar(
                    timestamp=ts,
                    open=_f(row.get("open")),
                    high=_f(row.get("high")),
                    low=_f(row.get("low")),
                    close=_f(row.get("close")),
                    volume=_f(row.get("volume")),
                )
            )
        return bars

    def get_most_active(self, limit: int = 25) -> list[str]:
        # Moomoo has no Alpaca-style most-actives screener in the adapter yet.
        seeds = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "SPY", "QQQ", "TSLA")
        return list(seeds[: max(1, limit)])

    def get_option_chain(
        self,
        underlying: str,
        expiration: str | None = None,
        option_type: str | None = None,
    ) -> list[OptionContract]:
        # Phase 2: wire Moomoo option chain APIs. Equities-only cycles work without this.
        return []

    # --- Orders --------------------------------------------------------------
    def submit_order(self, request: OrderRequest) -> Order:
        if request.is_protected:
            raise BrokerError(
                "Moomoo adapter does not yet submit bracket/OTO protective orders; "
                "use plain market/limit entries or extend the adapter."
            )
        if request.asset_class is AssetClass.OPTION:
            raise BrokerError("Moomoo options orders are not implemented in this adapter yet.")

        ft = self._sdk()
        trd = self._trade()
        code = to_moomoo_code(request.symbol, market=self._market)
        trd_side = ft.TrdSide.BUY if request.side is Side.BUY else ft.TrdSide.SELL
        order_type = (
            ft.OrderType.NORMAL
            if request.order_type is OrderType.LIMIT
            else ft.OrderType.MARKET
        )
        tif = (
            ft.TimeInForce.DAY
            if request.time_in_force is TimeInForce.DAY
            else ft.TimeInForce.GTC
        )
        kwargs: dict[str, Any] = {
            "price": request.limit_price or 0.0,
            "qty": int(request.qty),
            "code": code,
            "trd_side": trd_side,
            "order_type": order_type,
            "trd_env": self._trd_env(),
            "acc_id": self._account_id or 0,
            "time_in_force": tif,
            "remark": (request.client_order_id or "")[:64] or None,
        }
        if request.order_type is OrderType.MARKET:
            snap = self.get_quote(request.symbol)
            kwargs["price"] = snap.ask if request.side is Side.BUY else snap.bid or snap.mid
        ret, data = trd.place_order(**kwargs)
        df = self._check_ret(ret, data, "place_order")
        row = df.iloc[0]
        return Order(
            id=str(row.get("order_id", "")),
            symbol=from_moomoo_code(code),
            qty=_f(row.get("qty")),
            side=request.side,
            status=str(row.get("order_status", "submitted")),
            asset_class=request.asset_class,
            raw=row.to_dict() if hasattr(row, "to_dict") else {},
        )

    def list_orders(self, status: str = "open") -> list[Order]:
        trd = self._trade()
        ret, data = trd.order_list_query(
            trd_env=self._trd_env(),
            acc_id=self._account_id or 0,
        )
        df = self._check_ret(ret, data, "order_list_query")
        orders: list[Order] = []
        for _, row in df.iterrows():
            st = str(row.get("order_status", "")).lower()
            if status == "open" and st in {"filled", "cancelled", "failed"}:
                continue
            code = str(row.get("code", ""))
            side_raw = str(row.get("trd_side", "")).lower()
            side = Side.BUY if "buy" in side_raw else Side.SELL
            orders.append(
                Order(
                    id=str(row.get("order_id", "")),
                    symbol=from_moomoo_code(code),
                    qty=_f(row.get("qty")),
                    side=side,
                    status=st or "unknown",
                    filled_qty=_f(row.get("dealt_qty")),
                    filled_avg_price=_f(row.get("dealt_avg_price")) or None,
                )
            )
        return orders

    def cancel_order(self, order_id: str) -> None:
        ft = self._sdk()
        trd = self._trade()
        ret, data = trd.modify_order(
            ft.ModifyOrderOp.CANCEL,
            str(order_id),
            0,
            0,
            trd_env=self._trd_env(),
            acc_id=self._account_id or 0,
        )
        self._check_ret(ret, data, "cancel_order")

    def is_market_open(self) -> bool:
        ft = self._sdk()
        code = to_moomoo_code("AAPL", market=self._market)
        ret, data = self._quote().get_market_state([code])
        df = self._check_ret(ret, data, "get_market_state")
        row = df.iloc[0]
        state = row.get("market_us") or row.get("market_state")
        open_states = {
            getattr(ft.MarketState, name, None)
            for name in ("AFTERNOON", "MORNING", "FUTURE_OPEN")
        }
        open_states.discard(None)
        return state in open_states or str(state).endswith("AFTERNOON")

    def ping(self) -> None:
        """Verify OpenD is reachable."""
        self.get_account()
