"""Team orchestrator — coordinates Tom, Julie, Bob, Alan, and Aaron."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.analytics.bridge import CycleAnalyticsBridge
from aoa.brokerage.base import Broker
from aoa.config import Config
from aoa.data.news import NewsFeed
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient
from aoa.notify.iphone import IPhoneNotifier
from aoa.notify.policy import NotificationPolicy
from aoa.notify.types import StructuredNotification
from aoa.swarm.orchestrator import CycleResult, Orchestrator
from aoa.team.aaron import AaronAgent
from aoa.team.alan import AlanAgent
from aoa.team.alex import AlexAgent
from aoa.team.bob import BobAgent
from aoa.team.julie import JulieAgent
from aoa.team.models import (
    AlgorithmReport,
    AssistantBrief,
    CEOReport,
    DecisionBrief,
    HealthReport,
    MarketContextReport,
    TeamExpansionProposal,
    TrendReport,
)
from aoa.team.morgan import MorganAgent
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
    market_contexts: list[MarketContextReport] = field(default_factory=list)
    ceo: CEOReport | None = None
    assistant: AssistantBrief | None = None
    remediation: RemediationResult | None = None
    halted: bool = False
    halt_reason: str = ""


class TeamOrchestrator:
    """Runs Bob's health gate, Tom→Julie→Morgan→Alan analysis, then the trading swarm."""

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
        self.morgan = MorganAgent(llm)
        self.bob = BobAgent(config, broker)
        self.alan = AlanAgent(llm)
        self.alex = AlexAgent(llm)
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
        self.analytics = (
            CycleAnalyticsBridge.from_config(config) if config.analytics_enabled else None
        )
        self.trading.analytics_bridge = self.analytics
        self.notify_policy = NotificationPolicy(
            push_opportunities=config.notify_push_opportunities,
            push_halts=config.notify_push_halts,
            min_conviction=config.notify_min_conviction,
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
        if trends:
            algorithms = self._julie_for_trends(
                trends, snapshots, code_quality, parallel=self.config.team_parallel
            )
        self.journal.record(
            "team.julie.algorithms",
            {"reports": [a.to_context() for a in algorithms]},
        )

        market_contexts = self.morgan.analyze_contexts(snapshots) if snapshots else []
        self.journal.record(
            "team.morgan.context",
            {"reports": [m.to_context() for m in market_contexts]},
        )

        decision = self.alan.aggregate(
            trends,
            algorithms,
            scanner_context=scanner_context,
            code_quality=code_quality,
            market_contexts=market_contexts,
        )
        self.journal.record("team.alan.decision", decision.to_context())
        return trends, algorithms, decision

    def run_cycle(self, *, max_candidates: int = 6) -> TeamCycleResult:
        result = TeamCycleResult()
        run_id = ""
        if self.analytics:
            run_id = self.analytics.begin_cycle()

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
            if self.analytics:
                self.analytics.persist_cycle(result)
            self._dispatch_cycle_notifications(result, run_id=run_id)
            result.assistant = self._run_assistant(result)
            return result

        cycle, team_remediation = self._run_team_trading_cycle(max_candidates=max_candidates)
        result.cycle = cycle
        result.trends = getattr(cycle, "_team_trends", [])
        result.algorithms = getattr(cycle, "_team_algorithms", [])
        result.decision = getattr(cycle, "_team_decision", None)
        result.market_contexts = getattr(cycle, "_team_market_contexts", [])

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
        if self.analytics:
            self.analytics.persist_cycle(result)
        self._dispatch_cycle_notifications(result, run_id=run_id)
        result.assistant = self._run_assistant(result)
        return result

    def run_assistant_brief(self, *, last_cycle: TeamCycleResult | None = None) -> AssistantBrief:
        """On-demand prioritization brief for the user (Alex)."""
        cycle = last_cycle
        brief = self.alex.prioritize(
            cycle=cycle,
            analytics_store=self.analytics.store if self.analytics else None,
            market_open=self.broker.is_market_open(),
        )
        self.journal.record("team.alex.brief", brief.to_context())
        return brief

    def propose_team_expansions(
        self, *, replace_pending: bool = True
    ) -> list[TeamExpansionProposal]:
        """Each lead proposes a sub-team; stored for user approval."""
        if self.analytics is None:
            raise RuntimeError("Analytics must be enabled (AOA_ANALYTICS_ENABLED=1)")
        from aoa.team.expansion import TeamExpansionService

        svc = TeamExpansionService(self.llm, self.analytics.store, self.journal)
        return svc.propose_all(replace_pending=replace_pending)

    def _run_assistant(self, result: TeamCycleResult) -> AssistantBrief:
        brief = self.alex.prioritize(
            cycle=result,
            analytics_store=self.analytics.store if self.analytics else None,
            market_open=self.broker.is_market_open(),
        )
        self.journal.record("team.alex.brief", brief.to_context())
        return brief

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
        if trends:
            algorithms = self._julie_for_trends(
                trends,
                candidate_snaps,
                code_quality,
                parallel=self.config.team_parallel,
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

        market_contexts: list[MarketContextReport] = []
        if candidate_snaps:
            market_contexts = self.morgan.analyze_contexts(candidate_snaps)
        self.journal.record(
            "team.morgan.context",
            {"reports": [m.to_context() for m in market_contexts]},
        )

        decision = self.alan.aggregate(
            trends,
            algorithms,
            scanner_context=bb.candidates,
            code_quality=code_quality,
            market_contexts=market_contexts,
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
                        market_contexts=market_contexts,
                    ),
                )
            )
            decision = self.alan.aggregate(
                trends,
                algorithms,
                scanner_context=bb.candidates,
                code_quality=code_quality,
                market_contexts=market_contexts,
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
        cr._team_market_contexts = market_contexts  # type: ignore[attr-defined]
        return cr, team_remediation

    def _julie_for_trends(
        self,
        trends: list[TrendReport],
        snapshots: dict,
        code_quality,
        *,
        parallel: bool,
    ) -> list[AlgorithmReport]:
        if not parallel or len(trends) <= 1 or self.config.parallel_workers <= 1:
            out: list[AlgorithmReport] = []
            for trend in trends:
                snap = snapshots.get(trend.symbol)
                if snap:
                    out.append(self.julie.refine(trend, snap, code_quality=code_quality))
            return out

        algorithms: list[AlgorithmReport] = []
        workers = min(self.config.parallel_workers, len(trends))

        def _one(trend: TrendReport) -> AlgorithmReport | None:
            snap = snapshots.get(trend.symbol)
            if not snap:
                return None
            return self.julie.refine(trend, snap, code_quality=code_quality)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_one, t): t for t in trends}
            for fut in as_completed(futures):
                report = fut.result()
                if report is not None:
                    algorithms.append(report)
        algorithms.sort(key=lambda a: a.symbol)
        return algorithms

    def _dispatch_cycle_notifications(
        self, result: TeamCycleResult, *, run_id: str
    ) -> None:
        notes = self.notify_policy.evaluate_cycle(result, run_id=run_id)
        if not notes:
            return
        if self.analytics:
            self.notify_policy.log_all(self.analytics.store, notes)
        for note in notes:
            self._push_structured(note)

    def _push_structured(self, note: StructuredNotification) -> None:
        try:
            if self.aaron.notifier.configured:
                channels = self.aaron.notifier.send_structured(note)
                self.journal.record(
                    "team.notification.push",
                    {
                        "kind": note.kind.value,
                        "title": note.concise_title(),
                        "channels": channels,
                    },
                )
            else:
                self.journal.record("team.notification.logged", note.to_payload())
        except Exception as exc:  # noqa: BLE001
            self.journal.record(
                "team.notification.error",
                {"error": str(exc), "payload": note.to_payload()},
            )


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
