"""Runtime execution of approved sub-teams under their leads."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aoa.agents.base import clamp_conviction
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import (
    AlgorithmReport,
    ApprovedSubTeam,
    DecisionBrief,
    MarketContextReport,
    SubTeamMember,
    TrendDirection,
    TrendReport,
)
from aoa.team.morgan import (
    _highlights_from_scan,
    _options_note_from_scan,
    _scan_options_volume,
    _volume_baseline,
)
from aoa.team.tom import _clamp as _clamp_strength

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore
    from aoa.journal.store import Journal
    from aoa.llm.client import LLMClient
    from aoa.team.alan import AlanAgent
    from aoa.team.code_engineering import CodeQualityReport
    from aoa.team.julie import JulieAgent
    from aoa.team.morgan import MorganAgent
    from aoa.team.tom import TomAgent

_MEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {"type": "string"}},
        "assessment": {"type": "string"},
        "confidence": {"type": "number"},
        "recommendation": {"type": "string"},
    },
    "required": ["findings", "assessment"],
    "additionalProperties": False,
}

_TOM_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["up", "down", "sideways", "unclear"]},
        "strength": {"type": "number"},
        "timeframe": {"type": "string", "enum": ["intraday", "swing", "position"]},
        "rationale": {"type": "string"},
        "key_observations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["direction", "strength", "timeframe", "rationale", "key_observations"],
    "additionalProperties": False,
}

_JULIE_SCHEMA = {
    "type": "object",
    "properties": {
        "validated": {"type": "boolean"},
        "adjusted_strength": {"type": "number"},
        "method_notes": {"type": "string"},
        "signals": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["validated", "adjusted_strength", "method_notes", "signals"],
    "additionalProperties": False,
}

_MORGAN_SCHEMA = {
    "type": "object",
    "properties": {
        "volume_regime": {"type": "string", "enum": ["elevated", "normal", "thin"]},
        "volume_ratio": {"type": "number"},
        "liquidity_note": {"type": "string"},
        "options_volume_note": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": [
        "volume_regime",
        "volume_ratio",
        "liquidity_note",
        "options_volume_note",
        "summary",
    ],
    "additionalProperties": False,
}

_ALAN_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["watch", "consider_long", "consider_short_exit", "avoid"],
                    },
                    "conviction": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["symbol", "action", "conviction", "rationale"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["recommendations", "summary", "confidence"],
    "additionalProperties": False,
}


def load_approved_subteams(store: AnalyticsStore) -> dict[str, ApprovedSubTeam]:
    """Map lead name → latest approved sub-team roster."""
    rows = store.list_team_expansions(status="approved", limit=100)
    best: dict[str, tuple[str, ApprovedSubTeam]] = {}
    for row in rows:
        lead = str(row.get("lead_name", ""))
        if not lead:
            continue
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        members = [
            SubTeamMember(
                name=str(m.get("name", "")),
                role=str(m.get("role", "")),
                responsibilities=[str(x) for x in (m.get("responsibilities") or [])],
            )
            for m in payload.get("members") or []
            if m.get("name")
        ]
        if not members:
            continue
        stamp = str(row.get("resolved_at") or row.get("updated_at") or row.get("created_at") or "")
        team = ApprovedSubTeam(
            lead_name=lead,
            team_name=str(row.get("team_name", payload.get("team_name", f"{lead} Desk"))),
            mission=str(row.get("mission", payload.get("mission", ""))),
            members=members,
            resolved_at=stamp,
        )
        prev = best.get(lead)
        if prev is None or stamp > prev[0]:
            best[lead] = (stamp, team)
    return {lead: team for lead, (_, team) in best.items()}


@dataclass(frozen=True)
class SubTeamRunner:
    llm: LLMClient
    journal: Journal | None = None
    parallel: bool = True
    max_workers: int = 4

    def run_members(
        self,
        team: ApprovedSubTeam,
        task_context: str,
        *,
        lead_slug: str,
    ) -> list[dict[str, Any]]:
        if not team.members:
            return []
        if self.journal:
            self.journal.record(
                f"team.{lead_slug}.subteam.start",
                {
                    "lead": team.lead_name,
                    "team": team.team_name,
                    "members": [m.name for m in team.members],
                },
            )

        def _one(member: SubTeamMember) -> dict[str, Any]:
            system = (
                f"You are {member.name}, {member.role} on {team.lead_name}'s "
                f"sub-team ({team.team_name}). Mission: {team.mission}. "
                f"Responsibilities: {', '.join(member.responsibilities)}. "
                "Analyze the task context from your specialty angle. "
                "Return concise JSON for your lead to synthesize."
            )
            prompt = f"Task context:\n{task_context}\n\nReturn your analysis as JSON."
            try:
                result = self.llm.structured(system, prompt, _MEMBER_SCHEMA)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "findings": [f"{member.name} unavailable: {exc}"],
                    "assessment": "Sub-agent failed; lead should rely on direct analysis.",
                    "confidence": 0.0,
                }
            row = {
                "name": member.name,
                "role": member.role,
                **result,
            }
            if self.journal:
                self.journal.record(f"team.{lead_slug}.sub", row)
            return row

        if not self.parallel or len(team.members) <= 1 or self.max_workers <= 1:
            return [_one(m) for m in team.members]

        outputs: list[dict[str, Any]] = []
        workers = min(self.max_workers, len(team.members))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_one, m): m for m in team.members}
            for fut in as_completed(futures):
                outputs.append(fut.result())
        outputs.sort(key=lambda row: row.get("name", ""))
        return outputs

    def synthesize(
        self,
        *,
        lead_system: str,
        task_context: str,
        member_outputs: list[dict[str, Any]],
        schema: dict[str, Any],
        instruction: str,
        lead_slug: str,
    ) -> dict[str, Any]:
        prompt = (
            f"{task_context}\n\n"
            f"Sub-team member reports:\n{json.dumps(member_outputs, default=str)}\n\n"
            f"{instruction}\nReturn JSON."
        )
        result = self.llm.structured(lead_system, prompt, schema)
        if self.journal:
            self.journal.record(
                f"team.{lead_slug}.subteam.synthesis",
                {"member_count": len(member_outputs), "synthesized": True},
            )
        return result


def run_tom_with_subteam(
    tom: TomAgent,
    team: ApprovedSubTeam,
    snapshots: dict[str, SymbolSnapshot],
    runner: SubTeamRunner,
) -> list[TrendReport]:
    reports: list[TrendReport] = []
    for snap in snapshots.values():
        if snap.error or not snap.technicals:
            reports.append(tom.analyze_symbol(snap))
            continue
        task = (
            f"Symbol: {snap.symbol}\n"
            f"Quote: {json.dumps(snap.to_context().get('quote'))}\n"
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n"
        )
        members = runner.run_members(team, task, lead_slug="tom")
        try:
            r = runner.synthesize(
                lead_system=tom.system_prompt,
                task_context=task,
                member_outputs=members,
                schema=_TOM_SCHEMA,
                instruction=(
                    "You are Tom synthesizing your sub-team's trend analyses. "
                    "Merge member findings into one trend characterization."
                ),
                lead_slug="tom",
            )
            reports.append(
                TrendReport(
                    symbol=snap.symbol,
                    direction=TrendDirection(r["direction"]),
                    strength=_clamp_strength(r["strength"]),
                    timeframe=r.get("timeframe", "swing"),
                    rationale=r["rationale"],
                    key_observations=list(r.get("key_observations") or []),
                )
            )
        except Exception:  # noqa: BLE001
            reports.append(tom.analyze_symbol(snap))
    return reports


def run_julie_with_subteam(
    julie: JulieAgent,
    team: ApprovedSubTeam,
    trend: TrendReport,
    snap: SymbolSnapshot,
    runner: SubTeamRunner,
    *,
    code_quality: CodeQualityReport | None = None,
) -> AlgorithmReport:
    if snap.error or not snap.technicals:
        return julie.refine(trend, snap, code_quality=code_quality)
    task = (
        f"Tom's trend report:\n{json.dumps(trend.to_context())}\n\n"
        f"Symbol: {snap.symbol}\n"
        f"Technicals: {json.dumps(snap.technicals, default=str)}\n"
    )
    if code_quality is not None:
        task += f"\nCode-quality audit:\n{json.dumps(code_quality.to_context(), default=str)}\n"
    members = runner.run_members(team, task, lead_slug="julie")
    try:
        r = runner.synthesize(
            lead_system=julie.system_prompt,
            task_context=task,
            member_outputs=members,
            schema=_JULIE_SCHEMA,
            instruction=(
                "You are Julie synthesizing your sub-team's validation work. "
                "Produce one algorithm report per symbol."
            ),
            lead_slug="julie",
        )
        notes = r.get("method_notes", "")
        if code_quality and code_quality.worst_status.value != "ok":
            notes = f"{notes} Code note: {code_quality.summary}".strip()
        return AlgorithmReport(
            symbol=trend.symbol,
            validated=bool(r.get("validated")),
            adjusted_strength=clamp_conviction(r.get("adjusted_strength", 0)),
            method_notes=notes,
            signals=list(r.get("signals") or []),
        )
    except Exception:  # noqa: BLE001
        return julie.refine(trend, snap, code_quality=code_quality)


def run_morgan_with_subteam(
    morgan: MorganAgent,
    team: ApprovedSubTeam,
    snap: SymbolSnapshot,
    runner: SubTeamRunner,
) -> MarketContextReport:
    baseline = _volume_baseline(snap)
    options_scan = _scan_options_volume(morgan.broker, snap)
    if snap.error or not snap.has_technicals:
        return MarketContextReport(
            symbol=snap.symbol,
            volume_regime="thin",
            volume_ratio=baseline.get("volume_ratio"),
            liquidity_note="Insufficient market data.",
            summary=f"{snap.symbol}: data unavailable.",
            options_volume_note=options_scan.get("note", "Options data unavailable."),
            options_highlights=_highlights_from_scan(options_scan),
            options_by_expiration=dict(options_scan.get("by_expiration") or {}),
        )
    task = (
        f"Symbol snapshot:\n{json.dumps(snap.to_context(), default=str)}\n"
        f"Equity volume hints:\n{json.dumps(baseline, default=str)}\n"
        f"Options volume hints:\n{json.dumps(options_scan, default=str)}\n"
    )
    members = runner.run_members(team, task, lead_slug="morgan")
    try:
        r = runner.synthesize(
            lead_system=morgan.system_prompt,
            task_context=task,
            member_outputs=members,
            schema=_MORGAN_SCHEMA,
            instruction=(
                "You are Morgan synthesizing your sub-team's market and options "
                "flow analysis."
            ),
            lead_slug="morgan",
        )
        ratio = r.get("volume_ratio")
        if ratio is None:
            ratio = baseline.get("volume_ratio")
        return MarketContextReport(
            symbol=snap.symbol,
            volume_regime=str(r.get("volume_regime", baseline.get("regime", "normal"))),
            volume_ratio=float(ratio) if ratio is not None else None,
            liquidity_note=str(r.get("liquidity_note", "")),
            summary=str(r.get("summary", "")),
            options_volume_note=_options_note_from_scan(r, options_scan),
            options_highlights=_highlights_from_scan(options_scan),
            options_by_expiration=dict(options_scan.get("by_expiration") or {}),
        )
    except Exception:  # noqa: BLE001
        return morgan.analyze_symbol(snap)


def run_alan_with_subteam(
    alan: AlanAgent,
    team: ApprovedSubTeam,
    trends: list[TrendReport],
    algorithms: list[AlgorithmReport],
    runner: SubTeamRunner,
    *,
    scanner_context: list[dict] | None = None,
    code_quality: CodeQualityReport | None = None,
    market_contexts: list[MarketContextReport] | None = None,
) -> DecisionBrief:
    by_symbol = {a.symbol: a for a in algorithms}
    pairs = [
        {
            "symbol": t.symbol,
            "trend": t.to_context(),
            "algorithm": by_symbol.get(t.symbol, {}).to_context()
            if t.symbol in by_symbol
            else None,
        }
        for t in trends
    ]
    task = f"Trend + algorithm pairs:\n{json.dumps(pairs, default=str)}\n"
    if scanner_context:
        task += f"\nScanner shortlist:\n{json.dumps(scanner_context, default=str)}\n"
    if code_quality is not None:
        task += f"\nCode-quality audit:\n{json.dumps(code_quality.to_context(), default=str)}\n"
    if market_contexts:
        task += (
            f"\nMorgan market context:\n"
            f"{json.dumps([m.to_context() for m in market_contexts], default=str)}\n"
        )
    members = runner.run_members(team, task, lead_slug="alan")
    try:
        r = runner.synthesize(
            lead_system=alan.system_prompt,
            task_context=task,
            member_outputs=members,
            schema=_ALAN_SCHEMA,
            instruction=(
                "You are Alan synthesizing your sub-team's bull/risk perspectives "
                "into one decision brief."
            ),
            lead_slug="alan",
        )
        confidence = clamp_conviction(r.get("confidence", 0.5), default=0.5)
        if code_quality and not code_quality.can_proceed:
            confidence = min(confidence, 0.25)
        elif code_quality and code_quality.worst_status.value == "degraded":
            confidence = min(confidence, 0.55)
        return DecisionBrief(
            recommendations=list(r.get("recommendations") or []),
            summary=r.get("summary", ""),
            confidence=confidence,
            code_quality=code_quality.to_context() if code_quality else None,
        )
    except Exception:  # noqa: BLE001
        return alan.aggregate(
            trends,
            algorithms,
            scanner_context=scanner_context,
            code_quality=code_quality,
            market_contexts=market_contexts,
        )
