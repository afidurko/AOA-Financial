"""The quantitative core.

All modules operate on plain ``List[float]`` / ``List[Bar]`` and return plain
dataclasses or dicts, so they compose freely and need no heavy dependencies.
"""
from . import series, technical, fundamentals, forecast, regimes, factors, sentiment
from .reverse_engineer import reverse_engineer, ReverseEngineerResult

__all__ = [
    "series", "technical", "fundamentals", "forecast", "regimes",
    "factors", "sentiment", "reverse_engineer", "ReverseEngineerResult",
]
