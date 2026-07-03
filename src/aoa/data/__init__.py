"""Market-data assembly and technical indicators."""

from aoa.data.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
    technical_snapshot,
    volume_metrics,
)
from aoa.data.market_data import MarketDataService, SymbolSnapshot
from aoa.data.news import AlpacaNewsFeed, NewsFeed, NewsItem, NullNewsFeed
from aoa.data.timeframes import DEFAULT_TIMEFRAMES, TimeframeSpec, parse_timeframes

__all__ = [
    "sma",
    "ema",
    "rsi",
    "macd",
    "atr",
    "bollinger_bands",
    "technical_snapshot",
    "volume_metrics",
    "DEFAULT_TIMEFRAMES",
    "TimeframeSpec",
    "parse_timeframes",
    "MarketDataService",
    "AlpacaNewsFeed",
    "NewsFeed",
    "NewsItem",
    "NullNewsFeed",
    "SymbolSnapshot",
]
