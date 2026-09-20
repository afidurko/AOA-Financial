"""Team orchestrator — coordinates the twelve-member meshed team around one cycle.

Flow: Bob health gate → analysis lanes (Tom→Julie · Morgan · Hailey · Jim ·
Cindy, concurrent) → Alan decision → trading pipeline → Andrea risk plans →
execution → Aaron review → Alex brief.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

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
from aoa.parallel import fan_out, fan_out_named
from aoa.swarm.orchestrator import CycleResult, Orchestrator
from aoa.team.aaron import AaronAgent
from aoa.team.alan import AlanAgent
from aoa.team.alex import AlexAgent
from aoa.team.andrea import AndreaAgent
from aoa.team.bob import BobAgent
from aoa.team.cindy import CindyAgent
from aoa.team.code_engineering import CodeQualityReport
from aoa.team.hailey import HaileyAgent
from aoa.team.jim import JimAgent
from aoa.team.julie import JulieAgent
from aoa.team.kai import KaiAgent
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
from aoa.team.nova import NovaAgent
from aoa.team.reed import ReedAgent
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

T = TypeVar("T")


@dataclass
class TeamAnalysis:
    """Every analyst lane's output for one set of snapshots, plus Alan's call."""

    trends: list[TrendReport] = field(default_factory=list)
    algorithms: list[AlgorithmReport] = field(default_factory=list)
    market_contexts: list[MarketContextReport] = field(default_factory=list)
    catalysts: list[CatalystReport] = field(default_factory=list)
    short_term: list[ShortTermReport] = field(default_factory=list)
    company_analyses: list[CompanyAnalysisReport] = field(default_factory=list)
    decision: DecisionBrief = field(default_factory=lambda: DecisionBrief([], "", 0.0))
    code_quality: CodeQualityReport | None = None
    risk_plans: list[RiskPlanReport] = field(default_factory=list)


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

    def absorb(self, analysis: TeamAnalysis) -> None:
        self.trends = analysis.trends
        self.algorithms = analysis.algorithms
        self.decision = analysis.decision
        self.market_contexts = analysis.market_contexts
        self.catalysts = analysis.catalysts
        self.short_term = analysis.short_term
        self.company_analyses = analysis.company_analyses
        self.risk_plans = analysis.risk_plans


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
    """Runs Bob's health gate, team analysis lanes, then the trading swarm."""

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
        self.nova = NovaAgent(llm)
        self.reed = ReedAgent(llm)
        self.kai = KaiAgent(llm)
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

    # ------------------------------------------------------------ public API
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
        """Analysis lanes → Alan, without executing trades."""
        analysis = self.analyze(self._snapshots(universe), scanner_context=scanner_context)
        return analysis.trends, analysis.algorithms, analysis.decision

    def run_opportunity_sweep(
        self,
        *,
        universe: list[str] | None = None,
    ) -> OpportunitySweepResult:
        """Idle-time analysis sweep for overlooked setups; notifies per policy."""
        run_id = self.analytics.begin_cycle() if self.analytics else ""
        self.journal.record(
            "team.sweep.triggered",
            {
                "reason": "idle_no_alerts_or_opportunity_notifications",
                "threshold_seconds": self.config.opportunity_sweep_seconds,
            },
        )

        a = self.analyze(self._snapshots(universe))
        notes = self.notify_policy.evaluate_sweep(
            a.trends, a.decision, run_id=run_id, catalysts=a.catalysts
        )
        if notes:
            if self.analytics:
                self.notify_policy.log_all(self.analytics.store, notes)
            for note in notes:
                self._push_structured(note)

        self.journal.record(
            "team.sweep.complete",
            {
                "trends": len(a.trends),
                "catalysts": len(a.catalysts),
                "short_term": len(a.short_term),
                "company_analyses": len(a.company_analyses),
                "opportunities_notified": len(notes),
                "summary": a.decision.summary,
            },
        )
        return OpportunitySweepResult(
            trends=a.trends,
            algorithms=a.algorithms,
            catalysts=a.catalysts,
            short_term=a.short_term,
            company_analyses=a.company_analyses,
            decision=a.decision,
            opportunities_notified=len(notes),
        )

    def run_cycle(self, *, max_candidates: int = 6) -> TeamCycleResult:
        result = TeamCycleResult()
        run_id = self.analytics.begin_cycle() if self.analytics else ""

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
            return self._finish_cycle(result, run_id)

        cycle, analysis, team_remediation = self._run_team_trading_cycle(
            max_candidates=max_candidates
        )
        result.cycle = cycle
        result.absorb(analysis)

        bb = cycle.blackboard
        no_candidates = not bb.candidates
        result.ceo = self.aaron.review(
            health=health,
            tom_done=bool(analysis.trends) or not bb.universe,
            julie_done=bool(analysis.algorithms) or no_candidates,
            alan_done=True,
            hailey_done=bool(analysis.catalysts) or no_candidates,
            jim_done=bool(analysis.short_term) or no_candidates,
            cindy_done=bool(analysis.company_analyses) or no_candidates,
            andrea_done=bool(analysis.risk_plans) or no_candidates,
            decision=analysis.decision,
            tom_count=len(analysis.trends),
            julie_count=len(analysis.algorithms),
            remediation=remediation,
            team_remediation=team_remediation,
        )
        return self._finish_cycle(result, run_id)

    def run_assistant_brief(self, *, last_cycle: TeamCycleResult | None = None) -> AssistantBrief:
        """On-demand prioritization brief for the user (Alex)."""
        from aoa.loop.prompts import find_repo_root

        brief = self.alex.prioritize(
            cycle=last_cycle,
            analytics_store=self.analytics.store if self.analytics else None,
            market_open=self.broker.is_market_open(),
            loop_state_path=find_repo_root() / "STATE.md",
            repair_path=self.config.repair_path,
        )
        self.journal.record("team.alex.brief", brief.to_context())
        return brief

    def propose_team_expansions(
        self, *, replace_pending: bool = True
    ) -> list[TeamExpansionProposal]:
        """Each lead proposes a sub-team; stored for user approval."""
        from aoa.team.expansion import TeamExpansionService

        svc = TeamExpansionService(self.llm, self._require_store(), self.journal)
        return svc.propose_all(replace_pending=replace_pending)

    def start_quant_hire_round(self, *, replace_pending: bool = True):
        """Riley opens a 5-seat econophysics quant desk interview round."""
        from aoa.team.interview import QuantHireService

        svc = QuantHireService(self.llm, self._require_store(), self.journal)
        return svc.start_round(replace_pending=replace_pending)

    def latest_quant_hire_round(self):
        """Return the most recent quant hire interview round, if any."""
        from aoa.team.interview import QuantHireService

        svc = QuantHireService(self.llm, self._require_store(), self.journal)
        return svc.latest_round()

    # ------------------------------------------------------------ analysis
    def analyze(
        self,
        snapshots: dict,
        *,
        scanner_context: list[dict] | None = None,
        subteams: dict[str, ApprovedSubTeam] | None = None,
    ) -> TeamAnalysis:
        """Run every analyst lane over ``snapshots`` and let Alan decide.

        Tom→Julie, Morgan, Hailey, Jim and Cindy are independent given the
        snapshots, so they run concurrently (``AOA_TEAM_PARALLEL``); Alan
        aggregates once all lanes return. Journal order is deterministic.
        """
        subteams = subteams if subteams is not None else self._approved_subteams()
        a = TeamAnalysis()
        a.code_quality = self.bob.audit_codebase()
        self.journal.record("team.bob.code_quality", a.code_quality.to_context())

        if snapshots:
            lanes = {
                "trend_algo": lambda: self._run_trend_algo(snapshots, a.code_quality, subteams),
                "market": lambda: self._run_morgan(snapshots, subteams),
                "catalysts": lambda: self.hailey.analyze_contexts(snapshots),
                "short_term": lambda: self.jim.analyze_contexts(snapshots),
                "company": lambda: self.cindy.analyze_contexts(snapshots),
            }
            out = fan_out_named(
                lanes,
                workers=self.config.parallel_workers,
                parallel=self.config.team_parallel,
            )
            a.trends, a.algorithms = out["trend_algo"]
            a.market_contexts = out["market"]
            a.catalysts = out["catalysts"]
            a.short_term = out["short_term"]
            a.company_analyses = out["company"]

        self._journal_lanes(a, subteams)
        a.decision = self._run_alan(a, subteams, scanner_context=scanner_context)
        self.journal.record(
            "team.alan.decision",
            {**a.decision.to_context(), "subteam": "Alan" in subteams},
        )
        return a

    def _journal_lanes(self, a: TeamAnalysis, subteams: dict[str, ApprovedSubTeam]) -> None:
        self.journal.record(
            "team.tom.trends",
            {"reports": [t.to_context() for t in a.trends], "subteam": "Tom" in subteams},
        )
        self.journal.record(
            "team.julie.algorithms",
            {
                "reports": [x.to_context() for x in a.algorithms],
                "subteam": "Julie" in subteams,
            },
        )
        self.journal.record(
            "team.morgan.context",
            {
                "reports": [m.to_context() for m in a.market_contexts],
                "subteam": "Morgan" in subteams,
            },
        )
        self.journal.record(
            "team.hailey.catalysts", {"reports": [c.to_context() for c in a.catalysts]}
        )
        self.journal.record(
            "team.jim.short_term", {"reports": [j.to_context() for j in a.short_term]}
        )
        self.journal.record(
            "team.cindy.company", {"reports": [c.to_context() for c in a.company_analyses]}
        )

    def _run_trend_algo(
        self,
        snapshots: dict,
        code_quality: CodeQualityReport | None,
        subteams: dict[str, ApprovedSubTeam],
    ) -> tuple[list[TrendReport], list[AlgorithmReport]]:
        trends = self._run_trends(snapshots, subteams)
        algorithms = (
            self._run_julie_for_trends(trends, snapshots, code_quality, subteams)
            if trends
            else []
        )
        return trends, algorithms

    def _run_trends(
        self, snapshots: dict, subteams: dict[str, ApprovedSubTeam]
    ) -> list[TrendReport]:
        team = subteams.get("Tom")
        if team:
            return run_tom_with_subteam(self.tom, team, snapshots, self._subteam_runner())
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

    def _run_julie_for_trends(
        self,
        trends: list[TrendReport],
        snapshots: dict,
        code_quality: CodeQualityReport | None,
        subteams: dict[str, ApprovedSubTeam],
    ) -> list[AlgorithmReport]:
        with_data = [t for t in trends if t.symbol in snapshots]
        team = subteams.get("Julie")
        if team:
            runner = self._subteam_runner()
            return [
                run_julie_with_subteam(
                    self.julie, team, t, snapshots[t.symbol], runner, code_quality=code_quality
                )
                for t in with_data
            ]
        return fan_out(
            lambda t: self.julie.refine(t, snapshots[t.symbol], code_quality=code_quality),
            with_data,
            workers=self.config.parallel_workers,
            parallel=self.config.team_parallel,
        )

    def _run_alan(
        self,
        a: TeamAnalysis,
        subteams: dict[str, ApprovedSubTeam],
        *,
        scanner_context: list[dict] | None = None,
    ) -> DecisionBrief:
        kwargs = dict(
            scanner_context=scanner_context,
            code_quality=a.code_quality,
            market_contexts=a.market_contexts,
            catalyst_contexts=a.catalysts,
            short_term_contexts=a.short_term,
            company_contexts=a.company_analyses,
        )
        team = subteams.get("Alan")
        if team:
            return run_alan_with_subteam(
                self.alan, team, a.trends, a.algorithms, self._subteam_runner(), **kwargs
            )
        return self.alan.aggregate(a.trends, a.algorithms, **kwargs)

    # ------------------------------------------------------------ trading cycle
    def _run_team_trading_cycle(
        self, *, max_candidates: int
    ) -> tuple[CycleResult, TeamAnalysis, list[RemediationAction]]:
        """intake→scan→analyze, inject team brief, portfolio→risk, Andrea, execute."""
        team_remediation: list[RemediationAction] = []
        orch = self.trading
        ctx = orch._build_context(max_candidates=max_candidates)
        orch.pipeline.run_until(ctx, "portfolio")
        orch._ctx = ctx
        bb = ctx.blackboard

        if not bb.universe:
            return CycleResult(blackboard=bb, notes=ctx.notes), TeamAnalysis(), team_remediation

        symbols = [c.get("symbol", "").upper() for c in bb.candidates if c.get("symbol")]
        snaps = {s: bb.snapshots[s] for s in symbols if s in bb.snapshots}
        subteams = self._approved_subteams()
        a = self.analyze(snaps, scanner_context=bb.candidates, subteams=subteams)
        self.journal.record("team.julie.code_audit", a.code_quality.to_context())

        # Aaron's remediation: re-run a lane once when it came back empty.
        if snaps and not a.trends:
            action, a.trends = self._rerun(
                "Tom", lambda: self._run_trends(snaps, subteams), fallback=a.trends
            )
            team_remediation.append(action)
            self.journal.record(
                "team.tom.trends", {"reports": [t.to_context() for t in a.trends]}
            )
        if a.trends and len(a.algorithms) < len(a.trends):
            action, a.algorithms = self._rerun(
                "Julie",
                lambda: self._run_julie_for_trends(a.trends, snaps, a.code_quality, subteams),
                fallback=a.algorithms,
                expect_count=len(a.trends),
            )
            team_remediation.append(action)
            self.journal.record(
                "team.julie.algorithms", {"reports": [x.to_context() for x in a.algorithms]}
            )
        if a.trends and not a.decision.recommendations:
            action, a.decision = self._rerun(
                "Alan",
                lambda: self._run_alan(a, subteams, scanner_context=bb.candidates),
                fallback=a.decision,
            )
            team_remediation.append(action)
            self.journal.record("team.alan.decision", a.decision.to_context())

        _inject_team_brief(bb.environment, a, symbols)
        if a.decision.summary:
            prefix = a.decision.summary
            bb.commentary = f"{prefix}\n\n{bb.commentary}".strip() if bb.commentary else prefix

        orch.pipeline.run_until(ctx, "execute")
        orch._ctx = ctx

        a.risk_plans = self.andrea.analyze_plans(
            proposals=list(bb.proposals),
            decision=a.decision,
            trends=a.trends,
            algorithms=a.algorithms,
            market_contexts=a.market_contexts,
            catalysts=a.catalysts,
            snapshots=snaps,
            options_ideas=bb.options_ideas,
        )
        self.journal.record(
            "team.andrea.risk_plans", {"reports": [r.to_context() for r in a.risk_plans]}
        )
        _inject_risk_plans(bb.environment, a.risk_plans, symbols)

        orch.pipeline.run_from(ctx, "execute")
        orch._ctx = ctx

        cr = CycleResult(blackboard=bb, execution=ctx.execution, notes=ctx.notes)
        return cr, a, team_remediation

    def _rerun(
        self,
        name: str,
        fn: Callable[[], T],
        *,
        fallback: T,
        expect_count: int = 1,
    ) -> tuple[RemediationAction, T]:
        """Re-run one lane exactly once; return Aaron's action and the fresh output.

        ``retry_team_member`` swallows exceptions into a failed action, so the
        previous output is kept when the re-run itself blows up.
        """
        box: dict[str, T] = {}

        def _capture() -> T:
            box["out"] = fn()
            return box["out"]

        action = self.remediator.retry_team_member(name, _capture, expect_count=expect_count)
        return action, box.get("out", fallback)

    def _finish_cycle(self, result: TeamCycleResult, run_id: str) -> TeamCycleResult:
        self.journal.record("team.aaron.review", result.ceo.to_context())
        if self.analytics:
            self.analytics.persist_cycle(result)
        self._dispatch_cycle_notifications(result, run_id=run_id)
        result.assistant = self._run_assistant(result)
        return result

    # ------------------------------------------------------------ helpers
    def _snapshots(self, universe: list[str] | None) -> dict:
        symbols = universe or list(self.config.universe) or self.broker.get_most_active(limit=10)
        self.trading.market.clear_cache()
        return self.trading.market.snapshots(symbols)

    def _require_store(self):
        if self.analytics is None:
            raise RuntimeError("Analytics must be enabled (AOA_ANALYTICS_ENABLED=1)")
        return self.analytics.store

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

    def _run_assistant(self, result: TeamCycleResult) -> AssistantBrief:
        brief = self.alex.prioritize(
            cycle=result,
            analytics_store=self.analytics.store if self.analytics else None,
            market_open=self.broker.is_market_open(),
        )
        self.journal.record("team.alex.brief", brief.to_context())
        return brief

    def _dispatch_cycle_notifications(self, result: TeamCycleResult, *, run_id: str) -> None:
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


def _inject_team_brief(environment, a: TeamAnalysis, symbols: list[str]) -> None:
    brief_ctx = a.decision.to_context()
    environment.global_context["team_brief"] = brief_ctx
    trend_by = {t.symbol: t for t in a.trends}
    algo_by = {x.symbol: x for x in a.algorithms}
    catalyst_by = {c.symbol: c for c in a.catalysts}
    jim_by = {j.symbol: j for j in a.short_term}
    cindy_by = {c.symbol: c for c in a.company_analyses}
    rec_by = {r["symbol"].upper(): r for r in a.decision.recommendations if r.get("symbol")}

    def ctx_of(by: dict, sym: str):
        return by[sym].to_context() if sym in by else None

    for sym in symbols:
        environment.set_domain(
            f"team:{sym}",
            {
                "trend": ctx_of(trend_by, sym),
                "algorithm": ctx_of(algo_by, sym),
                "catalyst": ctx_of(catalyst_by, sym),
                "short_term": ctx_of(jim_by, sym),
                "company": ctx_of(cindy_by, sym),
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
