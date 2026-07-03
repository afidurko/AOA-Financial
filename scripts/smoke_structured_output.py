#!/usr/bin/env python3
"""Smoke-test structured JSON output from Claude for agent schemas.

Exercises representative agent JSON schemas against the live LLM API to confirm
structured output (or prompt fallback) returns parseable, schema-shaped payloads.

Usage:
  python scripts/smoke_structured_output.py
  python scripts/smoke_structured_output.py --only ping,technical,portfolio
  ANTHROPIC_API_KEY=sk-... python scripts/smoke_structured_output.py

Exits 0 when all selected cases pass; 1 on any failure. Skips gracefully when
ANTHROPIC_API_KEY is unset (exit 0) unless --require-key is passed.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, Callable

from aoa.agents import fund_manager as fund_manager_mod
from aoa.agents import fundamental as fundamental_mod
from aoa.agents import meshing as meshing_mod
from aoa.agents import news_analyst as news_mod
from aoa.agents import options as options_mod
from aoa.agents import portfolio as portfolio_mod
from aoa.agents import research as research_mod
from aoa.agents import risk as risk_mod
from aoa.agents import risk_debate as risk_debate_mod
from aoa.agents import scanner as scanner_mod
from aoa.agents import sentiment as sentiment_mod
from aoa.agents import technical as technical_mod
from aoa.config import Config
from aoa.llm.client import LLMClient, LLMError


@dataclass(frozen=True)
class SmokeCase:
    name: str
    system: str
    prompt: str
    schema: dict[str, Any]
    validate: Callable[[dict[str, Any]], None]


def _require_keys(*keys: str) -> Callable[[dict[str, Any]], None]:
    def _check(result: dict[str, Any]) -> None:
        missing = [k for k in keys if k not in result]
        if missing:
            raise ValueError(f"missing keys: {missing}")

    return _check


def _cases() -> list[SmokeCase]:
    return [
        SmokeCase(
            name="scanner",
            system=scanner_mod.ScannerAgent.system_prompt,
            prompt=(
                "Universe snapshot for AAPL: price ~100, RSI 58, MACD positive, "
                "volume elevated. Return up to 2 candidates as JSON."
            ),
            schema=scanner_mod._SCHEMA,
            validate=_require_keys("candidates"),
        ),
        SmokeCase(
            name="technical",
            system=technical_mod.TechnicalAgent.system_prompt,
            prompt=(
                "Symbol AAPL: daily RSI 62, above 50DMA, ATR 2.1. "
                "Return technical read as JSON."
            ),
            schema=technical_mod._SCHEMA,
            validate=_require_keys("direction", "conviction", "rationale"),
        ),
        SmokeCase(
            name="fundamental",
            system=fundamental_mod.FundamentalAgent.system_prompt,
            prompt=(
                "Symbol AAPL: large-cap quality name, low event risk this week. "
                "Return fundamental assessment as JSON."
            ),
            schema=fundamental_mod._SCHEMA,
            validate=_require_keys("direction", "conviction", "event_risk"),
        ),
        SmokeCase(
            name="news",
            system=news_mod.NewsAnalystAgent.system_prompt,
            prompt=(
                "Symbol AAPL: no verified headlines provided. "
                "Return qualitative news/macro read as JSON."
            ),
            schema=news_mod._SCHEMA,
            validate=_require_keys("direction", "summary", "key_events"),
        ),
        SmokeCase(
            name="sentiment",
            system=sentiment_mod.SentimentAnalystAgent.system_prompt,
            prompt=(
                "Symbol AAPL: mildly positive headline tone, steady volume. "
                "Return sentiment analysis as JSON."
            ),
            schema=sentiment_mod._SCHEMA,
            validate=_require_keys("direction", "sentiment_score", "summary"),
        ),
        SmokeCase(
            name="meshing",
            system=meshing_mod.MeshingAgent.system_prompt,
            prompt=(
                "Symbol AAPL. Technical bullish 0.7, fundamental bullish 0.6. "
                "Return unified meshed view as JSON."
            ),
            schema=meshing_mod._SCHEMA,
            validate=_require_keys("direction", "conviction", "corroboration"),
        ),
        SmokeCase(
            name="research_bull",
            system=research_mod.ResearchTeamAgent.system_prompt + " You are the BULLISH researcher.",
            prompt="Symbol AAPL with constructive analyst reports. Return bullish case as JSON.",
            schema=research_mod._BULL_SCHEMA,
            validate=_require_keys("argument", "conviction"),
        ),
        SmokeCase(
            name="research_facilitator",
            system=research_mod.ResearchTeamAgent.system_prompt + " You are the debate FACILITATOR.",
            prompt=(
                "Symbol AAPL. Bull: growth intact. Bear: valuation stretched. "
                "Select prevailing view as JSON."
            ),
            schema=research_mod._FACILITATOR_SCHEMA,
            validate=_require_keys("prevailing_view", "conviction", "rationale"),
        ),
        SmokeCase(
            name="portfolio",
            system=portfolio_mod.PortfolioManagerAgent.system_prompt,
            prompt=(
                "Account equity 100000, settled cash 100000. One bullish AAPL meshed view. "
                "Propose at most one trade as JSON."
            ),
            schema=portfolio_mod._SCHEMA,
            validate=_require_keys("proposals", "portfolio_commentary"),
        ),
        SmokeCase(
            name="risk",
            system=risk_mod.RiskManagerAgent.system_prompt,
            prompt=(
                "Account equity 100000. One approved AAPL buy proposal. "
                "Return vetoes as JSON."
            ),
            schema=risk_mod._SCHEMA,
            validate=_require_keys("vetoes", "assessment"),
        ),
        SmokeCase(
            name="risk_debate",
            system=risk_debate_mod.RiskDebateTeamAgent.system_prompt,
            prompt=(
                "Account equity 100000. One approved AAPL buy proposal. "
                "Return risk debate as JSON."
            ),
            schema=risk_debate_mod._SCHEMA,
            validate=_require_keys("perspectives", "facilitator_summary", "vetoes"),
        ),
        SmokeCase(
            name="fund_manager",
            system=fund_manager_mod.FundManagerAgent.system_prompt,
            prompt=(
                "Account equity 100000. One prudent AAPL buy proposal after risk review. "
                "Return fund manager decision as JSON."
            ),
            schema=fund_manager_mod._SCHEMA,
            validate=_require_keys("approved", "vetoes", "commentary"),
        ),
        SmokeCase(
            name="options",
            system=options_mod.OptionsStrategistAgent.system_prompt,
            prompt=(
                "Underlying AAPL at 100, bullish conviction 0.7. "
                "Contract AAPL250117C00100000 available. Return options idea as JSON."
            ),
            schema=options_mod._SCHEMA,
            validate=_require_keys("strategy", "rationale", "conviction"),
        ),
    ]


def run_smoke(
    llm: LLMClient,
    cases: list[SmokeCase],
    *,
    max_tokens: int = 512,
) -> list[str]:
    failures: list[str] = []
    for case in cases:
        try:
            result = llm.structured(
                case.system,
                case.prompt,
                case.schema,
                max_tokens=max_tokens,
            )
            if not isinstance(result, dict):
                raise TypeError(f"expected dict, got {type(result).__name__}")
            case.validate(result)
            print(f"PASS  {case.name}")
        except (LLMError, ValueError, TypeError) as exc:
            print(f"FAIL  {case.name}: {exc}")
            failures.append(case.name)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        help="Comma-separated smoke case names to run (default: all).",
    )
    parser.add_argument(
        "--require-key",
        action="store_true",
        help="Exit 1 when ANTHROPIC_API_KEY is unset (default: skip with exit 0).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="Max tokens per structured call (default: 512).",
    )
    args = parser.parse_args(argv)

    cfg = Config.from_env()
    if not cfg.anthropic_api_key:
        msg = "ANTHROPIC_API_KEY not set — skipping structured output smoke test."
        print(msg)
        return 1 if args.require_key else 0

    cases = _cases()
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        cases = [c for c in cases if c.name in wanted]
        unknown = wanted - {c.name for c in cases}
        if unknown:
            print(f"Unknown case names: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1

    llm = LLMClient(
        cfg.anthropic_api_key,
        model=cfg.model,
        effort=cfg.effort,
    )

    print(f"Model: {cfg.model} | effort: {cfg.effort}")
    try:
        llm.ping()
        print("PASS  ping")
    except LLMError as exc:
        print(f"FAIL  ping: {exc}")
        return 1

    failures = run_smoke(llm, cases, max_tokens=args.max_tokens)
    if failures:
        print(f"\n{len(failures)} case(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1

    print(f"\nAll {len(cases) + 1} structured output smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
