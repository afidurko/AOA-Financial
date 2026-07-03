"""Cycle context — shared runtime state passed through pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.brokerage.base import Broker
from aoa.config import Config
from aoa.data.market_data import MarketDataService
from aoa.data.news import NewsFeed
from aoa.execution.executor import ExecutionReport, Executor
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient
from aoa.plasticity.store import PlasticityStore
from aoa.state import StateStore
from aoa.swarm.blackboard import Blackboard
from aoa.swarm.team import AgentTeam


@dataclass
class CycleContext:
    """Mutable runtime bag threaded through every pipeline stage."""

    config: Config
    broker: Broker
    llm: LLMClient
    journal: Journal
    market: MarketDataService
    agents: AgentTeam
    executor: Executor
    news: NewsFeed
    state: StateStore
    signal_adapter: SignalAdapter | None = None
    adapt_pending: dict[str, dict] = field(default_factory=dict)
    plasticity: PlasticityStore | None = None
    blackboard: Blackboard = field(default_factory=Blackboard)
    notes: list[str] = field(default_factory=list)
    execution: ExecutionReport | None = None
    max_candidates: int = 6
    news_by_symbol: dict[str, list] = field(default_factory=dict)
    portfolio_output: dict = field(default_factory=dict)

    # Daily-loss tracking (owned by the orchestrator, read by risk stage).
    equity_day: date | None = None
    starting_equity: float = 0.0

    def update_starting_equity(self, equity: float) -> None:
        """Persist and return the day's equity baseline for the kill switch."""
        self.starting_equity = self.state.starting_equity_for_today(equity)
        self.equity_day = date.today()
