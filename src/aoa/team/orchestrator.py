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
from aoa.team.andrea import AndreaAgent
from aoa.team.bob import BobAgent
from aoa.team.cindy import CindyAgent
from aoa.team.hailey import HaileyAgent
from aoa.team.jim import JimAgent
from aoa.team.julie import JulieAgent
from aoa.team.models import (
    AlgorithmReport,
    AssistantBrief,
    CatalystReport,
    CEOReport,
    CompanyAnalysisReport,
    DecisionBrief,
    HealthReport,
    MarketContextReport,
    RiskPlanReport,
    ShortTermReport,
    TeamExpansionProposal,
    TrendReport,
)
from aoa.team.morgan import MorganAgent
from aoa.team.remediation import RemediationAction, RemediationResult, TeamRemediator
from aoa.team.subteam import (
    ApprovedSubTeam,
    SubTeamRunner,
    load_approved_subteams,
    run_alan_with_subteam,
    run_julie_with_subteam,
    run_morgan_with_subteam,
    run_tom_with_subteam,
)
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
    catalysts: list[CatalystReport] = field(default_factory=list)
    short_term: list[ShortTermReport] = field(default_factory=list)
    company_analyses: list[CompanyAnalysisReport] = field(default_factory=list)
    risk_plans: list[RiskPlanReport] = field(default_factory=list)
    ceo: CEOReport | None = None
    assistant: AssistantBrief | None = None
    remediation: RemediationResult | None = None
    halted: bool = False
    halt_reason: str = ""


@dataclass
class OpportunitySweepResult:
    """Outcome of an idle-triggered market analysis sweep."""

    trends: list[TrendReport] = field(default_factory=list)
    algorithms: list[AlgorithmReport] = field(default_factory=list)
    catalysts: list[CatalystReport] = field(default_factory=list)
    short_term: list[ShortTermReport] = field(default_factory=list)
    company_analyses: list[CompanyAnalysisReport] = field(default_factory=list)
    decision: DecisionBrief | None = None
    opportunities_notified: int = 0


