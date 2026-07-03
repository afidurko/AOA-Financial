"""Agent team — bundles specialist agents for the swarm pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from aoa.agents.fundamental import FundamentalAgent
from aoa.agents.options import OptionsStrategistAgent
from aoa.agents.portfolio import PortfolioManagerAgent
from aoa.agents.risk import RiskManagerAgent
from aoa.agents.scanner import ScannerAgent
from aoa.agents.technical import TechnicalAgent
from aoa.brokerage.base import Broker
from aoa.config import RiskLimits
from aoa.llm.client import LLMClient


@dataclass
class AgentTeam:
    """All reasoning agents wired for one orchestrator / pipeline run."""

    scanner: ScannerAgent
    technical: TechnicalAgent
    fundamental: FundamentalAgent
    options: OptionsStrategistAgent
    portfolio: PortfolioManagerAgent
    risk: RiskManagerAgent

    @classmethod
    def from_llm(cls, llm: LLMClient, broker: Broker, *, risk: RiskLimits) -> AgentTeam:
        return cls(
            scanner=ScannerAgent(llm),
            technical=TechnicalAgent(llm),
            fundamental=FundamentalAgent(llm),
            options=OptionsStrategistAgent(llm, broker),
            portfolio=PortfolioManagerAgent(llm),
            risk=RiskManagerAgent(llm, risk),
        )
