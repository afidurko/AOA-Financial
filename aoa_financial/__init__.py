"""
AOA-Financial
=============

A deep stock-market analysis, forecasting and decision engine.

The package is organised into five layers, each independently usable:

    databases/  - SQLite-backed stores for prices, fundamentals, sentiment,
                  inferred regimes, agent signals and swarm decisions.
    ingest/     - Data acquisition: a deterministic synthetic generator that
                  produces realistic history back to June 1960, plus optional
                  live loaders (Stooq CSV) that degrade gracefully offline.
    analysis/   - The quant core: technical indicators, fundamental scoring,
                  forecasting models, market-regime inference, a multifactor
                  "reverse-engineering" model, and sentiment scoring.
    llm/        - A Claude Opus 4.8 powered deep-analysis "analyst" that turns
                  the computed quant evidence into narrative theses and
                  recommendations. Falls back to a deterministic offline
                  analyst when the Anthropic SDK / API key is unavailable.
    swarm/      - A multi-agent decision engine: independent specialist agents
                  each emit a signal; the swarm aggregates them into a sized,
                  rationalised BUY / HOLD / SELL decision.

Design principle: the *core runs on the standard library alone*. numpy,
pandas, the anthropic SDK and network access are optional accelerators that
are detected and used when present.
"""

__version__ = "0.1.0"

from .config import Config, EPOCH_START  # noqa: E402,F401

__all__ = ["Config", "EPOCH_START", "__version__"]
