"""Alpaca brokerage implementation.

Uses the Alpaca Trading API (account, positions, orders, clock) and the Alpaca
Market Data API (quotes, bars, most-actives, option chains) over plain HTTPS via
``httpx``. No third-party Alpaca SDK is required, which keeps the dependency
surface small and the behavior transparent.

Endpoint references:
- Trading:    https://{paper-,}api.alpaca.markets/v2/...
- Market data: https://data.alpaca.markets/v2 (stocks) and /v1beta1 (options, screener)
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from aoa.brokerage.base import Broker, BrokerError
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

TRADING_LIVE = "https://api.alpaca.markets"
TRADING_PAPER = "https://paper-api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class AlpacaBroker(Broker):
    def __init__(
        self,
        key_id: str,
        secret_key: str,
        *,
        live: bool = False,
        timeout: float = 20.0,
    ) -> None:
        if not key_id or not secret_key:
            raise BrokerError("Alpaca credentials are required.")
        self.is_live = live
        self.name = "alpaca-live" if live else "alpaca-paper"
        self._trading_base = TRADING_LIVE if live else TRADING_PAPER
        headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(headers=headers, timeout=timeout)

    # --- low-level helpers ---------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> dict | list:
        try:
            resp = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:  # network error
            raise BrokerError(f"Alpaca network error: {exc}") from exc
        if resp.status_code >= 400:
            raise BrokerError(
                f"Alpaca API {resp.status_code} for {method} {url}: {resp.text[:400]}"
            )
        if not resp.content:
            return {}
        return resp.json()

    def _trading(self, method: str, path: str, **kwargs) -> dict | list:
        return self._request(method, f"{self._trading_base}{path}", **kwargs)

    def _data(self, method: str, path: str, **kwargs) -> dict | list:
        return self._request(method, f"{DATA_BASE}{path}", **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AlpacaBroker:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- account & positions -------------------------------------------------
    def get_account(self) -> Account:
        d = self._trading("GET", "/v2/account")
        assert isinstance(d, dict)
        return Account(
            equity=_f(d.get("equity")),
            cash=_f(d.get("cash")),
            buying_power=_f(d.get("buying_power")),
            # Non-marginable buying power is the immediately usable cash in a cash account.
            settled_cash=_f(
                d.get("non_marginable_buying_power", d.get("cash"))
            ),
            options_level=int(_f(d.get("options_approved_level", 0))),
            daytrade_count=int(_f(d.get("daytrade_count", 0))),
            pattern_day_trader=bool(d.get("pattern_day_trader", False)),
            currency=d.get("currency", "USD"),
        )

    def get_positions(self) -> list[Position]:
        rows = self._trading("GET", "/v2/positions")
        positions: list[Position] = []
        for r in rows if isinstance(rows, list) else []:
            ac = (
                AssetClass.OPTION
                if r.get("asset_class") == "us_option"
                else AssetClass.EQUITY
            )
            positions.append(
                Position(
                    symbol=r.get("symbol", ""),
                    asset_class=ac,
                    qty=_f(r.get("qty")),
                    avg_entry_price=_f(r.get("avg_entry_price")),
                    market_value=_f(r.get("market_value")),
                    unrealized_pl=_f(r.get("unrealized_pl")),
                    current_price=_f(r.get("current_price")),
                )
            )
        return positions

    # --- market data ---------------------------------------------------------
    def get_quote(self, symbol: str) -> Quote:
        d = self._data("GET", f"/v2/stocks/{symbol}/quotes/latest")
        q = d.get("quote", {}) if isinstance(d, dict) else {}
        return Quote(
            symbol=symbol,
            bid=_f(q.get("bp")),
            ask=_f(q.get("ap")),
            bid_size=_f(q.get("bs")),
            ask_size=_f(q.get("as")),
            timestamp=_parse_ts(q.get("t")),
        )

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 120) -> list[Bar]:
        params = {"timeframe": timeframe, "limit": limit, "adjustment": "split"}
        d = self._data("GET", f"/v2/stocks/{symbol}/bars", params=params)
        rows = d.get("bars", []) if isinstance(d, dict) else []
        bars: list[Bar] = []
        for r in rows:
            ts = _parse_ts(r.get("t"))
            if ts is None:
                continue
            bars.append(
                Bar(
                    timestamp=ts,
                    open=_f(r.get("o")),
                    high=_f(r.get("h")),
                    low=_f(r.get("l")),
                    close=_f(r.get("c")),
                    volume=_f(r.get("v")),
                )
            )
        return bars

    def get_most_active(self, limit: int = 25) -> list[str]:
        params = {"by": "volume", "top": limit}
        try:
            d = self._data("GET", "/v1beta1/screener/stocks/most-actives", params=params)
        except BrokerError:
            return []
        rows = d.get("most_actives", []) if isinstance(d, dict) else []
        return [r.get("symbol", "") for r in rows if r.get("symbol")]

    # --- options -------------------------------------------------------------
    def get_option_chain(
        self,
        underlying: str,
        expiration: str | None = None,
        option_type: str | None = None,
    ) -> list[OptionContract]:
        params: dict = {"limit": 100, "feed": "indicative"}
        if expiration:
            params["expiration_date"] = expiration
        if option_type:
            params["type"] = option_type  # "call" | "put"
        try:
            d = self._data("GET", f"/v1beta1/options/snapshots/{underlying}", params=params)
        except BrokerError:
            return []
        snapshots = d.get("snapshots", {}) if isinstance(d, dict) else {}
        oi_by_symbol = self._fetch_open_interest(underlying, expiration=expiration)
        contracts: list[OptionContract] = []
        for occ_symbol, snap in snapshots.items():
            parsed = _parse_occ(occ_symbol)
            if parsed is None:
                continue
            otype, strike, expiry = parsed
            quote = snap.get("latestQuote", {}) or {}
            trade = snap.get("latestTrade", {}) or {}
            greeks = snap.get("greeks", {}) or {}
            oi = oi_by_symbol.get(occ_symbol)
            if oi is None:
                oi = _f(snap.get("openInterest"))
            contracts.append(
                OptionContract(
                    symbol=occ_symbol,
                    underlying=underlying,
                    option_type=otype,
                    strike=strike,
                    expiration=expiry,
                    bid=_f(quote.get("bp")),
                    ask=_f(quote.get("ap")),
                    last=_f(trade.get("p")),
                    open_interest=oi,
                    implied_volatility=(
                        _f(snap.get("impliedVolatility"))
                        if snap.get("impliedVolatility") is not None
                        else None
                    ),
                    delta=_f(greeks.get("delta")) if greeks.get("delta") is not None else None,
                )
            )
        contracts.sort(key=lambda c: (c.expiration, c.option_type.value, c.strike))
        return contracts

    def _fetch_open_interest(
        self, underlying: str, *, expiration: str | None = None
    ) -> dict[str, float]:
        """Open interest lives on the trading API, not the data snapshot."""
        params: dict = {
            "underlying_symbols": underlying,
            "status": "active",
            "limit": 1000,
        }
        if expiration:
            params["expiration_date"] = expiration
        try:
            rows = self._trading("GET", "/v2/options/contracts", params=params)
        except BrokerError:
            return {}
        out: dict[str, float] = {}
        for row in rows if isinstance(rows, list) else []:
            sym = row.get("symbol")
            if sym:
                out[sym] = _f(row.get("open_interest"))
        return out

    # --- orders --------------------------------------------------------------
    def submit_order(self, request: OrderRequest) -> Order:
        payload: dict = {
            "symbol": request.symbol,
            "qty": str(request.qty),
            "side": request.side.value,
            "type": request.order_type.value,
            "time_in_force": request.time_in_force.value,
        }
        if request.limit_price is not None:
            payload["limit_price"] = str(request.limit_price)
        if request.client_order_id:
            payload["client_order_id"] = request.client_order_id
        d = self._trading("POST", "/v2/orders", json=payload)
        assert isinstance(d, dict)
        return _order_from_payload(d)

    def list_orders(self, status: str = "open") -> list[Order]:
        rows = self._trading("GET", "/v2/orders", params={"status": status, "limit": 100})
        return [_order_from_payload(r) for r in rows] if isinstance(rows, list) else []

    def cancel_order(self, order_id: str) -> None:
        self._trading("DELETE", f"/v2/orders/{order_id}")

    # --- clock ---------------------------------------------------------------
    def is_market_open(self) -> bool:
        d = self._trading("GET", "/v2/clock")
        return bool(d.get("is_open")) if isinstance(d, dict) else False


def _order_from_payload(d: dict) -> Order:
    ac = AssetClass.OPTION if d.get("asset_class") == "us_option" else AssetClass.EQUITY
    side_raw = d.get("side", "buy")
    return Order(
        id=d.get("id", ""),
        symbol=d.get("symbol", ""),
        qty=_f(d.get("qty")),
        side=Side(side_raw) if side_raw in (s.value for s in Side) else Side.BUY,
        status=d.get("status", "unknown"),
        asset_class=ac,
        filled_qty=_f(d.get("filled_qty")),
        filled_avg_price=(
            _f(d.get("filled_avg_price")) if d.get("filled_avg_price") else None
        ),
        submitted_at=_parse_ts(d.get("submitted_at")),
        raw=d,
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
