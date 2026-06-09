"""Thin wrapper over the Anthropic Messages API.

Every agent reasons through this client. It standardizes on:

- ``claude-opus-4-8`` (configurable), the most capable model — appropriate for
  the judgment-heavy task of trade analysis.
- Adaptive thinking, which lets Claude decide how much to reason per request.
- The ``effort`` parameter for the thoroughness/cost tradeoff.
- A ``structured`` helper that constrains output to a JSON schema so agents
  return machine-parseable signals rather than prose.
"""

from __future__ import annotations

import json
from typing import Any

try:  # The SDK is a hard runtime dependency, but keep import errors friendly.
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]


class LLMError(RuntimeError):
    """Raised when the Claude API call fails or returns unusable output."""


class LLMClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-opus-4-8",
        effort: str = "high",
        max_tokens: int = 8000,
    ) -> None:
        if anthropic is None:  # pragma: no cover
            raise LLMError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            )
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is required.")
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, prompt: str, *, max_tokens: int | None = None) -> str:
        """Return Claude's plain-text response."""
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 — surface any SDK/API error uniformly
            raise LLMError(f"Claude request failed: {exc}") from exc
        return _first_text(resp)

    def structured(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Return a dict validated against ``schema`` (JSON Schema).

        Uses the Messages API ``output_config.format`` so the model is
        constrained to emit conforming JSON.
        """
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Claude structured request failed: {exc}") from exc
        text = _first_text(resp)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Claude returned non-JSON output: {text[:300]}") from exc


def _first_text(resp: Any) -> str:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    raise LLMError("Claude response contained no text block.")
