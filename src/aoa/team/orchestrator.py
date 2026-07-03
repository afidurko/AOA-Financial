"""Team orchestrator — coordinates Tom, Julie, Bob, Alan, and Aaron."""

from __future__ import annotations

from dataclasses import dataclass, field

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.brokerage.base import Broker
from aoa.config import Config
from aoa.data.news import NewsFeed
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient
from aoa.notify.iphone import IPhoneNotifier
from aoa.swarm.orchestrator import CycleResult, Orchestrator
from aoa.team.aaron import AaronAgent
from aoa.team.alan import AlanAgent
from aoa.team.bob import BobAgent
from aoa.team.julie import JulieAgent
from aoa.team.models import (
    AlgorithmReport,
    CEOReport,
    DecisionBrief,
    HealthReport,
    TrendReport,
)
from aoa.team.remediation import RemediationAction, RemediationResult, TeamRemediator
from aoa.team.tom import TomAgent


@dataclass
class TeamCycleResult:
    """Outcome of a team-coordinated trading cycle."""

    cycle: CycleResult | None = None
    health: HealthReport | None = None
    trends: list[TrendReport] = field(default_factory=list)
    algorithms: list[AlgorithmReport] = field(default_factory=list)
    decision: DecisionBrief | None = None
    ceo: CEOReport | None = None
    remediation: RemediationResult | None = None
    halted: bool = False
    halt_reason: str = ""


