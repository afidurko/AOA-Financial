"""The crypto asset registry and the training calendar epoch.

``TRAINING_EPOCH`` (2007-07-17) predates every crypto asset — Bitcoin's genesis
block is 2009-01-03 and its first exchange-quoted market (Mt. Gox) opened
2010-07-17. The day-by-day trainer still walks the full calendar from the
epoch so the learner internalizes each asset's *entire* lifetime, including
how long the market simply did not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CryptoAsset:
    code: str  # "BTC"
    name: str
    genesis: date | None  # chain/genesis event (None if pre-chain)
    first_market: date  # earliest date daily market data can exist
    yahoo_symbol: str  # Yahoo Finance chart symbol
    bitstamp_pair: str | None  # Bitstamp OHLC pair (None if unlisted)
    notes: str = ""


TRAINING_EPOCH = date(2007, 7, 17)

ASSETS: dict[str, CryptoAsset] = {
    "BTC": CryptoAsset(
        code="BTC",
        name="Bitcoin",
        genesis=date(2009, 1, 3),
        first_market=date(2010, 7, 17),
        yahoo_symbol="BTC-USD",
        bitstamp_pair="btcusd",
        notes="Mt. Gox opened 2010-07-17; Bitstamp daily data from 2011-08.",
    ),
    "ETH": CryptoAsset(
        code="ETH",
        name="Ethereum",
        genesis=date(2015, 7, 30),
        first_market=date(2015, 8, 7),
        yahoo_symbol="ETH-USD",
        bitstamp_pair="ethusd",
        notes="Frontier launch 2015-07-30; first exchange listings 2015-08.",
    ),
    "SOL": CryptoAsset(
        code="SOL",
        name="Solana",
        genesis=date(2020, 3, 16),
        first_market=date(2020, 4, 10),
        yahoo_symbol="SOL-USD",
        bitstamp_pair=None,
        notes="Mainnet beta 2020-03; first market data 2020-04.",
    ),
    "XRP": CryptoAsset(
        code="XRP",
        name="XRP",
        genesis=date(2012, 6, 2),
        first_market=date(2013, 8, 4),
        yahoo_symbol="XRP-USD",
        bitstamp_pair="xrpusd",
        notes="Ledger launched 2012; consistent daily market data from 2013-08.",
    ),
}

DEFAULT_ASSETS = ("BTC", "ETH", "SOL", "XRP")


def get_asset(code: str) -> CryptoAsset:
    try:
        return ASSETS[code.upper()]
    except KeyError as exc:
        known = ", ".join(sorted(ASSETS))
        raise KeyError(f"Unknown crypto asset {code!r}. Known: {known}.") from exc
