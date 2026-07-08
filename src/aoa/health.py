"""Connectivity checks shared by doctor and auto-activate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aoa.brokerage.alpaca_bars import AlpacaBarsFetcher, bars_config_from_env
from aoa.brokerage.base import BrokerError
from aoa.llm.client import LLMError

if TYPE_CHECKING:
    from aoa.config import Config


def verify_broker_ready(cfg: Config) -> None:
    """Raise BrokerError if the configured broker cannot serve account + SPY bars."""
    from aoa.cli import build_broker

    broker = build_broker(cfg)
    broker.get_account()
    broker.verify_stock_bars("SPY", limit=1)


def verify_llm_ready(cfg: Config) -> None:
    """Raise LLMError if the configured LLM cannot complete a structured ping."""
    from aoa.cli import build_llm

    build_llm(cfg).ping()


def verify_crypto_bars(cfg: Config) -> None:
    """Raise BrokerError if public crypto bars are unreachable."""
    fetcher = AlpacaBarsFetcher(bars_config_from_env(cfg))
    try:
        fetcher.verify_crypto("BTC/USD", limit=1)
    finally:
        fetcher.close()


def run_connectivity_checks(cfg: Config) -> list[str]:
    """Return a list of error messages (empty when all checks pass)."""
    errors: list[str] = []
    try:
        verify_crypto_bars(cfg)
    except BrokerError as exc:
        errors.append(f"Crypto bars check failed: {exc}")
    if not cfg.has_brokerage_creds:
        return errors
    try:
        verify_broker_ready(cfg)
    except BrokerError as exc:
        errors.append(f"Broker check failed: {exc}")
    try:
        verify_llm_ready(cfg)
    except LLMError as exc:
        errors.append(f"LLM check failed: {exc}")
    return errors
