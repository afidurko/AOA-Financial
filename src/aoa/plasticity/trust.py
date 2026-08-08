"""Deterministic sizing adjustments from plastic symbol trust."""


def notional_trust_multiplier(trust: float) -> float:
    """Map symbol trust in [-1, 1] to a notional scale in [0.5, 1.25].

    Neutral trust (0) leaves size unchanged. Positive trust nudges size up;
    negative trust scales down — exploiting journal learnings without an LLM gate.
    """
    clamped = max(-1.0, min(1.0, trust))
    if clamped < 0:
        return max(0.5, 1.0 + 0.5 * clamped)
    return min(1.25, 1.0 + 0.25 * clamped)
