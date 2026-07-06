"""Moomoo brokerage via OpenD + ``moomoo-api``.

Requires Moomoo OpenD running locally (default ``127.0.0.1:11111``). US equities
and options use ``OpenSecTradeContext`` with ``TrdMarket.US``.
"""

from __future__ import annotations

import re
import socket
from datetime import datetime, timezone
from typing import Any

from aoa.brokerage.base import Broker, BrokerError
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

try:
    import moomoo as ft
except ImportError:  # pragma: no cover - optional until pip install
    ft = None  # type: ignore[assignment]

_US_PREFIX = "US."
_TIMEFRAME_MAP = {
    "1Min": "K_1M",
    "3Min": "K_3M",
    "5Min": "K_5M",
    "15Min": "K_15M",
    "1Hour": "K_60M",
    "1Day": "K_DAY",
    "12Month": "K_YEAR",
}
_OCC_TAIL_RE = re.compile(r"^(\d{6})([CP])(\d{8})$")
_DEFAULT_OPEND_CONNECT_TIMEOUT = 2.0


def opend_reachable(
    host: str,
    port: int,
    *,
    timeout: float = _DEFAULT_OPEND_CONNECT_TIMEOUT,
) -> bool:
    """Return True when the OpenD TCP port accepts a connection."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _require_sdk() -> Any:
    if ft is None:
        raise BrokerError(
            "moomoo-api is not installed. Run: pip install moomoo-api"
        )
    return ft


def to_moomoo_code(symbol: str, *, market: str = "US") -> str:
    """Map ``AAPL`` → ``US.AAPL`` for Moomoo OpenAPI."""
    sym = symbol.strip().upper()
    if not sym:
        return sym
    prefix = f"{market.upper()}."
    if "." in sym:
        return sym
    return f"{prefix}{sym}"


def from_moomoo_code(code: str) -> str:
    """Map ``US.AAPL`` → ``AAPL`` for AOA-internal symbols."""
    text = code.strip().upper()
    if text.startswith(_US_PREFIX):
        return text[len(_US_PREFIX) :]
    if "." in text:
        return text.split(".", 1)[1]
    return text


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return _ensure_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    try:
        return _ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _row_value(row: Any, key: str, default: Any = "") -> Any:
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return default


def _check_ret(ret: int, data: Any, *, action: str) -> Any:
    sdk = _require_sdk()
    if ret == sdk.RET_OK:
        return data
    raise BrokerError(f"Moomoo {action} failed: {data}")


def _parse_option_tail(tail: str) -> tuple[OptionType, float, str] | None:
    match = _OCC_TAIL_RE.fullmatch(tail)
    if not match:
        return None
    date_part, type_char, strike_part = match.groups()
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


def _parse_moomoo_option(code: str, underlying: str) -> tuple[OptionType, float, str] | None:
    bare = from_moomoo_code(code)
    root = underlying.upper()
    if not bare.startswith(root) or len(bare) <= len(root):
        return None
    return _parse_option_tail(bare[len(root) :])


class MoomooBroker(Broker):
    """US securities broker through Moomoo OpenD."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        live: bool = False,
        market: str = "US",
        security_firm: str = "FUTUINC",
        acc_id: int = 0,
        acc_index: int = 0,
        unlock_password: str = "",
        bar_feed: str = "iex",
    ) -> None:
        sdk = _require_sdk()
        del bar_feed  # Moomoo feed is tied to OpenD subscription
        self.is_live = live
        self.name = "moomoo-live" if live else "moomoo-paper"
        self._market = market.upper()
        self._host = host
        self._port = int(port)
        self._acc_id = int(acc_id)
        self._acc_index = int(acc_index)
        self._unlock_password = unlock_password.strip()
        self._trd_env = sdk.TrdEnv.REAL if live else sdk.TrdEnv.SIMULATE
        self._security_firm = getattr(
            sdk.SecurityFirm, security_firm.upper(), sdk.SecurityFirm.FUTUINC
        )
        self._trd_market = getattr(sdk.TrdMarket, self._market, sdk.TrdMarket.US)
        if not opend_reachable(self._host, self._port):
            raise BrokerError(
                f"Moomoo OpenD not reachable at {self._host}:{self._port}. "
                "Start OpenD locally or set AOA_BROKER=alpaca."
            )
        self._quote_ctx = sdk.OpenQuoteContext(host=self._host, port=self._port)
        self._trade_ctx = sdk.OpenSecTradeContext(
            filter_trdmarket=self._trd_market,
            host=self._host,
            port=self._port,
            security_firm=self._security_firm,
        )
        self._unlocked = False

    @classmethod
    def from_config(cls, cfg) -> MoomooBroker:
        return cls(
            host=cfg.moomoo_opend_host,
            port=cfg.moomoo_opend_port,
            live=cfg.moomoo_live,
            market=cfg.moomoo_market,
            security_firm=cfg.moomoo_security_firm,
            acc_id=cfg.moomoo_acc_id,
            acc_index=cfg.moomoo_acc_index,
            unlock_password=cfg.moomoo_unlock_password,
            bar_feed=cfg.bar_feed,
        )

    def _ensure_unlocked(self) -> None:
        if not self.is_live or self._unlocked or not self._unlock_password:
            return
        _require_sdk()
        ret, data = self._trade_ctx.unlock_trade(self._unlock_password)
        _check_ret(ret, data, action="unlock_trade")
        self._unlocked = True

    def close(self) -> None:
        for ctx in (self._quote_ctx, self._trade_ctx):
            close = getattr(ctx, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> MoomooBroker:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def get_account(self) -> Account:
        self._ensure_unlocked()
        ret, data = self._trade_ctx.accinfo_query(
            trd_env=self._trd_env,
            acc_id=self._acc_id,
            acc_index=self._acc_index,
            currency="USD",
        )
        _check_ret(ret, data, action="accinfo_query")
        if data is None or len(data) == 0:
            raise BrokerError("Moomoo accinfo_query returned no rows.")
        row = data.iloc[0]
        cash = _f(_row_value(row, "us_cash", _row_value(row, "cash", 0)))
        buying_power = _f(_row_value(row, "power", cash))
        settled = _f(_row_value(row, "avl_withdrawal_cash", cash))
        equity = _f(_row_value(row, "total_assets", buying_power))
        return Account(
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            settled_cash=settled or cash,
            options_level=2,
            currency="USD",
        )

    def get_positions(self) -> list[Position]:
        self._ensure_unlocked()
        ret, data = self._trade_ctx.position_list_query(
            trd_env=self._trd_env,
            acc_id=self._acc_id,
            acc_index=self._acc_index,
            currency="USD",
        )
        _check_ret(ret, data, action="position_list_query")
        if data is None or len(data) == 0:
            return []
        positions: list[Position] = []
        for _, row in data.iterrows():
            code = str(_row_value(row, "code", ""))
            symbol = from_moomoo_code(code)
            sec_type = str(_row_value(row, "position_type", "")).upper()
            asset_class = (
                AssetClass.OPTION if "OPTION" in sec_type else AssetClass.EQUITY
            )
            positions.append(
                Position(
                    symbol=symbol,
                    asset_class=asset_class,
                    qty=_f(_row_value(row, "qty", 0)),
                    avg_entry_price=_f(_row_value(row, "cost_price", 0)),
                    market_value=_f(_row_value(row, "market_val", 0)),
                    unrealized_pl=_f(_row_value(row, "pl_val", 0)),
                    current_price=_f(_row_value(row, "nominal_price", 0)),
                )
            )
        return positions

    def get_quote(self, symbol: str) -> Quote:
        return self.get_quotes_many([symbol]).get(symbol.upper(), Quote(symbol=symbol, bid=0, ask=0))

    def get_quotes_many(self, symbols: list[str]) -> dict[str, Quote]:
        codes = [to_moomoo_code(s, market=self._market) for s in symbols if s]
        if not codes:
            return {}
        ret, data = self._quote_ctx.get_market_snapshot(codes)
        _check_ret(ret, data, action="get_market_snapshot")
        out: dict[str, Quote] = {}
        if data is None:
            return out
        for _, row in data.iterrows():
            code = str(_row_value(row, "code", ""))
            sym = from_moomoo_code(code)
            bid_prices = _row_value(row, "bid_price", [])
            ask_prices = _row_value(row, "ask_price", [])
            bid = _f(bid_prices[0] if isinstance(bid_prices, (list, tuple)) and bid_prices else 0)
            ask = _f(ask_prices[0] if isinstance(ask_prices, (list, tuple)) and ask_prices else 0)
            last = _f(_row_value(row, "last_price", 0))
            if bid <= 0 and last > 0:
                bid = last
            if ask <= 0 and last > 0:
                ask = last
            out[sym] = Quote(
                symbol=sym,
                bid=bid,
                ask=ask,
                timestamp=_parse_ts(_row_value(row, "update_time", None)),
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
        sdk = _require_sdk()
        ktype = getattr(sdk.KLType, _TIMEFRAME_MAP.get(timeframe, "K_DAY"), sdk.KLType.K_DAY)
        out: dict[str, list[Bar]] = {}
        for symbol in symbols:
            if not symbol:
                continue
            sym = symbol.upper()
            code = to_moomoo_code(sym, market=self._market)
            ret, data, _page = self._quote_ctx.request_history_kline(
                code,
                ktype=ktype,
                max_count=max(1, limit),
            )
            _check_ret(ret, data, action=f"request_history_kline({sym})")
            bars: list[Bar] = []
            if data is not None and len(data) > 0:
                for _, row in data.iterrows():
                    bars.append(
                        Bar(
                            timestamp=_parse_ts(_row_value(row, "time_key", None))
                            or datetime.now(timezone.utc),
                            open=_f(_row_value(row, "open", 0)),
                            high=_f(_row_value(row, "high", 0)),
                            low=_f(_row_value(row, "low", 0)),
                            close=_f(_row_value(row, "close", 0)),
                            volume=_f(_row_value(row, "volume", 0)),
                        )
                    )
            if len(bars) > limit:
                bars = bars[-limit:]
            out[sym] = bars
        return out

    def verify_stock_bars(self, symbol: str = "AAPL", limit: int = 1) -> Bar:
        bars = self.get_bars(symbol, timeframe="1Day", limit=limit)
        if not bars:
            raise BrokerError(
                f"Moomoo bars API reachable but returned no data for {symbol}. "
                "Is OpenD running and logged in?"
            )
        return bars[-1]

    def get_most_active(self, limit: int = 25) -> list[str]:
        sdk = _require_sdk()
        ret, data = self._quote_ctx.get_us_pre_market_rank(count=max(1, limit))
        if ret == sdk.RET_OK and data is not None and len(data) > 0:
            code_col = "code" if "code" in data.columns else data.columns[0]
            return [from_moomoo_code(str(v)) for v in data[code_col].tolist()[:limit]]
        # Fallback when rank API is empty outside extended hours.
        ret2, snap = self._quote_ctx.get_market_snapshot(
            [to_moomoo_code(s, market=self._market) for s in ("AAPL", "MSFT", "NVDA", "SPY", "QQQ")]
        )
        if ret2 == sdk.RET_OK and snap is not None and len(snap) > 0:
            ranked = snap.sort_values("volume", ascending=False)
            return [from_moomoo_code(str(v)) for v in ranked["code"].tolist()[:limit]]
        return ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"][:limit]

    def get_option_chain(
        self,
        underlying: str,
        expiration: str | None = None,
        option_type: str | None = None,
    ) -> list[OptionContract]:
        sdk = _require_sdk()
        code = to_moomoo_code(underlying, market=self._market)
        kwargs: dict[str, Any] = {"code": code}
        if expiration:
            kwargs["start"] = expiration
            kwargs["end"] = expiration
        if option_type == "call":
            kwargs["option_type"] = sdk.OptionType.CALL
        elif option_type == "put":
            kwargs["option_type"] = sdk.OptionType.PUT
        ret, data = self._quote_ctx.get_option_chain(**kwargs)
        _check_ret(ret, data, action="get_option_chain")
        if data is None or len(data) == 0:
            return []
        option_codes = [str(v) for v in data["code"].tolist()]
        snapshots: dict[str, Any] = {}
        if option_codes:
            snap_ret, snap = self._quote_ctx.get_market_snapshot(option_codes[:400])
            if snap_ret == sdk.RET_OK and snap is not None:
                for _, row in snap.iterrows():
                    snapshots[str(_row_value(row, "code", ""))] = row
        contracts: list[OptionContract] = []
        root = underlying.upper()
        for _, row in data.iterrows():
            occ_code = str(_row_value(row, "code", ""))
            parsed = _parse_moomoo_option(occ_code, root)
            if parsed is None:
                strike = _f(_row_value(row, "strike_price", 0))
                expiry = str(_row_value(row, "strike_time", ""))[:10]
                otype_raw = str(_row_value(row, "option_type", "")).upper()
                otype = OptionType.PUT if "PUT" in otype_raw else OptionType.CALL
            else:
                otype, strike, expiry = parsed
            snap = snapshots.get(occ_code, {})
            bid_prices = _row_value(snap, "bid_price", [])
            ask_prices = _row_value(snap, "ask_price", [])
            bid = _f(bid_prices[0] if isinstance(bid_prices, (list, tuple)) and bid_prices else 0)
            ask = _f(ask_prices[0] if isinstance(ask_prices, (list, tuple)) and ask_prices else 0)
            last = _f(_row_value(snap, "last_price", 0))
            contracts.append(
                OptionContract(
                    symbol=from_moomoo_code(occ_code),
                    underlying=root,
                    option_type=otype,
                    strike=strike,
                    expiration=expiry,
                    bid=bid,
                    ask=ask,
                    last=last,
                    volume=_f(_row_value(snap, "volume", 0)),
                    open_interest=_f(_row_value(snap, "option_open_interest", 0)),
                    implied_volatility=_f(_row_value(snap, "option_implied_volatility", 0)) or None,
                    delta=_f(_row_value(snap, "option_delta", 0)) or None,
                )
            )
        contracts.sort(key=lambda c: (c.expiration, c.option_type.value, c.strike))
        return contracts

    def submit_order(self, request: OrderRequest) -> Order:
        if request.is_protected:
            raise BrokerError(
                "Moomoo broker does not support bracket/OTO protective orders yet."
            )
        self._ensure_unlocked()
        sdk = _require_sdk()
        code = to_moomoo_code(request.symbol, market=self._market)
        side = sdk.TrdSide.BUY if request.side is Side.BUY else sdk.TrdSide.SELL
        order_type = sdk.OrderType.NORMAL
        price = 0.0
        if request.order_type is OrderType.LIMIT:
            order_type = sdk.OrderType.NORMAL
            price = float(request.limit_price or 0)
        tif = (
            sdk.TimeInForce.GTC
            if request.time_in_force is TimeInForce.GTC
            else sdk.TimeInForce.DAY
        )
        ret, data = self._trade_ctx.place_order(
            price=price,
            qty=float(request.qty),
            code=code,
            trd_side=side,
            order_type=order_type,
            trd_env=self._trd_env,
            acc_id=self._acc_id,
            acc_index=self._acc_index,
            time_in_force=tif,
        )
        _check_ret(ret, data, action="place_order")
        if data is None or len(data) == 0:
            raise BrokerError("Moomoo place_order returned no order id.")
        row = data.iloc[0]
        return Order(
            id=str(_row_value(row, "order_id", "")),
            symbol=request.symbol.upper(),
            qty=float(request.qty),
            side=request.side,
            status="submitted",
            asset_class=request.asset_class,
            raw={"order_id": str(_row_value(row, "order_id", ""))},
        )

    def list_orders(self, status: str = "open") -> list[Order]:
        self._ensure_unlocked()
        sdk = _require_sdk()
        status_filter: list = []
        if status == "open":
            status_filter = [
                sdk.OrderStatus.SUBMITTED,
                sdk.OrderStatus.SUBMITTING,
                sdk.OrderStatus.WAITING_SUBMIT,
            ]
        ret, data = self._trade_ctx.order_list_query(
            trd_env=self._trd_env,
            acc_id=self._acc_id,
            acc_index=self._acc_index,
            status_filter_list=status_filter,
        )
        _check_ret(ret, data, action="order_list_query")
        if data is None or len(data) == 0:
            return []
        orders: list[Order] = []
        for _, row in data.iterrows():
            side_raw = str(_row_value(row, "trd_side", "")).upper()
            side = Side.BUY if "BUY" in side_raw else Side.SELL
            code = str(_row_value(row, "code", ""))
            orders.append(
                Order(
                    id=str(_row_value(row, "order_id", "")),
                    symbol=from_moomoo_code(code),
                    qty=_f(_row_value(row, "qty", 0)),
                    side=side,
                    status=str(_row_value(row, "order_status", "unknown")),
                    filled_qty=_f(_row_value(row, "dealt_qty", 0)),
                    filled_avg_price=_f(_row_value(row, "dealt_avg_price", 0)) or None,
                    submitted_at=_parse_ts(_row_value(row, "create_time", None)),
                )
            )
        return orders

    def cancel_order(self, order_id: str) -> None:
        self._ensure_unlocked()
        sdk = _require_sdk()
        ret, data = self._trade_ctx.modify_order(
            sdk.ModifyOrderOp.CANCEL,
            order_id,
            0,
            0,
            trd_env=self._trd_env,
            acc_id=self._acc_id,
            acc_index=self._acc_index,
        )
        _check_ret(ret, data, action="cancel_order")

    def is_market_open(self) -> bool:
        sdk = _require_sdk()
        code = to_moomoo_code("SPY", market=self._market)
        ret, data = self._quote_ctx.get_market_state([code])
        if ret != sdk.RET_OK or data is None or len(data) == 0:
            ret2, state = self._quote_ctx.get_global_state()
            if ret2 != sdk.RET_OK or state is None or len(state) == 0:
                return False
            market_state = str(state.iloc[0].get("market_us", ""))
            return "AFTER_HOURS" in market_state or "MORNING" in market_state or "TRADING" in market_state
        market_state = str(data.iloc[0].get("market_state", ""))
        return market_state not in {"CLOSED", "REST", "AFTER_HOURS_END", "NONE"}
