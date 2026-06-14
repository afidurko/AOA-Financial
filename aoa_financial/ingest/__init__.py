"""Data acquisition layer.

Two interchangeable sources implement the same contract (return a list of
``Bar`` plus reference/fundamental/sentiment context):

* :mod:`synthetic` - deterministic, offline, full history back to June 1960.
* :mod:`loaders`   - optional live feeds (Stooq CSV) with automatic fallback
                     to the synthetic generator when the network is down.
"""
from .synthetic import SyntheticGenerator
from .loaders import ingest_ticker, ingest_universe

__all__ = ["SyntheticGenerator", "ingest_ticker", "ingest_universe"]
