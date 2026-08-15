"""LLM client for swarm reasoning.

Default backend is a local OpenAI-compatible server such as WASTE
(``python3 -m serve``). Claude/Anthropic is available only when
``AOA_LLM_PROVIDER=anthropic`` is set explicitly.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

try:  # Optional — only required for AOA_LLM_PROVIDER=anthropic.
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]


class LLMError(RuntimeError):
    """Raised when an LLM call fails or returns unusable output."""


_VALID_EFFORT = frozenset({"low", "medium", "high", "xhigh", "max"})
_VALID_PROVIDERS = frozenset({"anthropic", "openai_compatible"})
_DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
# WASTE accept low|high|max for reasoning_effort; map AOA medium/xhigh.
_WASTE_EFFORT = {
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "max",
    "max": "max",
}


class LLMClient:
    def __init__(
        self,
        api_key: str = "",
        *,
        provider: str = "openai_compatible",
        model: str = "kimi-linear",
        effort: str = "high",
        max_tokens: int = 8000,
        base_url: str | None = None,
    ) -> None:
        if provider not in _VALID_PROVIDERS:
            raise LLMError(
                f"Invalid LLM provider {provider!r}; expected one of "
                f"{sorted(_VALID_PROVIDERS)}."
            )
        if effort not in _VALID_EFFORT:
            raise LLMError(
                f"Invalid effort {effort!r}; expected one of {sorted(_VALID_EFFORT)}."
            )
        self.provider = provider
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._client: Any = None

        if provider == "anthropic":
            self.base_url = (base_url or "").rstrip("/")
            if anthropic is None:  # pragma: no cover
                raise LLMError(
                    "The 'anthropic' package is not installed. "
                    "Run: pip install 'aoa-financial[anthropic]' "
                    "or set AOA_LLM_PROVIDER=openai_compatible for local WASTE."
                )
            if not api_key:
                raise LLMError("ANTHROPIC_API_KEY is required when using Anthropic.")
            self._client = anthropic.Anthropic(api_key=api_key)
        else:
            if base_url is None:
                self.base_url = _DEFAULT_BASE_URL
            else:
                self.base_url = base_url.strip().rstrip("/")
            if not self.base_url:
                raise LLMError(
                    "AOA_LLM_BASE_URL is required for openai_compatible "
                    "(e.g. http://127.0.0.1:8000/v1)."
                )
            if not self._api_key:
                self._api_key = "local"

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
        """Return the model's plain-text response."""
        tokens = max_tokens or self.max_tokens
        if self.provider == "openai_compatible":
            return self._openai_complete(system, prompt, max_tokens=tokens)
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
        if self.provider == "openai_compatible":
            try:
                text = self._openai_complete(
                    system,
                    prompt,
                    max_tokens=tokens,
                    schema=schema,
                )
                return json.loads(text)
            except (LLMError, json.JSONDecodeError):
                return self._structured_prompt_fallback(
                    system, prompt, schema, max_tokens=tokens
                )
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
            raise LLMError(f"Anthropic request failed: {exc}") from exc

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
            raise LLMError(f"Anthropic request failed: {exc}") from exc

    def _openai_complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """POST /chat/completions against an OpenAI-compatible server (WASTE)."""
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        # WASTE documents reasoning_effort (thinking_effort is an alias).
        # kimi-linear / chat.json may reject effort — retry without it on 400.
        body["reasoning_effort"] = _WASTE_EFFORT.get(self.effort, "high")
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "aoa_structured",
                    "schema": schema,
                    "strict": True,
                },
            }
        try:
            return self._openai_post(body)
        except LLMError as exc:
            detail = str(exc).lower()
            if "400" in detail and (
                "effort" in detail or "reasoning" in detail or "response_format" in detail
            ):
                body.pop("reasoning_effort", None)
                if "response_format" in detail:
                    body.pop("response_format", None)
                return self._openai_post(body)
            raise

    def _openai_post(self, body: dict[str, Any]) -> str:
        url = f"{self.base_url}/chat/completions"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise LLMError(
                f"OpenAI-compatible request failed ({exc.code}): {detail}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"OpenAI-compatible request failed: {exc}") from exc
        return _openai_first_text(payload)

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
            raise LLMError(f"LLM returned non-JSON output: {text[:300]}") from None


def _first_text(resp: Any) -> str:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    raise LLMError("Anthropic response contained no text block.")


def _openai_first_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise LLMError(f"OpenAI-compatible response had no choices: {payload!r}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {None, "text"}
        ]
        text = "".join(parts).strip()
        if text:
            return text
    raise LLMError(f"OpenAI-compatible response contained no text: {payload!r}")


def llm_from_config(cfg: Any) -> LLMClient:
    """Build an :class:`LLMClient` from an AOA ``Config``-like object.

    Shared by the CLI, workloop, and smoke scripts so provider/base_url
    selection cannot drift.
    """
    provider = getattr(cfg, "llm_provider", "openai_compatible")
    model = getattr(cfg, "model", "kimi-linear")
    effort = getattr(cfg, "effort", "high")
    if provider == "openai_compatible":
        return LLMClient(
            getattr(cfg, "llm_api_key", "")
            or getattr(cfg, "anthropic_api_key", "")
            or "local",
            provider="openai_compatible",
            model=model,
            effort=effort,
            base_url=getattr(cfg, "llm_base_url", None) or _DEFAULT_BASE_URL,
        )
    if provider == "anthropic":
        return LLMClient(
            getattr(cfg, "anthropic_api_key", ""),
            provider="anthropic",
            model=model,
            effort=effort,
        )
    raise LLMError(
        f"Unsupported AOA_LLM_PROVIDER {provider!r}; expected one of "
        f"{sorted(_VALID_PROVIDERS)}."
    )
