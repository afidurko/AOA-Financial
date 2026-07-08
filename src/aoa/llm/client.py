"""Thin wrapper over a chat LLM used by every agent.

Three providers are supported behind one interface (``complete`` / ``structured``
/ ``ping``):

- ``anthropic`` (default) — the Anthropic Messages API with adaptive thinking and
  JSON-schema structured output, falling back to a plain Messages call.
- ``openai`` — any OpenAI-compatible Chat Completions endpoint.
- ``ollama`` — a local Ollama server via its OpenAI-compatible ``/v1`` endpoint
  (no API key required, no per-token cost).

``openai`` and ``ollama`` share one code path (the OpenAI SDK); ``ollama`` just
defaults the base URL and a placeholder key.
"""

from __future__ import annotations

import json
import re
from typing import Any

try:  # Anthropic SDK — default provider.
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

try:  # OpenAI SDK — used for the ``openai`` and ``ollama`` providers.
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns unusable output."""


_VALID_EFFORT = frozenset({"low", "medium", "high", "xhigh", "max"})
VALID_PROVIDERS = frozenset({"anthropic", "openai", "ollama"})
_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class LLMClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-sonnet-4-6",
        effort: str = "high",
        max_tokens: int = 8000,
        provider: str = "anthropic",
        base_url: str | None = None,
    ) -> None:
        if provider not in VALID_PROVIDERS:
            raise LLMError(
                f"Invalid provider {provider!r}; expected one of {sorted(VALID_PROVIDERS)}."
            )
        if effort not in _VALID_EFFORT:
            raise LLMError(
                f"Invalid effort {effort!r}; expected one of {sorted(_VALID_EFFORT)}."
            )
        self.provider = provider
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        if provider == "anthropic":
            if anthropic is None:  # pragma: no cover
                raise LLMError(
                    "The 'anthropic' package is not installed. Run: pip install anthropic"
                )
            if not api_key:
                raise LLMError("ANTHROPIC_API_KEY is required.")
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.Anthropic(**kwargs)
        else:
            if OpenAI is None:  # pragma: no cover
                raise LLMError(
                    "The 'openai' package is not installed. Run: pip install openai"
                )
            if provider == "ollama":
                base_url = base_url or _OLLAMA_DEFAULT_BASE_URL
                api_key = api_key or "ollama"
            if not api_key:
                raise LLMError("OPENAI_API_KEY is required.")
            self._client = OpenAI(api_key=api_key, base_url=base_url or None)

    def ping(self) -> None:
        """Verify connectivity with a minimal structured call."""
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
        """Return the model's plain-text response."""
        tokens = max_tokens or self.max_tokens
        if self.provider == "anthropic":
            try:
                resp = self._create_advanced(system=system, prompt=prompt, max_tokens=tokens)
            except LLMError:
                resp = self._create_basic(system=system, prompt=prompt, max_tokens=tokens)
            return _first_text(resp)
        return self._openai_complete(system, prompt, tokens)

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
        if self.provider == "anthropic":
            try:
                resp = self._create_advanced(
                    system=system, prompt=prompt, max_tokens=tokens, schema=schema
                )
                return json.loads(_first_text(resp))
            except (LLMError, json.JSONDecodeError):
                return self._structured_prompt_fallback(system, prompt, schema, max_tokens=tokens)
        return self._openai_structured(system, prompt, schema, tokens)

    # ------------------------------------------------------------- anthropic
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
            raise LLMError(f"LLM request failed: {exc}") from exc

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
            raise LLMError(f"LLM request failed: {exc}") from exc

    def _structured_prompt_fallback(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        augmented_system = _schema_system(system, schema)
        return _parse_json(self.complete(augmented_system, prompt, max_tokens=max_tokens))

    # ----------------------------------------------------- openai / ollama
    def _openai_complete(self, system: str, prompt: str, max_tokens: int) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM request failed: {exc}") from exc
        text = resp.choices[0].message.content if resp.choices else None
        if not text:
            raise LLMError("LLM response contained no text.")
        return text

    def _openai_structured(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int
    ) -> dict[str, Any]:
        augmented_system = _schema_system(system, schema)
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": augmented_system},
                    {"role": "user", "content": prompt},
                ],
            )
            text = resp.choices[0].message.content if resp.choices else None
            return _parse_json(text or "")
        except LLMError:
            raise
        except Exception:  # noqa: BLE001 — retry without JSON mode (older/local models).
            return _parse_json(self._openai_complete(augmented_system, prompt, max_tokens))


def _schema_system(system: str, schema: dict[str, Any]) -> str:
    schema_hint = json.dumps(schema, separators=(",", ":"))
    return (
        f"{system}\n\nRespond with a single JSON object matching this schema "
        f"(no markdown, no commentary):\n{schema_hint}"
    )


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError(f"LLM returned non-JSON output: {text[:300]}") from None


def _first_text(resp: Any) -> str:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    raise LLMError("LLM response contained no text block.")
