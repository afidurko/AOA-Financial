"""Bar timeframe definitions for multi-timeframe market analysis.

Alpaca accepts values such as ``1Min``, ``3Min``, ``5Min``, ``15Min``, ``1Hour``,
``1Day``, and ``12Month``. There is no native ``1Year`` bar — ``12Month`` is the
annual aggregation and is exposed under the ``12Month`` key (yearly context).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeframeSpec:
    """One timeframe to fetch and surface to the agents."""

    key: str
    alpaca: str
    limit: int


# Default stack: 1m, 3m, 5m, 15m, 1h, daily, yearly (12-month bars).
DEFAULT_TIMEFRAMES: tuple[TimeframeSpec, ...] = (
    TimeframeSpec("1Min", "1Min", 390),
    TimeframeSpec("3Min", "3Min", 260),
    TimeframeSpec("5Min", "5Min", 156),
    TimeframeSpec("15Min", "15Min", 260),
    TimeframeSpec("1Hour", "1Hour", 168),
    TimeframeSpec("1Day", "1Day", 220),
    TimeframeSpec("12Month", "12Month", 10),
)

_REGISTRY: dict[str, TimeframeSpec] = {}
for spec in DEFAULT_TIMEFRAMES:
    _REGISTRY[spec.key] = spec
    _REGISTRY[spec.key.lower()] = spec
    _REGISTRY[spec.alpaca] = spec
    _REGISTRY[spec.alpaca.lower()] = spec
_REGISTRY["1D"] = _REGISTRY["1Day"]
_REGISTRY["1d"] = _REGISTRY["1Day"]
_REGISTRY["1H"] = _REGISTRY["1Hour"]
_REGISTRY["1h"] = _REGISTRY["1Hour"]
_REGISTRY["1Y"] = _REGISTRY["12Month"]
_REGISTRY["1y"] = _REGISTRY["12Month"]
_REGISTRY["1Year"] = _REGISTRY["12Month"]
_REGISTRY["1year"] = _REGISTRY["12Month"]


def parse_timeframes(raw: str) -> tuple[TimeframeSpec, ...]:
    """Parse a comma-separated list of timeframe keys (falls back to defaults)."""
    if not raw.strip():
        return DEFAULT_TIMEFRAMES
    specs: list[TimeframeSpec] = []
    seen: set[str] = set()
    for token in raw.split(","):
        key = token.strip()
        if not key:
            continue
        spec = _REGISTRY.get(key) or _REGISTRY.get(key.upper())
        if spec is None:
            raise ValueError(
                f"Unknown bar timeframe {key!r}. "
                f"Use comma-separated keys such as 1Min,3Min,5Min,15Min,1Hour,1Day,12Month."
            )
        if spec.key not in seen:
            specs.append(spec)
            seen.add(spec.key)
    return tuple(specs) if specs else DEFAULT_TIMEFRAMES