class TeamOrchestrator:
    """Runs Bob's health gate, team analysis chain, then the trading swarm."""

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
        from aoa.data.news import NullNewsFeed

        self.news_feed = news or NullNewsFeed()

        self.tom = TomAgent(llm)
        self.julie = JulieAgent(llm)
        self.morgan = MorganAgent(llm, broker)
        self.hailey = HaileyAgent(llm, self.news_feed)
        self.jim = JimAgent(llm)
        self.cindy = CindyAgent(llm)
        self.andrea = AndreaAgent(llm, broker, config)
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
        """Tom → Julie → Morgan → Alan pipeline without executing trades."""
        symbols = universe or list(self.config.universe) or self.broker.get_most_active(limit=10)
        self.trading.market.clear_cache()
        snapshots = self.trading.market.snapshots(symbols)

        trends, algorithms, market_contexts, catalysts, short_term, company, decision, _ = (
            self._run_analysis_pipeline(
                snapshots,
                scanner_context=scanner_context,
            )
        )
        _ = market_contexts, catalysts, short_term, company
        return trends, algorithms, decision

    def run_opportunity_sweep(
        self,
        *,
        universe: list[str] | None = None,
    ) -> OpportunitySweepResult:
        """Tom → Julie → Morgan → Hailey → Alan analysis for overlooked setups."""
        run_id = ""
        if self.analytics:
            run_id = self.analytics.begin_cycle()

        self.journal.record(
            "team.sweep.triggered",
            {
                "reason": "idle_no_alerts_or_opportunity_notifications",
                "threshold_seconds": self.config.opportunity_sweep_seconds,
            },
        )

        symbols = universe or list(self.config.universe) or self.broker.get_most_active(limit=10)
        self.trading.market.clear_cache()
        snapshots = self.trading.market.snapshots(symbols)

        (
            trends,
            algorithms,
            market_contexts,
            catalysts,
            short_term,
            company,
            decision,
            _,
        ) = self._run_analysis_pipeline(
            snapshots,
        )
        _ = market_contexts

        notes = self.notify_policy.evaluate_sweep(
            trends,
            decision,
            run_id=run_id,
            catalysts=catalysts,
        )
        if notes:
            if self.analytics:
                self.notify_policy.log_all(self.analytics.store, notes)
            for note in notes:
                self._push_structured(note)

        result = OpportunitySweepResult(
            trends=trends,
            algorithms=algorithms,
            catalysts=catalysts,
            short_term=short_term,
            company_analyses=company,
            decision=decision,
            opportunities_notified=len(notes),
        )
        self.journal.record(
            "team.sweep.complete",
            {
                "trends": len(trends),
                "catalysts": len(catalysts),
                "short_term": len(short_term),
                "company_analyses": len(company),
                "opportunities_notified": len(notes),
                "summary": decision.summary if decision else "",
            },
        )
        return result

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
        result.catalysts = getattr(cycle, "_team_catalysts", [])
        result.short_term = getattr(cycle, "_team_short_term", [])
        result.company_analyses = getattr(cycle, "_team_company_analyses", [])
        result.risk_plans = getattr(cycle, "_team_risk_plans", [])

        result.ceo = self.aaron.review(
            health=health,
            tom_done=len(result.trends) > 0 or not cycle.blackboard.universe,
            julie_done=len(result.algorithms) > 0 or not cycle.blackboard.candidates,
            alan_done=result.decision is not None,
            hailey_done=len(result.catalysts) > 0 or not cycle.blackboard.candidates,
            jim_done=len(result.short_term) > 0 or not cycle.blackboard.candidates,
            cindy_done=len(result.company_analyses) > 0 or not cycle.blackboard.candidates,
            andrea_done=len(result.risk_plans) > 0 or not cycle.blackboard.candidates,
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
        from aoa.loop.prompts import find_repo_root

        cycle = last_cycle
        repo_root = find_repo_root()
        brief = self.alex.prioritize(
            cycle=cycle,
            analytics_store=self.analytics.store if self.analytics else None,
            market_open=self.broker.is_market_open(),
            loop_state_path=repo_root / "STATE.md",
            repair_path=self.config.repair_path,
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
            cr._team_catalysts = []  # type: ignore[attr-defined]
            cr._team_short_term = []  # type: ignore[attr-defined]
            cr._team_company_analyses = []  # type: ignore[attr-defined]
            cr._team_risk_plans = []  # type: ignore[attr-defined]
            return cr, team_remediation

        candidate_symbols = [c.get("symbol", "").upper() for c in bb.candidates if c.get("symbol")]
        candidate_snaps = {s: bb.snapshots[s] for s in candidate_symbols if s in bb.snapshots}

        subteams = self._approved_subteams()
        (
            trends,
            algorithms,
            market_contexts,
            catalysts,
            short_term,
            company_analyses,
            decision,
            code_quality,
        ) = self._run_analysis_pipeline(
            candidate_snaps,
            scanner_context=bb.candidates,
            subteams=subteams,
        )
        self.journal.record("team.julie.code_audit", code_quality.to_context())

        if candidate_snaps and not trends:
            team_remediation.append(
                self.remediator.retry_team_member(
                    "Tom",
                    lambda: self._run_trends(candidate_snaps, subteams),
                )
            )
            trends = self._run_trends(candidate_snaps, subteams)
            self.journal.record(
                "team.tom.trends",
                {"reports": [t.to_context() for t in trends]},
            )

        if trends and len(algorithms) < len(trends):
            team_remediation.append(
                self.remediator.retry_team_member(
                    "Julie",
                    lambda: self._run_julie_for_trends(
                        trends,
                        candidate_snaps,
                        code_quality,
                        subteams,
                        parallel=self.config.team_parallel,
                    ),
                    expect_count=len(trends),
                )
            )
            algorithms = self._run_julie_for_trends(
                trends,
                candidate_snaps,
                code_quality,
                subteams,
                parallel=self.config.team_parallel,
            )
            self.journal.record(
                "team.julie.algorithms",
                {"reports": [a.to_context() for a in algorithms]},
            )

        if trends and not decision.recommendations:
            team_remediation.append(
                self.remediator.retry_team_member(
                    "Alan",
                    lambda: self._run_alan(
                        trends,
                        algorithms,
                        subteams,
                        scanner_context=bb.candidates,
                        code_quality=code_quality,
                        market_contexts=market_contexts,
                        catalyst_contexts=catalysts,
                        short_term_contexts=short_term,
                        company_contexts=company_analyses,
                    ),
                )
            )
            decision = self._run_alan(
                trends,
                algorithms,
                subteams,
                scanner_context=bb.candidates,
                code_quality=code_quality,
                market_contexts=market_contexts,
                catalyst_contexts=catalysts,
                short_term_contexts=short_term,
                company_contexts=company_analyses,
            )
            self.journal.record("team.alan.decision", decision.to_context())

        _inject_team_brief(
            bb.environment,
            trends,
            algorithms,
            decision,
            candidate_symbols,
            catalysts=catalysts,
            short_term=short_term,
            company_analyses=company_analyses,
        )
        if decision.summary:
            prefix = decision.summary
            bb.commentary = f"{prefix}\n\n{bb.commentary}".strip() if bb.commentary else prefix

        orch.pipeline.run_until(ctx, "execute")
        orch._ctx = ctx

        risk_plans = self.andrea.analyze_plans(
            proposals=list(bb.proposals),
            decision=decision,
            trends=trends,
            algorithms=algorithms,
            market_contexts=market_contexts,
            catalysts=catalysts,
            snapshots=candidate_snaps,
            options_ideas=bb.options_ideas,
        )
        self.journal.record(
            "team.andrea.risk_plans",
            {"reports": [r.to_context() for r in risk_plans]},
        )
        _inject_risk_plans(bb.environment, risk_plans, candidate_symbols)

        orch.pipeline.run_from(ctx, "execute")
        orch._ctx = ctx

        cr = CycleResult(blackboard=bb, execution=ctx.execution, notes=ctx.notes)
        cr._team_trends = trends  # type: ignore[attr-defined]
        cr._team_algorithms = algorithms  # type: ignore[attr-defined]
        cr._team_decision = decision  # type: ignore[attr-defined]
        cr._team_market_contexts = market_contexts  # type: ignore[attr-defined]
        cr._team_catalysts = catalysts  # type: ignore[attr-defined]
        cr._team_short_term = short_term  # type: ignore[attr-defined]
        cr._team_company_analyses = company_analyses  # type: ignore[attr-defined]
        cr._team_risk_plans = risk_plans  # type: ignore[attr-defined]
        return cr, team_remediation

    def _approved_subteams(self) -> dict[str, ApprovedSubTeam]:
        if not self.config.team_subagents_enabled or self.analytics is None:
            return {}
        return load_approved_subteams(self.analytics.store)

    def _subteam_runner(self) -> SubTeamRunner:
        return SubTeamRunner(
            self.llm,
            self.journal,
            parallel=self.config.team_parallel,
            max_workers=self.config.parallel_workers,
        )

    def _run_analysis_pipeline(
        self,
        snapshots: dict,
        *,
        scanner_context: list[dict] | None = None,
        subteams: dict[str, ApprovedSubTeam] | None = None,
    ) -> tuple[
        list[TrendReport],
        list[AlgorithmReport],
        list[MarketContextReport],
        list[CatalystReport],
        list[ShortTermReport],
        list[CompanyAnalysisReport],
        DecisionBrief,
        object,
    ]:
        subteams = subteams if subteams is not None else self._approved_subteams()
        code_quality = self.bob.audit_codebase()
        self.journal.record("team.bob.code_quality", code_quality.to_context())

        trends = self._run_trends(snapshots, subteams) if snapshots else []
        self.journal.record(
            "team.tom.trends",
            {"reports": [t.to_context() for t in trends], "subteam": "Tom" in subteams},
        )

        algorithms: list[AlgorithmReport] = []
        if trends:
            algorithms = self._run_julie_for_trends(
                trends,
                snapshots,
                code_quality,
                subteams,
                parallel=self.config.team_parallel,
            )
        self.journal.record(
            "team.julie.algorithms",
            {"reports": [a.to_context() for a in algorithms], "subteam": "Julie" in subteams},
        )

        market_contexts = self._run_morgan(snapshots, subteams) if snapshots else []
        self.journal.record(
            "team.morgan.context",
            {"reports": [m.to_context() for m in market_contexts], "subteam": "Morgan" in subteams},
        )

        catalysts = self.hailey.analyze_contexts(snapshots) if snapshots else []
        self.journal.record(
            "team.hailey.catalysts",
            {"reports": [c.to_context() for c in catalysts]},
        )

        short_term = self.jim.analyze_contexts(snapshots) if snapshots else []
        self.journal.record(
            "team.jim.short_term",
            {"reports": [j.to_context() for j in short_term]},
        )

        company_analyses = self.cindy.analyze_contexts(snapshots) if snapshots else []
        self.journal.record(
            "team.cindy.company",
            {"reports": [c.to_context() for c in company_analyses]},
        )

        decision = self._run_alan(
            trends,
            algorithms,
            subteams,
            scanner_context=scanner_context,
            code_quality=code_quality,
            market_contexts=market_contexts,
            catalyst_contexts=catalysts,
            short_term_contexts=short_term,
            company_contexts=company_analyses,
        )
        self.journal.record(
            "team.alan.decision",
            {**decision.to_context(), "subteam": "Alan" in subteams},
        )
        return (
            trends,
            algorithms,
            market_contexts,
            catalysts,
            short_term,
            company_analyses,
            decision,
            code_quality,
        )

    def _run_trends(
        self, snapshots: dict, subteams: dict[str, ApprovedSubTeam]
    ) -> list[TrendReport]:
        team = subteams.get("Tom")
        if team:
            return run_tom_with_subteam(
                self.tom, team, snapshots, self._subteam_runner()
            )
        return self.tom.analyze_trends(snapshots)

    def _run_morgan(
        self, snapshots: dict, subteams: dict[str, ApprovedSubTeam]
    ) -> list[MarketContextReport]:
        team = subteams.get("Morgan")
        if team:
            return [
                run_morgan_with_subteam(self.morgan, team, snap, self._subteam_runner())
                for snap in snapshots.values()
            ]
        return self.morgan.analyze_contexts(snapshots)

    def _run_alan(
        self,
        trends: list[TrendReport],
        algorithms: list[AlgorithmReport],
        subteams: dict[str, ApprovedSubTeam],
        *,
        scanner_context: list[dict] | None = None,
        code_quality=None,
        market_contexts: list[MarketContextReport] | None = None,
        catalyst_contexts: list[CatalystReport] | None = None,
        short_term_contexts: list[ShortTermReport] | None = None,
        company_contexts: list[CompanyAnalysisReport] | None = None,
    ) -> DecisionBrief:
        team = subteams.get("Alan")
        if team:
            return run_alan_with_subteam(
                self.alan,
                team,
                trends,
                algorithms,
                self._subteam_runner(),
                scanner_context=scanner_context,
                code_quality=code_quality,
                market_contexts=market_contexts,
                catalyst_contexts=catalyst_contexts,
                short_term_contexts=short_term_contexts,
                company_contexts=company_contexts,
            )
        return self.alan.aggregate(
            trends,
            algorithms,
            scanner_context=scanner_context,
            code_quality=code_quality,
            market_contexts=market_contexts,
            catalyst_contexts=catalyst_contexts,
            short_term_contexts=short_term_contexts,
            company_contexts=company_contexts,
        )

    def _run_julie_for_trends(
        self,
        trends: list[TrendReport],
        snapshots: dict,
        code_quality,
        subteams: dict[str, ApprovedSubTeam],
        *,
        parallel: bool,
    ) -> list[AlgorithmReport]:
        team = subteams.get("Julie")
        if team:
            runner = self._subteam_runner()
            out: list[AlgorithmReport] = []
            for trend in trends:
                snap = snapshots.get(trend.symbol)
                if snap:
                    out.append(
                        run_julie_with_subteam(
                            self.julie,
                            team,
                            trend,
                            snap,
                            runner,
                            code_quality=code_quality,
                        )
                    )
            return out
        return self._julie_for_trends(
            trends, snapshots, code_quality, parallel=parallel
        )

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
    *,
    catalysts: list[CatalystReport] | None = None,
    short_term: list[ShortTermReport] | None = None,
    company_analyses: list[CompanyAnalysisReport] | None = None,
) -> None:
    brief_ctx = decision.to_context()
    environment.global_context["team_brief"] = brief_ctx
    trend_by = {t.symbol: t for t in trends}
    algo_by = {a.symbol: a for a in algorithms}
    catalyst_by = {c.symbol: c for c in (catalysts or [])}
    jim_by = {j.symbol: j for j in (short_term or [])}
    cindy_by = {c.symbol: c for c in (company_analyses or [])}
    rec_by = {r["symbol"].upper(): r for r in decision.recommendations if r.get("symbol")}
    for sym in symbols:
        environment.set_domain(
            f"team:{sym}",
            {
                "trend": trend_by[sym].to_context() if sym in trend_by else None,
                "algorithm": algo_by[sym].to_context() if sym in algo_by else None,
                "catalyst": catalyst_by[sym].to_context() if sym in catalyst_by else None,
                "short_term": jim_by[sym].to_context() if sym in jim_by else None,
                "company": cindy_by[sym].to_context() if sym in cindy_by else None,
                "recommendation": rec_by.get(sym),
                "team_brief": brief_ctx,
            },
        )


def _inject_risk_plans(
    environment,
    risk_plans: list[RiskPlanReport],
    symbols: list[str],
) -> None:
    by_sym = {r.symbol.upper(): r for r in risk_plans}
    environment.global_context["risk_plans"] = [r.to_context() for r in risk_plans]
    for sym in symbols:
        plan = by_sym.get(sym)
        if plan is None:
            continue
        slice_ = environment.domains.get(f"team:{sym}")
        if slice_ is not None:
            slice_.data["risk_plan"] = plan.to_context()
