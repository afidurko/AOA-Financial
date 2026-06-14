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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:  # The SDK is a hard runtime dependency, but keep import errors friendly.
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]


class LLMError(RuntimeError):
    """Raised when the Claude API call fails or returns unusable output."""


@dataclass
class ToolRunResult:
    """The outcome of an agentic tool-use loop."""

    text: str
    messages: list[dict]  # the full transcript, for follow-up turns
    tool_calls: list[dict] = field(default_factory=list)  # {name, input} in call order
    stopped_at_limit: bool = False


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


    def run_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        tool_runner: Callable[[str, dict], dict],
        *,
        max_iterations: int = 8,
        max_tokens: int | None = None,
    ) -> ToolRunResult:
        """Run an agentic loop: let Claude call tools until it answers in prose.

        ``tool_runner(name, input)`` executes one tool and returns a JSON-able
        dict. The loop preserves the full message transcript (including thinking
        and tool blocks) so the conversation can be continued.
        """
        convo: list[dict] = list(messages)
        tool_calls: list[dict] = []
        last_text = ""

        for _ in range(max_iterations):
            try:
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    system=system,
                    thinking={"type": "adaptive"},
                    output_config={"effort": self.effort},
                    tools=tools,
                    messages=convo,
                )
            except Exception as exc:  # noqa: BLE001
                raise LLMError(f"Claude tool request failed: {exc}") from exc

            text_parts: list[str] = []
            tool_uses: list[Any] = []
            for block in getattr(resp, "content", []) or []:
                btype = getattr(block, "type", None)
                if btype == "text":
                    text_parts.append(block.text)
                elif btype == "tool_use":
                    tool_uses.append(block)
            if text_parts:
                last_text = "\n".join(text_parts).strip()

            # Preserve the assistant turn verbatim (thinking + tool_use blocks).
            convo.append({"role": "assistant", "content": resp.content})

            if getattr(resp, "stop_reason", None) != "tool_use" or not tool_uses:
                return ToolRunResult(text=last_text, messages=convo, tool_calls=tool_calls)

            results = []
            for tu in tool_uses:
                tool_calls.append({"name": tu.name, "input": tu.input})
                output = tool_runner(tu.name, tu.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(output, default=str),
                })
            convo.append({"role": "user", "content": results})

        return ToolRunResult(
            text=last_text or "(stopped: reached the tool-iteration limit)",
            messages=convo,
            tool_calls=tool_calls,
            stopped_at_limit=True,
        )


def _first_text(resp: Any) -> str:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    raise LLMError("Claude response contained no text block.")
