"""Executor — submits approved proposals to the broker (or simulates in dry-run).

Only proposals with ``approved == True`` are ever sent. In dry-run mode the
executor logs exactly what it *would* submit without touching the broker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aoa.agents.base import TradeProposal
from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.models import (
    AssetClass,
    Order,
    OrderRequest,
    OrderType,
    Side,
    TimeInForce,
)
from aoa.journal.store import Journal

if TYPE_CHECKING:
    from aoa.state import StateStore


@dataclass
class ExecutionReport:
    submitted: list[Order] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False


class Executor:
    def __init__(
        self,
        broker: Broker,
        journal: Journal,
        *,
        dry_run: bool = False,
        state: StateStore | None = None,
    ) -> None:
        self.broker = broker
        self.journal = journal
        self.dry_run = dry_run
        self.state = state

    def execute(self, proposals: list[TradeProposal]) -> ExecutionReport:
        report = ExecutionReport(dry_run=self.dry_run)
        open_order_keys = self._open_order_keys()

        for prop in proposals:
            if not prop.approved:
                report.skipped.append(
                    {"symbol": prop.symbol, "reason": "; ".join(prop.risk_notes)}
                )
                continue
            if prop.qty <= 0:
                report.skipped.append({"symbol": prop.symbol, "reason": "zero quantity"})
                continue

            order_key = (prop.symbol.upper(), prop.side)
            if order_key in open_order_keys:
                reason = "duplicate open order for same symbol and side"
                report.skipped.append({"symbol": prop.symbol, "reason": reason})
                self.journal.record(
                    "order.skipped",
                    {"symbol": prop.symbol, "side": prop.side.value, "reason": reason},
                )
                continue

            request = self._to_request(prop)

            if self.dry_run:
                self.journal.record(
                    "order.dry_run",
                    {"request": _request_ctx(request), "rationale": prop.rationale},
                )
                report.skipped.append({"symbol": prop.symbol, "reason": "dry-run"})
                continue

            try:
                order = self.broker.submit_order(request)
                report.submitted.append(order)
                open_order_keys.add(order_key)
                # Record sale proceeds as unsettled (T+1) so the swarm does not
                # redeploy them before settlement and trip a good-faith violation.
                if self.state is not None and prop.side is Side.SELL:
                    self.state.record_sale(prop.est_notional)
                self.journal.record(
                    "order.submitted",
                    {
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "qty": order.qty,
                        "status": order.status,
                        "rationale": prop.rationale,
                    },
                )
            except BrokerError as exc:
                report.errors.append({"symbol": prop.symbol, "error": str(exc)})
                self.journal.record(
                    "order.error", {"symbol": prop.symbol, "error": str(exc)}
                )
        return report

    def _open_order_keys(self) -> set[tuple[str, Side]]:
        if self.dry_run:
            return set()
        try:
            orders = self.broker.list_orders(status="open")
        except BrokerError as exc:
            self.journal.record("broker.error", {"op": "list_orders", "error": str(exc)})
            return set()
        return {(o.symbol.upper(), o.side) for o in orders}

    @staticmethod
    def _to_request(prop: TradeProposal) -> OrderRequest:
        # Use a marketable limit when we have a price estimate, otherwise market.
        order_type = OrderType.LIMIT if prop.limit_price else OrderType.MARKET
        # Protective legs only attach to opening equity buys.
        is_entry = prop.side is Side.BUY and prop.asset_class is AssetClass.EQUITY
        return OrderRequest(
            symbol=prop.symbol,
            qty=prop.qty,
            side=prop.side,
            asset_class=prop.asset_class,
            order_type=order_type,
            time_in_force=TimeInForce.DAY,
            limit_price=prop.limit_price,
            stop_loss_price=prop.stop_price if is_entry else None,
            take_profit_price=prop.take_profit_price if is_entry else None,
            client_order_id=f"aoa-{uuid.uuid4().hex[:16]}",
            rationale=prop.rationale,
        )


def _request_ctx(r: OrderRequest) -> dict:
    return {
        "symbol": r.symbol,
        "qty": r.qty,
        "side": r.side.value,
        "asset_class": r.asset_class.value,
        "order_type": r.order_type.value,
        "limit_price": r.limit_price,
        "stop_loss_price": r.stop_loss_price,
        "take_profit_price": r.take_profit_price,
    }
