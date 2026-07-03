"""Sentiment scoring.

Two entry points:

* :func:`score_text` - a transparent lexicon-based scorer for headlines / notes
  (no model download, works offline). Returns a [-1, 1] score.
* :func:`blended` - combines any stored market sentiment with price-momentum
  to produce a single robust sentiment reading for an asset.
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Sequence

# Compact finance-tuned sentiment lexicon. Deliberately small and auditable.
_POSITIVE = {
    "beat", "beats", "surge", "surges", "soar", "rally", "rallies", "growth",
    "profit", "record", "upgrade", "outperform", "bullish", "strong", "gain",
    "gains", "rebound", "expansion", "raise", "raised", "tops", "breakthrough",
    "accelerate", "momentum", "robust", "optimistic", "buyback", "dividend",
}
_NEGATIVE = {
    "miss", "misses", "plunge", "plunges", "slump", "selloff", "loss", "losses",
    "downgrade", "underperform", "bearish", "weak", "decline", "drop", "drops",
    "recession", "lawsuit", "probe", "cut", "cuts", "warning", "warns",
    "default", "bankruptcy", "fraud", "layoffs", "slowdown", "headwind", "risk",
}
_NEGATORS = {"not", "no", "never", "without", "fails", "failed", "won't", "cannot"}

_WORD = re.compile(r"[a-zA-Z']+")


def score_text(text: str) -> float:
    """Lexicon sentiment in [-1, 1] with simple negation handling."""
    tokens = [t.lower() for t in _WORD.findall(text)]
    if not tokens:
        return 0.0
    total = 0
    hits = 0
    for i, tok in enumerate(tokens):
        val = 0
        if tok in _POSITIVE:
            val = 1
        elif tok in _NEGATIVE:
            val = -1
        if val:
            # Flip polarity if a negator appears within the prior 3 tokens.
            window = tokens[max(0, i - 3):i]
            if any(w in _NEGATORS for w in window):
                val = -val
            total += val
            hits += 1
    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, total / math.sqrt(hits) / 2.0))


def score_headlines(headlines: Sequence[str]) -> float:
    if not headlines:
        return 0.0
    scores = [score_text(h) for h in headlines]
    return sum(scores) / len(scores)


def blended(stored_sentiment: Optional[float],
            recent_returns: Sequence[float]) -> float:
    """Combine a stored sentiment reading with realised momentum.

    Momentum acts as a market-revealed sentiment proxy. The two are averaged
    with momentum down-weighted so it informs but doesn't dominate.
    """
    mom = 0.0
    if recent_returns:
        cum = sum(recent_returns)
        mom = math.tanh(6.0 * cum)
    if stored_sentiment is None:
        return mom
    return max(-1.0, min(1.0, 0.6 * stored_sentiment + 0.4 * mom))
