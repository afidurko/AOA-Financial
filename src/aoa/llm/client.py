"""Thin wrapper over the Anthropic Messages API.

Every agent reasons through this client. It standardizes on:

- A configurable Claude model (default ``claude-sonnet-4-20250514``).
- Adaptive thinking and structured JSON output when the API supports them.
- Automatic fallback to a plain Messages call when advanced parameters fail.
- A ``structured`` helper that constrains output to a JSON schema so agents
  return machine-parseable signals rather than prose.
"""

from __future__ import annotations

import json
import re
from typing import Any

try:  # The SDK is a hard runtime dependency, but keep import errors friendly.
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]


class LLMError(RuntimeError):
    """Raised when the Claude API call fails or returns unusable output."""


_VALID_EFFORT = frozenset({"low", "medium", "high", "xhigh", "max"})


class LLMClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-sonnet-4-20250514",
        effort: str = "high",
        max_tokens: int = 8000,
    ) -> None:
        if anthropic is None:  # pragma: no cover
            raise LLMError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            )
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is required.")
        if effort not in _VALID_EFFORT:
            raise LLMError(
                f"Invalid effort {effort!r}; expected one of {sorted(_VALID_EFFORT)}."
            )
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def ping(self) -> None:
        """Verify API connectivity with a minimal structured call."""
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        result = self.structured(
            "You are a connectivity check.",
            "Return ok:true as JSON.",
            schema,
            max_tokens=256,
        )
        if result.get("ok") is not True:
            raise LLMError(f"Unexpected LLM ping response: {result!r}")

    def complete(self, system: str, prompt: str, *, max_tokens: int | None = None) -> str:
        """Return Claude's plain-text response."""
        tokens = max_tokens or self.max_tokens
        try:
            resp = self._create_advanced(
                system=system,
                prompt=prompt,
                max_tokens=tokens,
            )
        except LLMError:
            resp = self._create_basic(system=system, prompt=prompt, max_tokens=tokens)
        return _first_text(resp)

    def structured(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Return a dict validated against ``schema`` (JSON Schema)."""
        tokens = max_tokens or self.max_tokens
        try:
            resp = self._create_advanced(
                system=system,
                prompt=prompt,
                max_tokens=tokens,
                schema=schema,
            )
            text = _first_text(resp)
            return json.loads(text)
        except (LLMError, json.JSONDecodeError):
            return self._structured_prompt_fallback(system, prompt, schema, max_tokens=tokens)

    def _create_advanced(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        output_config: dict[str, Any] = {"effort": self.effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            return self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                output_config=output_config,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Claude request failed: {exc}") from exc

    def _create_basic(self, *, system: str, prompt: str, max_tokens: int) -> Any:
        try:
            return self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Claude request failed: {exc}") from exc

    def _structured_prompt_fallback(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        schema_hint = json.dumps(schema, separators=(",", ":"))
        augmented_system = (
            f"{system}\n\nRespond with a single JSON object matching this schema "
            f"(no markdown, no commentary):\n{schema_hint}"
        )
        text = self.complete(augmented_system, prompt, max_tokens=max_tokens)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"Claude returned non-JSON output: {text[:300]}") from None


def _first_text(resp: Any) -> str:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    raise LLMError("Claude response contained no text block.")