class TeamOrchestrator:
    """Runs Bob's health gate, Tom→Julie→Alan analysis, then the trading swarm."""

    def __init__(
        self,
        config: Config,
        broker: Broker,
        llm: LLMClient,
        journal: Journal | None = None,
        news: NewsFeed | None = None,
        signal_adapter: SignalAdapter | None = None,
    ) -> None:
        self.config = config
        self.broker = broker
        self.llm = llm
        self.journal = journal or Journal(config.journal_path)

        self.tom = TomAgent(llm)
        self.julie = JulieAgent(llm)
        self.bob = BobAgent(config, broker)
        self.alan = AlanAgent(llm)
        self.remediator = TeamRemediator(self.bob, broker)
        notifier = IPhoneNotifier(
            custom_app_webhook_url=config.custom_app_webhook_url,
            custom_app_api_key=config.custom_app_api_key,
            custom_app_device_id=config.custom_app_device_id,
            pushover_user_key=config.pushover_user_key,
            pushover_app_token=config.pushover_app_token,
            ntfy_topic=config.ntfy_topic,
            ntfy_server=config.ntfy_server,
        )
        self.aaron = AaronAgent(
            llm,
            config=config,
            remediator=self.remediator,
            notifier=notifier,
            journal=self.journal,
        )
        self.trading = Orchestrator(
            config, broker, llm, self.journal, news, signal_adapter=signal_adapter
        )

    def run_health_check(self) -> HealthReport:
        report = self.bob.check_health()
        self.journal.record("team.bob.health", report.to_context())
        return report

    def run_team_brief(
        self,
        *,
        universe: list[str] | None = None,
        scanner_context: list[dict] | None = None,
    ) -> tuple[list[TrendReport], list[AlgorithmReport], DecisionBrief]:
        """Tom → Julie → Alan pipeline without executing trades."""
        symbols = universe or list(self.config.universe) or self.broker.get_most_active(limit=10)
        self.trading.market.clear_cache()
        snapshots = self.trading.market.snapshots(symbols)

        code_quality = self.bob.audit_codebase()
        self.journal.record("team.bob.code_quality", code_quality.to_context())

        trends = self.tom.analyze_trends(snapshots)
        self.journal.record(
            "team.tom.trends",
            {"reports": [t.to_context() for t in trends]},
        )

        algorithms: list[AlgorithmReport] = []
        for trend in trends:
            snap = snapshots.get(trend.symbol)
            if snap:
                algorithms.append(
                    self.julie.refine(trend, snap, code_quality=code_quality)
                )
        self.journal.record(
            "team.julie.algorithms",
            {"reports": [a.to_context() for a in algorithms]},
        )

        decision = self.alan.aggregate(
            trends,
            algorithms,
            scanner_context=scanner_context,
            code_quality=code_quality,
        )
        self.journal.record("team.alan.decision", decision.to_context())
        return trends, algorithms, decision

    def run_cycle(self, *, max_candidates: int = 6) -> TeamCycleResult:
        result = TeamCycleResult()

        # 1) Bob — systems health gate; Aaron may fix recoverable issues.
        health = self.run_health_check()
        remediation = self.aaron.attempt_health_recovery(
            health,
            market_cache_clear=self.trading.market.clear_cache,
        )
        result.remediation = remediation
        if remediation.health:
            health = remediation.health
        result.health = health

        if not health.can_proceed:
            result.halted = True
            result.halt_reason = health.summary
            result.ceo = self.aaron.review(
                health=health,
                tom_done=False,
                julie_done=False,
                alan_done=False,
                decision=None,
                halted=True,
                halt_reason=result.halt_reason,
                remediation=remediation,
            )
            self.journal.record("team.aaron.review", result.ceo.to_context())
            return result

        # 2) Trading cycle with team-augmented analysis.
        cycle, team_remediation = self._run_team_trading_cycle(max_candidates=max_candidates)
        result.cycle = cycle
        result.trends = getattr(cycle, "_team_trends", [])
        result.algorithms = getattr(cycle, "_team_algorithms", [])
        result.decision = getattr(cycle, "_team_decision", None)

        # 3) Aaron — CEO oversight, team fixes, iPhone alerts when needed.
        result.ceo = self.aaron.review(
            health=health,
            tom_done=len(result.trends) > 0 or not cycle.blackboard.universe,
            julie_done=len(result.algorithms) > 0 or not cycle.blackboard.candidates,
            alan_done=result.decision is not None,
            decision=result.decision,
            tom_count=len(result.trends),
            julie_count=len(result.algorithms),
            remediation=remediation,
            team_remediation=team_remediation,
        )
        self.journal.record("team.aaron.review", result.ceo.to_context())
        return result

    def _run_team_trading_cycle(
        self, *, max_candidates: int
    ) -> tuple[CycleResult, list[RemediationAction]]:
        """Run intake→scan→analyze, inject team brief, then portfolio→execute."""
        team_remediation: list[RemediationAction] = []
        orch = self.trading
        ctx = orch._build_context(max_candidates=max_candidates)
        orch.pipeline.run_until(ctx, "portfolio")
        orch._ctx = ctx
        bb = ctx.blackboard

        if not bb.universe:
            cr = CycleResult(blackboard=bb, notes=ctx.notes)
            cr._team_trends = []  # type: ignore[attr-defined]
            cr._team_algorithms = []  # type: ignore[attr-defined]
            cr._team_decision = None  # type: ignore[attr-defined]
            return cr, team_remediation

        candidate_symbols = [c.get("symbol", "").upper() for c in bb.candidates if c.get("symbol")]
        candidate_snaps = {s: bb.snapshots[s] for s in candidate_symbols if s in bb.snapshots}

        code_quality = self.bob.audit_codebase()
        self.journal.record("team.bob.code_quality", code_quality.to_context())
        self.journal.record("team.julie.code_audit", code_quality.to_context())

        trends = self.tom.analyze_trends(candidate_snaps) if candidate_snaps else []
        if candidate_snaps and not trends:
            team_remediation.append(
                self.remediator.retry_team_member(
                    "Tom",
                    lambda: self.tom.analyze_trends(candidate_snaps),
                )
            )
            trends = self.tom.analyze_trends(candidate_snaps)
        self.journal.record(
            "team.tom.trends",
            {"reports": [t.to_context() for t in trends]},
        )

        algorithms: list[AlgorithmReport] = []
        for trend in trends:
            snap = candidate_snaps.get(trend.symbol)
            if snap:
                algorithms.append(
                    self.julie.refine(trend, snap, code_quality=code_quality)
                )
        if trends and len(algorithms) < len(trends):
            team_remediation.append(
                self.remediator.retry_team_member(
                    "Julie",
                    lambda: [
                        self.julie.refine(
                            t, candidate_snaps[t.symbol], code_quality=code_quality
                        )
                        for t in trends
                        if t.symbol in candidate_snaps
                    ],
                    expect_count=len(trends),
                )
            )
            algorithms = [
                self.julie.refine(
                    t, candidate_snaps[t.symbol], code_quality=code_quality
                )
                for t in trends
                if t.symbol in candidate_snaps
            ]
        self.journal.record(
            "team.julie.algorithms",
            {"reports": [a.to_context() for a in algorithms]},
        )

        decision = self.alan.aggregate(
            trends,
            algorithms,
            scanner_context=bb.candidates,
            code_quality=code_quality,
        )
        if trends and not decision.recommendations:
            team_remediation.append(
                self.remediator.retry_team_member(
                    "Alan",
                    lambda: self.alan.aggregate(
                        trends,
                        algorithms,
                        scanner_context=bb.candidates,
                        code_quality=code_quality,
                    ),
                )
            )
            decision = self.alan.aggregate(
                trends,
                algorithms,
                scanner_context=bb.candidates,
                code_quality=code_quality,
            )
        self.journal.record("team.alan.decision", decision.to_context())

        _inject_team_brief(bb.environment, trends, algorithms, decision, candidate_symbols)
        if decision.summary:
            prefix = decision.summary
            bb.commentary = f"{prefix}\n\n{bb.commentary}".strip() if bb.commentary else prefix

        orch.pipeline.run_from(ctx, "portfolio")
        orch._ctx = ctx

        cr = CycleResult(blackboard=bb, execution=ctx.execution, notes=ctx.notes)
        cr._team_trends = trends  # type: ignore[attr-defined]
        cr._team_algorithms = algorithms  # type: ignore[attr-defined]
        cr._team_decision = decision  # type: ignore[attr-defined]
        return cr, team_remediation


def _inject_team_brief(
    environment,
    trends: list[TrendReport],
    algorithms: list[AlgorithmReport],
    decision: DecisionBrief,
    symbols: list[str],
) -> None:
    brief_ctx = decision.to_context()
    environment.global_context["team_brief"] = brief_ctx
    trend_by = {t.symbol: t for t in trends}
    algo_by = {a.symbol: a for a in algorithms}
    rec_by = {r["symbol"].upper(): r for r in decision.recommendations if r.get("symbol")}
    for sym in symbols:
        environment.set_domain(
            f"team:{sym}",
            {
                "trend": trend_by[sym].to_context() if sym in trend_by else None,
                "algorithm": algo_by[sym].to_context() if sym in algo_by else None,
                "recommendation": rec_by.get(sym),
                "team_brief": brief_ctx,
            },
        )
