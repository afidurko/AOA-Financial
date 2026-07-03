"""The blackboard — shared per-cycle working memory for the swarm.

Agents read context from and write findings to the blackboard. Keeping the
shared state in one explicit object (rather than threading many arguments
through the orchestrator) makes the data flow auditable and easy to journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aoa.agents.base import Signal, TradeProposal
from aoa.brokerage.models import Account, OptionContract, Position
from aoa.data.market_data import SymbolSnapshot


@dataclass
class Blackboard:
    account: Account | None = None
    positions: list[Position] = field(default_factory=list)
    universe: list[str] = field(default_factory=list)
    snapshots: dict[str, SymbolSnapshot] = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)
    per_symbol: list[dict] = field(default_factory=list)
    signals: dict[str, list[Signal]] = field(default_factory=dict)
    options_ideas: dict[str, dict] = field(default_factory=dict)
    option_contracts: dict[str, OptionContract] = field(default_factory=dict)
    proposals: list[TradeProposal] = field(default_factory=list)
    commentary: str = ""

    def add_signal(self, signal: Signal) -> None:
        self.signals.setdefault(signal.symbol, []).append(signal)

    def signals_for(self, symbol: str) -> list[Signal]:
        return self.signals.get(symbol, [])
