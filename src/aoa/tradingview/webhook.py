"""TradingView alert webhook → human-gated proposal queue.

TradingView fires an HTTP POST with the strategy's ``alert_message`` JSON
(see :mod:`aoa.tradingview.pine`). This module validates it, journals it,
runs it through the fly connectome as an *ascending* sensory event, and
stores a **pending proposal**. Nothing is executed: approving a proposal only
records the human's decision; order placement stays with the existing
risk-guarded broker path, which this module never imports.

Security: set ``AOA_TRADINGVIEW_WEBHOOK_SECRET`` and either send it as the
``X-AOA-Token`` header or as a ``"token"`` field in the alert JSON. When the
secret is set and absent/mismatched, the alert is rejected.
"""

from __future__ import annotations

import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.tradingview.connectome import FlyConnectome, MarketSense
from aoa.tradingview.memory import DeskMemory
from aoa.tradingview.presets import PRESETS

VALID_EVENTS = ("enter_long", "enter_short", "exit_long", "exit_short")
DEFAULT_ALERTS_PATH = Path("data") / "tradingview" / "alerts.jsonl"


class WebhookError(ValueError):
    pass


@dataclass
class AlertRecord:
    id: str
    received_at: str
    preset: str
    event: str
    ticker: str
    exchange: str
    timeframe: str
    price: float | None
    market: str
    known_preset: bool
    memory_trust: float
    motor: dict[str, Any]
    status: str = "pending"  # pending | approved | rejected | acknowledged
    note: str = ""
    responded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def alerts_path() -> Path:
    override = os.environ.get("AOA_TRADINGVIEW_ALERTS_PATH")
    return Path(override) if override else DEFAULT_ALERTS_PATH


def _secret() -> str:
    return os.environ.get("AOA_TRADINGVIEW_WEBHOOK_SECRET", "")


def verify_token(payload: dict[str, Any], header_token: str | None) -> None:
    secret = _secret()
    if not secret:
        return
    supplied = header_token or str(payload.get("token") or "")
    if not supplied or not hmac.compare_digest(supplied, secret):
        raise WebhookError("invalid or missing webhook token")


def parse_alert(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WebhookError(f"alert body is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WebhookError("alert body must be a JSON object")
    if payload.get("source") != "aoa-tradingview":
        raise WebhookError("alert source is not aoa-tradingview")
    event = str(payload.get("event") or "")
    if event not in VALID_EVENTS:
        raise WebhookError(f"unknown event {event!r}")
    if not payload.get("ticker"):
        raise WebhookError("alert is missing ticker")
    return payload


def handle_alert(
    raw: str | bytes | dict[str, Any],
    *,
    header_token: str | None = None,
    memory: DeskMemory | None = None,
    path: Path | None = None,
    journal: Any | None = None,
) -> AlertRecord:
    """Validate, journal, connectome-step and persist one TradingView alert."""
    payload = parse_alert(raw)
    verify_token(payload, header_token)
    memory = memory or DeskMemory.load()
    brain = FlyConnectome.from_json(memory.connectome)
    preset_name = str(payload.get("preset") or "")
    ticker = str(payload["ticker"]).upper()
    tf = str(payload.get("tf") or "")
    event = str(payload["event"])
    price = payload.get("price")
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None
    market = str(payload.get("market") or ("crypto" if ticker.endswith(("USD", "USDT")) and preset_name.find("crypto") >= 0 else "equity"))
    trust = memory.recall(preset_name, ticker, tf) if preset_name else 0.0
    direction = 1.0 if event == "enter_long" else -1.0 if event == "enter_short" else 0.0
    exposure = 0.0 if event.startswith("enter") else (1.0 if event == "exit_long" else -1.0)
    sense = MarketSense(
        symbol=ticker,
        trend=direction,
        momentum=direction * 0.5,
        orderflow=0.0,
        volatility=0.2,
        drawdown=0.0,
        memory_trust=trust,
        exposure=exposure,
        fundamentals_ok=True,
    )
    motor = brain.step(sense, preset=preset_name).to_dict()
    memory.connectome = brain.to_json()
    record = AlertRecord(
        id=uuid.uuid4().hex[:12],
        received_at=datetime.now(tz=timezone.utc).isoformat(),
        preset=preset_name,
        event=event,
        ticker=ticker,
        exchange=str(payload.get("exchange") or ""),
        timeframe=tf,
        price=price_f,
        market=market,
        known_preset=preset_name in PRESETS,
        memory_trust=round(trust, 4),
        motor=motor,
    )
    memory.add_episode("tradingview.alert", {"id": record.id, "preset": preset_name, "event": event, "ticker": ticker, "tf": tf})
    memory.save()
    append_alert(record, path)
    if journal is not None:
        try:
            # Nest the record: its own ``event`` key (enter_long, …) must not shadow the journal's.
            journal.record(
                "tradingview.alert",
                {"alert_id": record.id, "tv_event": record.event, "alert": record.to_dict(), "requires_human": True},
            )
        except Exception:  # noqa: BLE001 - journaling must never break the webhook
            pass
    return record


def append_alert(record: AlertRecord, path: Path | None = None) -> Path:
    p = path or alerts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict(), default=str) + "\n")
    return p


def load_alerts(path: Path | None = None, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    p = path or alerts_path()
    if not p.is_file():
        return []
    rows: dict[str, dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[str(row.get("id"))] = row  # later lines (responses) override earlier state
    out = [r for r in rows.values() if not status or r.get("status") == status]
    out.sort(key=lambda r: r.get("received_at", ""), reverse=True)
    return out[:limit]


def respond_alert(alert_id: str, action: str, *, note: str = "", path: Path | None = None) -> dict[str, Any]:
    """Record the human decision. ``approve`` never places an order by itself."""
    action = action.lower().strip()
    mapping = {"approve": "approved", "reject": "rejected", "ack": "acknowledged"}
    if action not in mapping:
        raise WebhookError("action must be approve, reject or ack")
    rows = {r["id"]: r for r in load_alerts(path, limit=10_000)}
    row = rows.get(alert_id)
    if row is None:
        raise WebhookError(f"unknown alert id {alert_id}")
    row = dict(row)
    row["status"] = mapping[action]
    row["note"] = note
    row["responded_at"] = datetime.now(tz=timezone.utc).isoformat()
    record = AlertRecord(**{k: row[k] for k in AlertRecord.__dataclass_fields__ if k in row})
    append_alert(record, path)
    return {**record.to_dict(), "executed": False, "detail": "Decision recorded. Execution stays with the human-controlled broker path."}
