"""The orchestrator — thin facade over the composable swarm pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.brokerage.base import Broker
from aoa.brokerage.models import Side
from aoa.config import Config
from aoa.data.market_data import MarketDataService
from aoa.data.news import NewsFeed, NullNewsFeed
from aoa.execution.executor import ExecutionReport, Executor
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient
from aoa.state import StateStore
from aoa.swarm.blackboard import Blackboard
from aoa.swarm.context import CycleContext
from aoa.swarm.pipeline import Pipeline
from aoa.swarm.stages import default_stages
from aoa.swarm.team import AgentTeam


@dataclass
class CycleResult:
    blackboard: Blackboard
    execution: ExecutionReport | None = None
    notes: list[str] = field(default_factory=list)


class Orchestrator:
    """Runs one full analysis→decision→execution cycle via a stage pipeline."""

    def __init__(
        self,
        config: Config,
        broker: Broker,
        llm: LLMClient,
        journal: Journal | None = None,
        news: NewsFeed | None = None,
        *,
        pipeline: Pipeline | None = None,
        signal_adapter: SignalAdapter | None = None,
    ) -> None:
        self.config = config
        self.broker = broker
        self.llm = llm
        self.journal = journal or Journal(config.journal_path)
        self.news = news if news is not None else NullNewsFeed()
        self.state = StateStore(config.state_path)
        self.market = MarketDataService(
            broker,
            timeframes=config.bar_timeframes,
            bar_feed=config.bar_feed,
        )
        self.agents = AgentTeam.from_llm(llm, broker, risk=config.risk)
        self.executor = Executor(
            broker, self.journal, dry_run=config.dry_run, state=self.state
        )
        self.pipeline = pipeline or Pipeline(stages=default_stages())

        # Optional low-rank online adaptation of agent signals.
        self.signal_adapter = signal_adapter
        self._adapt_pending: dict[str, dict] = {}

        # Preserve attributes referenced by tests and CLI.
        self.scanner = self.agents.scanner
        self.technical = self.agents.technical
        self.fundamental = self.agents.fundamental
        self.meshing = self.agents.meshing
        self.options = self.agents.options
        self.portfolio = self.agents.portfolio
        self.risk = self.agents.risk

        # Daily-loss tracking lives on the context each cycle.
        self._ctx: CycleContext | None = None

    @property
    def _starting_equity(self) -> float:
        return self._ctx.starting_equity if self._ctx else 0.0

    def run_cycle(self, *, max_candidates: int = 6) -> CycleResult:
        ctx = self._build_context(max_candidates=max_candidates)
        self.pipeline.run(ctx)
        self._ctx = ctx
        return CycleResult(
            blackboard=ctx.blackboard,
            execution=ctx.execution,
            notes=ctx.notes,
        )

    def run_until(self, stop_before: str, *, max_candidates: int = 6) -> CycleResult:
        """Run the pipeline up to a stage — useful for editing the environment mid-cycle."""
        ctx = self._build_context(max_candidates=max_candidates)
        self.pipeline.run_until(ctx, stop_before)
        self._ctx = ctx
        return CycleResult(blackboard=ctx.blackboard, notes=ctx.notes)

    def _build_context(self, *, max_candidates: int) -> CycleContext:
        return CycleContext(
            config=self.config,
            broker=self.broker,
            llm=self.llm,
            journal=self.journal,
            market=self.market,
            agents=self.agents,
            executor=self.executor,
            news=self.news,
            state=self.state,
            signal_adapter=self.signal_adapter,
            adapt_pending=self._adapt_pending,
            max_candidates=max_candidates,
            equity_day=self._ctx.equity_day if self._ctx else None,
            starting_equity=self._ctx.starting_equity if self._ctx else 0.0,
        )


def _marketable_limit(price: float, side: Side) -> float:
    """A protective limit ~1% through the mid to improve fill odds without chasing."""
    pad = 1.01 if side is Side.BUY else 0.99
    return round(price * pad, 2)
